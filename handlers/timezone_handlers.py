from __future__ import annotations

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from core import admin_roles
from core import user_timezone

CUSTOM_OFFSET = 9901


def _back_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="global_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]])


def timezone_markup(telegram_id: int, include_back: bool = True):
    current = database.get_user_timezone(int(telegram_id))
    current_offset = int(current["msk_offset"] or 0) if current and int(current["configured"] or 0) else None
    rows = []
    for title, offset, zone_name in user_timezone.PRESETS:
        mark = "✅ " if current_offset == offset else ""
        rows.append([InlineKeyboardButton(f"{mark}{title} • {user_timezone.msk_label(offset)}", callback_data=f"tz_set|{offset}|{zone_name}")])
    rows.append([InlineKeyboardButton("🌍 Другой часовой пояс", callback_data="tz_custom")])
    if include_back:
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="global_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")])
    return InlineKeyboardMarkup(rows)


def menu_text(telegram_id: int) -> str:
    pref = database.get_user_timezone(int(telegram_id))
    if pref and int(pref["configured"] or 0):
        current = user_timezone.msk_label(pref["msk_offset"])
        intro = f"Сейчас у вас: {current}."
    else:
        intro = "Ваш часовой пояс пока не настроен."
    return (
        "💜 АДЕЛИЯ • ВАШЕ ВРЕМЯ\n\n"
        f"{intro}\n\n"
        "Все занятия и свободные окна я буду показывать по вашему местному времени. "
        "Само занятие при смене региона не переносится — меняется только отображение времени.\n\n"
        "Выберите регион:"
    )


def should_update_bot_timezone(telegram_id: int) -> bool:
    try:
        return bool(admin_roles.is_owner(int(telegram_id)))
    except Exception:
        return False


async def _apply(update: Update, context: ContextTypes.DEFAULT_TYPE, offset: int, zone_name: str | None):
    tid = int(update.effective_user.id)
    database.set_user_timezone(tid, int(offset), zone_name=zone_name, configured=True)
    database.mark_timezone_notified(tid)

    # Only the OWNER (the teacher) defines the TutorBot working timezone.
    # Other administrators keep a personal display zone in user_timezones
    # (already stored per telegram_id) and must not move bot-wide schedules.
    if should_update_bot_timezone(tid):
        effective_zone = zone_name or user_timezone.fixed_zone_name_from_msk_offset(int(offset))
        database.set_setting("bot_timezone", effective_zone)
        database.set_setting("bot_timezone_msk_offset", str(int(offset)))
        try:
            import bot as runtime
            runtime.apply_bot_timezone(effective_zone)
            if hasattr(runtime, "reschedule_all_upcoming_reminders"):
                runtime.reschedule_all_upcoming_reminders(context.application)
        except Exception as exc:
            print("TIMEZONE RUNTIME APPLY ERROR:", repr(exc))

    text = (
        "💜 Готово!\n\n"
        f"Ваше время: {user_timezone.msk_label(offset)}.\n\n"
        "Существующие занятия не перенесены. Я просто буду показывать их в вашем времени, "
        "а ежедневные локальные уведомления будут ориентироваться на выбранный регион."
    )
    q = update.callback_query
    if q:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главная", callback_data="global_home"), InlineKeyboardButton("🌍 Сменить пояс", callback_data="tz_menu")]]))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главная", callback_data="global_home"), InlineKeyboardButton("🌍 Сменить пояс", callback_data="tz_menu")]]))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return ConversationHandler.END
    await q.answer()
    data = q.data or ""
    if data == "tz_menu":
        await q.edit_message_text(menu_text(q.from_user.id), reply_markup=timezone_markup(q.from_user.id))
        return ConversationHandler.END
    if data.startswith("tz_set|"):
        _, offset, zone_name = data.split("|", 2)
        await _apply(update, context, int(offset), zone_name or None)
        return ConversationHandler.END
    if data == "tz_custom":
        await q.edit_message_text(
            "💜 ДРУГОЙ ЧАСОВОЙ ПОЯС\n\n"
            "Напишите разницу с московским временем.\n\n"
            "Например:\n"
            "+5 — если у вас на 5 часов больше Москвы\n"
            "-2 — если на 2 часа меньше Москвы\n\n"
            "Отправьте только +5 или -2.",
            reply_markup=_back_markup(),
        )
        return CUSTOM_OFFSET
    return ConversationHandler.END


async def custom_offset_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip().replace(" ", "")
    if not re.fullmatch(r"[+-]?\d{1,2}", raw):
        await update.message.reply_text("💜 Напишите только разницу с Москвой, например +5 или -2.", reply_markup=_back_markup())
        return CUSTOM_OFFSET
    offset = int(raw)
    # Global civil-time range UTC-12..UTC+14 => relative to Moscow: -15..+11.
    if offset < -15 or offset > 11:
        await update.message.reply_text("Такое смещение выглядит необычно. Допустимый диапазон: от МСК -15 до МСК +11.", reply_markup=_back_markup())
        return CUSTOM_OFFSET
    context.user_data["tz_custom_offset"] = offset
    example = (15 + offset) % 24
    day_note = ""
    if 15 + offset >= 24:
        day_note = " (уже следующий день)"
    elif 15 + offset < 0:
        day_note = " (ещё предыдущий день)"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Сохранить {user_timezone.msk_label(offset)}", callback_data=f"tz_confirm_custom|{offset}")],
        [InlineKeyboardButton("✏️ Ввести заново", callback_data="tz_custom")],
        [InlineKeyboardButton("❌ Отмена", callback_data="global_home")],
    ])
    await update.message.reply_text(
        "💜 Поняла.\n\n"
        f"Ваше время: {user_timezone.msk_label(offset)}.\n"
        f"Например, когда в Москве 15:00, у вас будет {example:02d}:00{day_note}.\n\n"
        "Ваши занятия не переносятся — меняется только то, как время показывается вам.",
        reply_markup=kb,
    )
    return ConversationHandler.END


async def confirm_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    offset = int((q.data or "").split("|", 1)[1])
    await _apply(update, context, offset, None)
    return ConversationHandler.END


def handlers():
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callbacks, pattern=r"^(?:tz_menu|tz_set\||tz_custom$)")],
        states={CUSTOM_OFFSET: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_offset_text)]},
        fallbacks=[],
        allow_reentry=True,
    )
    return [conv, CallbackQueryHandler(confirm_custom, pattern=r"^tz_confirm_custom\|"), CallbackQueryHandler(callbacks, pattern=r"^tz_")]
