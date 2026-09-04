from __future__ import annotations

import database
import education_profile
from core import admin_roles
from handlers import education_admin


async def _program_entry(update, context):
    q = update.callback_query
    if not q or not admin_roles.is_admin_id(q.from_user.id): return
    await q.answer()
    try: pid = int(q.data.split("|", 1)[1])
    except Exception: return
    conn = database.connect()
    try: p = conn.execute("SELECT * FROM student_programs WHERE id=?", (pid,)).fetchone()
    finally: conn.close()
    if not p:return
    user = database.get_user(int(p["user_id"]))
    text = (f"📚 НАПРАВЛЕНИЕ\n\n👤 {user['name']}\n🎓 {education_profile.label(user)}\n\n"
            f"📖 {education_admin.SUBJECTS.get(p['subject'], p['subject'])}\n🎯 {education_admin.GOALS.get(p['study_goal'], p['study_goal'])}\n"
            f"{'⭐ Основное направление' if p['is_primary'] else 'Дополнительное направление'}\n\n"
            "Можно изменить направление или перевести ученика между школой и колледжем. История занятий и оплат останется прежней.")
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton("🎯 Сменить цель", callback_data=f"edu_goal_menu|{pid}"), InlineKeyboardButton("📖 Сменить предмет", callback_data=f"edu_subject_menu|{pid}")],
            [InlineKeyboardButton("🎓 Школа / колледж", callback_data=f"edu_profile|{user['id']}"), InlineKeyboardButton("📚 Все направления", callback_data=f"edu_programs|{user['id']}")]]
    if not int(p["is_primary"] or 0): rows.append([InlineKeyboardButton("⭐ Сделать основным", callback_data=f"edu_primary|{pid}")])
    rows += [[InlineKeyboardButton("🚫 Отключить направление", callback_data=f"edu_disable|{pid}")], [InlineKeyboardButton("⬅️ К ученику", callback_data=f"student_view|{user['id']}")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


def _walk(application):
    seen=set()
    def visit(handler):
        if id(handler) in seen:return
        seen.add(id(handler));yield handler
        states=getattr(handler,"states",None)
        if isinstance(states,dict):
            for items in states.values():
                for child in items:yield from visit(child)
        for attr in ("entry_points","fallbacks"):
            for child in (getattr(handler,attr,None) or []):yield from visit(child)
    for group_handlers in application.handlers.values():
        for handler in group_handlers:yield from visit(handler)


def install(application):
    """Activate education support without replacing legacy registration completion."""
    # Save the real completion callback first: it contains parent/timezone/admin
    # behavior that must remain exactly as production currently implements it.
    original_phone = None
    for h in _walk(application):
        cb=getattr(h,"callback",None)
        if getattr(cb,"__name__","")=="registration_phone": original_phone=cb;break

    education_profile.install_runtime()
    education_admin.initialize()
    import __main__ as bot

    patched_name=getattr(bot,"registration_name",None)
    patched_grade=getattr(bot,"registration_grade",None)

    async def registration_phone_preserved(update, context):
        result = await original_phone(update, context)
        try:
            user = database.get_user_by_telegram_id(int(update.effective_user.id))
            if user and context.user_data.get("reg_education_type"):
                education_profile.set_profile(
                    int(user["id"]),
                    context.user_data.get("reg_education_type","SCHOOL"),
                    int(context.user_data.get("reg_education_level") or context.user_data.get("reg_grade") or user["grade"]),
                )
        except Exception as exc:
            print("EDUCATION REGISTRATION FINALIZE ERROR:",repr(exc))
        return result

    for h in _walk(application):
        cb=getattr(h,"callback",None);name=getattr(cb,"__name__","")
        if name=="registration_name" and patched_name: h.callback=patched_name
        elif name=="registration_grade" and patched_grade: h.callback=patched_grade
        elif name=="registration_phone" and original_phone: h.callback=registration_phone_preserved

    from telegram.ext import CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(_program_entry, pattern=r"^admin_program\|"), group=-170)
    for handler in education_admin.handlers(): application.add_handler(handler, group=-169)
