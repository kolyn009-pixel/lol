"""Telegram student homework UI backed by the shared homework channel presenter."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database
from core import homework_channel_ui
from web_backend.homework_status import canonical


def _status_icon(value):
    return {
        "ASSIGNED": "🟣",
        "SUBMITTED": "🟡",
        "UNDER_REVIEW": "🟡",
        "REVISION": "🔴",
        "REVIEWED": "🟢",
        "COMPLETED": "✅",
        "CANCELLED": "⚪",
    }.get(canonical(value), "📝")


async def homework_router(update, context):
    query = update.callback_query
    if not query:
        return
    user = database.get_user_by_telegram_id(update.effective_user.id)
    if not user or not int(user["active"] or 0):
        return

    data = str(query.data or "")
    if data == "homework":
        await query.answer()
        rows = homework_channel_ui.list_items(user["id"], 20)
        keyboard = []
        for i, row in enumerate(rows, 1):
            status = row["status"] if "status" in row.keys() else "ASSIGNED"
            keyboard.append([InlineKeyboardButton(
                f"{_status_icon(status)} {homework_channel_ui.item_title(row, i)[:38]}",
                callback_data=f"homework_view|{row['id']}",
            )])
        keyboard.append([InlineKeyboardButton("🌐 Открыть все ДЗ в Аделии", url=homework_channel_ui.app_url())])
        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main")])
        await query.edit_message_text(
            homework_channel_ui.list_text(user["id"], 20),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("homework_view|"):
        await query.answer()
        try:
            homework_id = int(data.split("|", 1)[1])
        except Exception:
            return
        item = homework_channel_ui.detail(user["id"], homework_id)
        if not item:
            await query.answer("Это домашнее задание недоступно.", show_alert=True)
            return
        await query.edit_message_text(
            item["text"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Открыть и выполнить в Аделии", url=item["url"])],
                [InlineKeyboardButton("⬅️ К домашним заданиям", callback_data="homework")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main")],
            ]),
        )


def handlers():
    return [CallbackQueryHandler(homework_router, pattern=r"^(homework|homework_view\|\d+)$")]
