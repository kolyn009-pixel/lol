from __future__ import annotations

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler

import database
from core import admin_roles
from . import schema, lesson_link_bridge

VK_MESSAGES_URL = "https://vk.me/club241263797"


def _link_keyboard(code: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать код", copy_text=CopyTextButton(text=code))],
        [InlineKeyboardButton("💙 Открыть VK", url=VK_MESSAGES_URL)],
        [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ])


async def _send_link_code(update, context):
    tg_id = int(update.effective_user.id)
    c = database.connect()
    try:
        user = c.execute("SELECT id,name FROM users WHERE telegram_id=? AND active=1 LIMIT 1", (tg_id,)).fetchone()
    finally:
        c.close()
    target = update.callback_query.message if update.callback_query else update.message
    if not user:
        await target.reply_text("Сначала завершите регистрацию ученика в TutorBot.")
        return
    code = schema.create_link_code(int(user["id"]), minutes=15)
    await target.reply_text(
        "💙 Подключение VK\n\n1️⃣ Нажми «Скопировать код»\n2️⃣ Открой VK\n3️⃣ Вставь код в сообщения сообщества и отправь\n\n"
        f"Код: {code}\n\nОн действует 15 минут и используется только один раз.",
        reply_markup=_link_keyboard(code),
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
        "💜 Подключение VK преподавателя\n\n1️⃣ Нажмите «Скопировать код»\n2️⃣ Откройте VK\n3️⃣ Вставьте код в сообщения сообщества и отправьте\n\n"
        f"Код: {code}\n\nКод действует 15 минут и используется один раз. После привязки во VK откроется меню преподавателя.",
        reply_markup=_link_keyboard(code),
    )


def _install_student_menu_patch():
    import bot as bot_module
    original = getattr(bot_module, "student_menu", None)
    if not callable(original) or getattr(original, "_vk_link_button_installed", False):
        return
    def student_menu_with_vk(user_id=None):
        markup = original(user_id)
        if markup is None:return markup
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

    from handlers import calendar_runtime
    calendar_runtime.install(application)

    from handlers import schedule_exceptions_v2
    schedule_exceptions_v2.install(application)

    # Replace the legacy teacher morning/evening content while preserving the
    # existing configurable dispatcher, ON/OFF switches and test buttons.
    from handlers import briefs_v2
    briefs_v2.install(application)

    from handlers import education_runtime
    education_runtime.install(application)

    from handlers import teacher_end_notifications
    teacher_end_notifications.install(application)

    from handlers import trial_ux_runtime
    trial_ux_runtime.install(application)

    from handlers import college_curriculum_handlers
    college_curriculum_handlers.install(application)

    from handlers import receipt_center
    for handler in receipt_center.handlers():
        application.add_handler(handler, group=-172)

    application.add_handler(CommandHandler("vklink", vklink_cmd), group=-171)
    application.add_handler(CommandHandler("vkadminlink", vkadminlink_cmd), group=-171)
    application.add_handler(CallbackQueryHandler(vklink_callback, pattern=r"^vk_link_start$"), group=-171)
