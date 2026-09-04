from __future__ import annotations

import database
import education_profile
from core import admin_roles
from handlers import education_admin


async def _program_entry(update, context):
    """Existing program buttons in the student card become the edit entry point."""
    q = update.callback_query
    if not q or not admin_roles.is_admin_id(q.from_user.id):
        return
    await q.answer()
    try:
        pid = int(q.data.split("|", 1)[1])
    except Exception:
        return
    conn = database.connect()
    try:
        p = conn.execute("SELECT * FROM student_programs WHERE id=?", (pid,)).fetchone()
    finally:
        conn.close()
    if not p:
        return
    user = database.get_user(int(p["user_id"]))
    text = (
        f"📚 НАПРАВЛЕНИЕ\n\n👤 {user['name']}\n"
        f"🎓 {education_profile.label(user)}\n\n"
        f"📖 {education_admin.SUBJECTS.get(p['subject'], p['subject'])}\n"
        f"🎯 {education_admin.GOALS.get(p['study_goal'], p['study_goal'])}\n"
        f"{'⭐ Основное направление' if p['is_primary'] else 'Дополнительное направление'}\n\n"
        "Можно изменить направление или перевести ученика между школой и колледжем. История занятий и оплат останется прежней."
    )
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton("🎯 Сменить цель", callback_data=f"edu_goal_menu|{pid}"), InlineKeyboardButton("📖 Сменить предмет", callback_data=f"edu_subject_menu|{pid}")],
        [InlineKeyboardButton("🎓 Школа / колледж", callback_data=f"edu_profile|{user['id']}"), InlineKeyboardButton("📚 Все направления", callback_data=f"edu_programs|{user['id']}")],
    ]
    if not int(p["is_primary"] or 0):
        rows.append([InlineKeyboardButton("⭐ Сделать основным", callback_data=f"edu_primary|{pid}")])
    rows += [
        [InlineKeyboardButton("🚫 Отключить направление", callback_data=f"edu_disable|{pid}")],
        [InlineKeyboardButton("⬅️ К ученику", callback_data=f"student_view|{user['id']}")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


def install(application):
    """Activate college-aware registration after Application handlers exist."""
    education_profile.install_runtime()
    education_admin.initialize()

    import __main__ as bot
    replacements = {
        "registration_name": getattr(bot, "registration_name", None),
        "registration_grade": getattr(bot, "registration_grade", None),
        "registration_phone": getattr(bot, "registration_phone", None),
    }

    def patch_handler(handler):
        callback = getattr(handler, "callback", None)
        name = getattr(callback, "__name__", "")
        replacement = replacements.get(name)
        if replacement is not None and callback is not replacement:
            handler.callback = replacement
        states = getattr(handler, "states", None)
        if isinstance(states, dict):
            for items in states.values():
                for child in items: patch_handler(child)
        entries = getattr(handler, "entry_points", None)
        if entries:
            for child in entries: patch_handler(child)
        fallbacks = getattr(handler, "fallbacks", None)
        if fallbacks:
            for child in fallbacks: patch_handler(child)

    for group_handlers in application.handlers.values():
        for handler in group_handlers: patch_handler(handler)

    from telegram.ext import CallbackQueryHandler
    # Existing direction buttons on the student card now open the editable card.
    application.add_handler(CallbackQueryHandler(_program_entry, pattern=r"^admin_program\|"), group=-170)
    for handler in education_admin.handlers():
        application.add_handler(handler, group=-169)
