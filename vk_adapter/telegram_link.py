from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler

import database
from . import schema, lesson_link_bridge


async def vklink_cmd(update, context):
    tg_id = int(update.effective_user.id)
    c = database.connect()
    try:
        user = c.execute(
            "SELECT id,name FROM users WHERE telegram_id=? AND active=1 LIMIT 1",
            (tg_id,),
        ).fetchone()
    finally:
        c.close()

    if not user:
        await update.message.reply_text(
            "Сначала завершите регистрацию ученика в TutorBot."
        )
        return

    code = schema.create_link_code(int(user["id"]), minutes=15)
    await update.message.reply_text(
        "🔗 ПОДКЛЮЧЕНИЕ VK\n\n"
        "Откройте сообщения сообщества Аделии во ВКонтакте и отправьте туда этот код:\n\n"
        f"{code}\n\n"
        "Код действует 15 минут и может быть использован только один раз.\n"
        "После привязки Telegram и VK будут работать с одной карточкой ученика, одним расписанием и одним балансом.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
        ]),
    )


def register(application):
    schema.initialize()
    lesson_link_bridge.install()
    application.add_handler(CommandHandler("vklink", vklink_cmd))
