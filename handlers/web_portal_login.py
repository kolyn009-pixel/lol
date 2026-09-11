"""Telegram entry points for Adelia web cabinets.

Codes are issued as separate persistent messages so opening the web cabinet does
not replace the main menu. Each code is one-time and valid for 10 minutes.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
try:
    from telegram import CopyTextButton
except ImportError:  # compatibility with older python-telegram-bot
    CopyTextButton = None
from telegram.ext import CallbackQueryHandler

import database
from core import admin_roles
from web_backend.parent_auth import create_parent_login_code
from web_backend.student_auth import issue_student_login_code
from web_backend.teacher_auth import issue_teacher_login_code

SITE_URL = "https://adeliatutor.ru"
TTL_MINUTES = 10


def issue_student_code(student_id: int) -> str:
    """Use the canonical student auth issuer so the website can validate it."""
    return issue_student_login_code(int(student_id), ttl_minutes=TTL_MINUTES)


def issue_teacher_code(telegram_id: int) -> str:
    """Use the canonical teacher auth issuer so the website can validate it."""
    return issue_teacher_login_code(int(telegram_id), ttl_minutes=TTL_MINUTES)


def _copy_button(code: str):
    if CopyTextButton is not None:
        return InlineKeyboardButton(
            "📋 Скопировать код",
            copy_text=CopyTextButton(text=str(code)),
        )
    return InlineKeyboardButton(
        "📋 Показать код",
        callback_data=f"web_show_code:{code}",
    )


def _code_markup(code: str, role: str):
    if role == "student":
        open_label, url, refresh, back = (
            "🌐 Открыть личный кабинет",
            f"{SITE_URL}/app/",
            "web_student_code",
            "main",
        )
    elif role == "parent":
        open_label, url, refresh, back = (
            "🌐 Открыть кабинет родителя",
            f"{SITE_URL}/parent/",
            "web_parent_code",
            "parent_main",
        )
    else:
        open_label, url, refresh, back = (
            "🌐 Открыть кабинет преподавателя",
            f"{SITE_URL}/teacher/",
            "web_teacher_code",
            "admin_main",
        )
    return InlineKeyboardMarkup([
        [_copy_button(code)],
        [InlineKeyboardButton(open_label, url=url)],
        [InlineKeyboardButton("🔄 Новый код", callback_data=refresh)],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data=back)],
    ])


async def _send_code_message(q, title: str, code: str, role: str, extra: str = ""):
    text = (
        f"{title}\n\n"
        f"Код для входа:\n`{code}`\n\n"
        "Код действует 10 минут и только один раз.\n"
        "Нажмите «Скопировать код» или откройте кабинет кнопкой ниже."
    )
    if extra:
        text += f"\n\n{extra}"
    await q.message.reply_text(
        text,
        reply_markup=_code_markup(code, role),
        parse_mode="Markdown",
    )


async def student_code(update, context):
    q = update.callback_query
    await q.answer("Код создан")
    user = database.get_user_by_telegram_id(update.effective_user.id)
    if not user or not user["active"]:
        await q.answer("Активный профиль ученика не найден.", show_alert=True); return
    code = issue_student_code(int(user["id"]))
    await _send_code_message(
        q,
        "🌐 ЛИЧНЫЙ КАБИНЕТ",
        code,
        "student",
        "На компьютере введите код на сайте. На телефоне можно сразу открыть кабинет.",
    )


async def parent_code(update, context):
    q = update.callback_query
    await q.answer("Код создан")
    parent = database.get_parent_by_telegram_id(update.effective_user.id)
    if not parent or not parent["active"]:
        await q.answer("Активный профиль родителя не найден.", show_alert=True); return
    issued = create_parent_login_code(int(parent["id"]))
    code = issued["code"]
    await _send_code_message(
        q,
        "🌐 РОДИТЕЛЬСКИЙ КАБИНЕТ",
        code,
        "parent",
        "В кабинете доступны расписание, прогресс, оплаты и остаток занятий.",
    )


async def teacher_code(update, context):
    q = update.callback_query
    await q.answer("Код создан")
    tid = int(update.effective_user.id)
    if not admin_roles.is_admin_id(tid):
        await q.answer("Доступ только преподавателю.", show_alert=True); return
    code = issue_teacher_code(tid)
    await _send_code_message(
        q,
        "🌐 КАБИНЕТ ПРЕПОДАВАТЕЛЯ",
        code,
        "teacher",
        "На компьютере введите код на сайте. На телефоне можно открыть кабинет сразу.",
    )


async def show_code(update, context):
    q = update.callback_query
    raw = str(q.data or "")
    code = raw.split(":", 1)[1] if ":" in raw else ""
    if len(code) == 6 and code.isdigit():
        await q.answer(f"Код: {code}", show_alert=True)
    else:
        await q.answer("Код недоступен", show_alert=True)


def handlers():
    return [
        CallbackQueryHandler(student_code, pattern=r"^web_student_code$"),
        CallbackQueryHandler(parent_code, pattern=r"^web_parent_code$"),
        CallbackQueryHandler(teacher_code, pattern=r"^web_teacher_code$"),
        CallbackQueryHandler(show_code, pattern=r"^web_show_code:\d{6}$"),
    ]
