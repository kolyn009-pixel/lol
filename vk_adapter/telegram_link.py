from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

import database
from core import admin_roles
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
        await target.reply_text("Сначала завершите регистрацию ученика в TutorBot.")
        return

    code = schema.create_link_code(int(user["id"]), minutes=15)
    await target.reply_text(
        "🔗 ПОДКЛЮЧЕНИЕ VK\n\n"
        "Откройте сообщения сообщества Аделии во ВКонтакте и отправьте туда этот код:\n\n"
        f"{code}\n\n"
        "Код действует 15 минут и может быть использован только один раз.\n"
        "После привязки Telegram и VK будут работать с одной карточкой ученика, одним расписанием и одним балансом.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]),
    )


async def vklink_cmd(update, context):
    await _send_link_code(update, context)


async def vklink_callback(update, context):
    await update.callback_query.answer()
    await _send_link_code(update, context)


async def vkadminlink_cmd(update, context):
    tg_id = int(update.effective_user.id)
    if not admin_roles.is_admin_id(tg_id):
        await update.message.reply_text("🔒 Команда доступна только преподавателю.")
        return
    code = schema.create_admin_link_code(tg_id, minutes=15)
    await update.message.reply_text(
        "💜 ПОДКЛЮЧЕНИЕ VK ПРЕПОДАВАТЕЛЯ\n\n"
        "Отправьте этот код в сообщения сообщества Аделии во ВКонтакте:\n\n"
        f"{code}\n\n"
        "Код действует 15 минут и используется один раз. После привязки во VK откроется меню преподавателя."
    )


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
        if not any(button.callback_data == "vk_link_start" for row in rows for button in row):
            rows.append([InlineKeyboardButton("🔗 Привязать VK", callback_data="vk_link_start")])
        return InlineKeyboardMarkup(rows)

    student_menu_with_vk._vk_link_button_installed = True
    bot_module.student_menu = student_menu_with_vk


def register(application):
    schema.initialize()
    lesson_link_bridge.install()
    _install_student_menu_patch()
    application.add_handler(CommandHandler("vklink", vklink_cmd), group=-171)
    application.add_handler(CommandHandler("vkadminlink", vkadminlink_cmd), group=-171)
    application.add_handler(CallbackQueryHandler(vklink_callback, pattern=r"^vk_link_start$"), group=-171)
