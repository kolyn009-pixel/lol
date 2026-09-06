from __future__ import annotations

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, MessageHandler, filters

import database
from core import admin_roles

STATE_KEY = "schedule_exception_v2"


def _admin(update):
    return bool(update.effective_user and admin_roles.is_admin_id(int(update.effective_user.id)))


def _home_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Исключения", callback_data="schedule_exceptions")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="global_home")],
    ])


def _parse_date(text):
    value = str(text or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except Exception:
            pass
    raise ValueError("Дата нужна в формате ДД.ММ.ГГГГ")


def _parse_time(text):
    value = str(text or "").strip()
    try:
        return datetime.strptime(value, "%H:%M").strftime("%H:%M")
    except Exception:
        raise ValueError("Время нужно в формате ЧЧ:ММ")


async def start(update, context):
    q = update.callback_query
    if not q or not _admin(update):
        return
    await q.answer()
    context.user_data.pop(STATE_KEY, None)
    await q.edit_message_text(
        "🚫 НЕДОСТУПНОЕ ВРЕМЯ\n\nЧто закрываем для новых записей?\n\n"
        "• Целый день — полностью выходной.\n"
        "• Промежуток — например, 14:00–18:00; остальной день останется рабочим.\n\n"
        "Уже созданные занятия автоматически не удаляются и не переносятся.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Целый день", callback_data="schedule_closed_v2|FULL")],
            [InlineKeyboardButton("🕐 Указать промежуток", callback_data="schedule_closed_v2|PARTIAL")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="schedule_exceptions")],
        ]),
    )
    raise ApplicationHandlerStop


async def choose(update, context):
    q = update.callback_query
    if not q or not _admin(update):
        return
    await q.answer()
    mode = q.data.split("|", 1)[1].upper()
    context.user_data[STATE_KEY] = {"mode": mode, "step": "DATE"}
    await q.edit_message_text(
        ("🚫 ВЫХОДНОЙ НА ВЕСЬ ДЕНЬ" if mode == "FULL" else "🕐 НЕДОСТУПНЫЙ ПРОМЕЖУТОК")
        + "\n\nОтправьте дату в формате ДД.ММ.ГГГГ.\nНапример: 12.09.2026",
        reply_markup=_home_kb(),
    )
    raise ApplicationHandlerStop


async def text(update, context):
    if not _admin(update):
        return
    st = context.user_data.get(STATE_KEY)
    if not st:
        return
    raw = (update.message.text or "").strip()
    try:
        if st["step"] == "DATE":
            st["date"] = _parse_date(raw)
            if st["mode"] == "FULL":
                st["step"] = "COMMENT"
                await update.message.reply_text(
                    "💬 Можно добавить комментарий, например «личные дела».\n"
                    "Если комментарий не нужен — отправьте -"
                )
            else:
                st["step"] = "START"
                await update.message.reply_text("🕐 С какого времени закрыть? Например: 14:00")
            raise ApplicationHandlerStop

        if st["step"] == "START":
            st["start_time"] = _parse_time(raw)
            st["step"] = "END"
            await update.message.reply_text("🕐 До какого времени закрыть? Например: 18:00")
            raise ApplicationHandlerStop

        if st["step"] == "END":
            st["end_time"] = _parse_time(raw)
            if st["end_time"] <= st["start_time"]:
                st["step"] = "START"
                await update.message.reply_text(
                    "❌ Конец должен быть позже начала.\n\nВведите время начала ещё раз, например 14:00"
                )
                raise ApplicationHandlerStop
            st["step"] = "COMMENT"
            await update.message.reply_text(
                "💬 Можно добавить комментарий, например «врач» или «дорога».\n"
                "Если комментарий не нужен — отправьте -"
            )
            raise ApplicationHandlerStop

        if st["step"] == "COMMENT":
            comment = None if raw == "-" else raw[:200]
            database.add_schedule_exception(
                st["date"],
                "CLOSED",
                start_time=st.get("start_time"),
                end_time=st.get("end_time"),
                comment=comment,
            )
            if st["mode"] == "FULL":
                result = f"✅ {datetime.fromisoformat(st['date']).strftime('%d.%m.%Y')} отмечен как выходной на весь день."
            else:
                result = (
                    f"✅ {datetime.fromisoformat(st['date']).strftime('%d.%m.%Y')} "
                    f"закрыт промежуток {st['start_time']}–{st['end_time']}.\n\n"
                    "Остальные рабочие интервалы этого дня сохраняются."
                )
            if comment:
                result += f"\n💬 {comment}"
            context.user_data.pop(STATE_KEY, None)
            await update.message.reply_text(result, reply_markup=_home_kb())
            raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}\nПопробуйте ещё раз.")
        raise ApplicationHandlerStop


def install(application):
    application.add_handler(CallbackQueryHandler(start, pattern=r"^schedule_closed_add$"), group=-176)
    application.add_handler(CallbackQueryHandler(choose, pattern=r"^schedule_closed_v2\|(?:FULL|PARTIAL)$"), group=-176)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text), group=-176)
