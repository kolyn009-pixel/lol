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
    return issue_student_login_code(int(student_id), ttl_minutes=TTL_MINUTES)


def issue_teacher_code(telegram_id: int) -> str:
    return issue_teacher_login_code(int(telegram_id), ttl_minutes=TTL_MINUTES)


def _copy_button(code: str):
    if CopyTextButton is not None:
        try:
            return InlineKeyboardButton(
                "📋 Скопировать код",
                copy_text=CopyTextButton(text=str(code)),
            )
        except Exception:
            pass
    return InlineKeyboardButton(
        "📋 Показать код",
        callback_data=f"web_show_code:{code}",
    )


def _code_markup(code: str, role: str, *, native_copy: bool = True):
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

    copy_button = (
        _copy_button(code)
        if native_copy
        else InlineKeyboardButton(
            "📋 Показать код",
            callback_data=f"web_show_code:{code}",
        )
    )

    return InlineKeyboardMarkup([
        [copy_button],
        [InlineKeyboardButton(open_label, url=url)],
        [InlineKeyboardButton("🔄 Новый код", callback_data=refresh)],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data=back)],
    ])


async def _send_code_message(q, title: str, code: str, role: str, extra: str = ""):
    text = (
        f"{title}\n\n"
        f"Код для входа:\n`{code}`\n\n"
        "Код действует 10 минут и только один раз.\n"
        "Нажмите кнопку ниже или скопируйте цифры из сообщения."
    )
    if extra:
        text += f"\n\n{extra}"

    try:
        await q.message.reply_text(
            text,
            reply_markup=_code_markup(code, role, native_copy=True),
            parse_mode="Markdown",
        )
        print("WEB LOGIN CODE MESSAGE SENT", role, q.from_user.id)
        return
    except Exception as exc:
        print("WEB LOGIN CODE MESSAGE PRIMARY SEND FAILED", role, q.from_user.id, repr(exc))

    # Guaranteed fallback: no CopyTextButton and no Markdown dependency.
    fallback_text = (
        f"{title}\n\n"
        f"Код для входа: {code}\n\n"
        "Код действует 10 минут и только один раз."
    )
    if extra:
        fallback_text += f"\n\n{extra}"

    try:
        await q.message.reply_text(
            fallback_text,
            reply_markup=_code_markup(code, role, native_copy=False),
        )
        print("WEB LOGIN CODE MESSAGE FALLBACK SENT", role, q.from_user.id)
    except Exception as exc:
        print("WEB LOGIN CODE MESSAGE FALLBACK FAILED", role, q.from_user.id, repr(exc))
        # Last resort: send plain text only. If this fails as well, let the error
        # surface so it is visible in systemd logs instead of silently disappearing.
        await q.message.reply_text(f"Код для входа: {code}\nДействует 10 минут.")
        print("WEB LOGIN CODE MESSAGE PLAIN SENT", role, q.from_user.id)


async def student_code(update, context):
    q = update.callback_query
    user = database.get_user_by_telegram_id(update.effective_user.id)
    if not user or not user["active"]:
        await q.answer("Активный профиль ученика не найден.", show_alert=True)
        return
    try:
        code = issue_student_code(int(user["id"]))
    except Exception as exc:
        print("WEB LOGIN CODE ISSUE FAILED student", update.effective_user.id, repr(exc))
        await q.answer("Не удалось создать код. Попробуйте ещё раз.", show_alert=True)
        return
    await q.answer("Код создан")
    await _send_code_message(
        q,
        "🌐 ЛИЧНЫЙ КАБИНЕТ",
        code,
        "student",
        "На компьютере введите код на сайте. На телефоне можно сразу открыть кабинет.",
    )


async def parent_code(update, context):
    q = update.callback_query
    parent = database.get_parent_by_telegram_id(update.effective_user.id)
    if not parent or not parent["active"]:
        await q.answer("Активный профиль родителя не найден.", show_alert=True)
        return
    try:
        issued = create_parent_login_code(int(parent["id"]))
        code = issued["code"]
    except Exception as exc:
        print("WEB LOGIN CODE ISSUE FAILED parent", update.effective_user.id, repr(exc))
        await q.answer("Не удалось создать код. Попробуйте ещё раз.", show_alert=True)
        return
    await q.answer("Код создан")
    await _send_code_message(
        q,
        "🌐 РОДИТЕЛЬСКИЙ КАБИНЕТ",
        code,
        "parent",
        "В кабинете доступны расписание, прогресс, оплаты и остаток занятий.",
    )


async def teacher_code(update, context):
    q = update.callback_query
    tid = int(update.effective_user.id)
    if not admin_roles.is_admin_id(tid):
        await q.answer("Доступ только преподавателю.", show_alert=True)
        return
    try:
        code = issue_teacher_code(tid)
    except Exception as exc:
        print("WEB LOGIN CODE ISSUE FAILED teacher", tid, repr(exc))
        await q.answer("Не удалось создать код. Попробуйте ещё раз.", show_alert=True)
        return
    await q.answer("Код создан")
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
