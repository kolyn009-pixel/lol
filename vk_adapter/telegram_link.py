from __future__ import annotations

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

import database
from . import schema, lesson_link_bridge


async def _send_link_code(update, context):
    tg_id = int(update.effective_user.id)
    c = database.connect()
    try:
        user = c.execute(
            "SELECT id,name FROM users WHERE telegram_id=? AND active=1 LIMIT 1",
            (tg_id,),
        ).fetchone()
    finally:
        c.close()

    target = update.callback_query.message if update.callback_query else update.message

    if not user:
        await target.reply_text(
            "Сначала завершите регистрацию ученика в TutorBot."
        )
        return

    code = schema.create_link_code(int(user["id"]), minutes=15)
    await target.reply_text(
        "💙 Подключение VK\n\n"
        "1️⃣ Нажми «Скопировать код»\n"
        "2️⃣ Открой VK\n"
        "3️⃣ Вставь код в сообщения сообщества и отправь\n\n"
        f"Код: {code}\n\n"
        "Он действует 15 минут и используется только один раз.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📋 Скопировать код",
                    copy_text=CopyTextButton(text=code),
                )
            ],
            [
                InlineKeyboardButton(
                    "💙 Открыть VK",
                    url="https://vk.me/club241263797",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 Главная",
                    callback_data="global_home",
                )
            ],
        ]),
    )


async def vklink_cmd(update, context):
    await _send_link_code(update, context)


async def vklink_callback(update, context):
    await update.callback_query.answer()
    await _send_link_code(update, context)


def _install_student_menu_patch():
    import bot as bot_module

    original = getattr(bot_module, "student_menu", None)
    if not callable(original):
        return
    if getattr(original, "_vk_link_button_installed", False):
        return

    def student_menu_with_vk(user_id=None):
        markup = original(user_id)
        if markup is None:
            return markup

        rows = [list(row) for row in markup.inline_keyboard]
        if not any(
            button.callback_data == "vk_link_start"
            for row in rows
            for button in row
        ):
            rows.append([
                InlineKeyboardButton(
                    "🔗 Привязать VK",
                    callback_data="vk_link_start",
                )
            ])
        return InlineKeyboardMarkup(rows)

    student_menu_with_vk._vk_link_button_installed = True
    bot_module.student_menu = student_menu_with_vk


def register(application):
    schema.initialize()
    lesson_link_bridge.install()
    _install_student_menu_patch()
    application.add_handler(CommandHandler("vklink", vklink_cmd), group=-171)
    application.add_handler(
        CallbackQueryHandler(vklink_callback, pattern=r"^vk_link_start$"),
        group=-171,
    )
