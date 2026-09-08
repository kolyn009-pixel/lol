"""Telegram entry points for Adelia web cabinets.

This module deliberately owns only code issuance. The website consumes the same
SQLite tables through web_backend.student_auth / teacher_auth. Codes are
6-digit, one-time and valid for 10 minutes, which makes them convenient for
logging in on a desktop while the Telegram button opens the site on a phone.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database
from core import admin_roles

SITE_URL = "https://adeliatutor.ru"
TTL_MINUTES = 10


def ensure_tables():
    conn = database.connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS student_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_student_web_login_code
            ON student_web_login_codes(code);

        CREATE TABLE IF NOT EXISTS teacher_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_telegram_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_teacher_web_code
            ON teacher_web_login_codes(code);
        """
    )
    conn.commit()
    conn.close()


def _code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _expiry():
    return (datetime.now() + timedelta(minutes=TTL_MINUTES)).isoformat(timespec="seconds")


def issue_student_code(student_id: int) -> str:
    ensure_tables(); student_id = int(student_id); conn = database.connect()
    row = conn.execute("SELECT id FROM users WHERE id=? AND active=1", (student_id,)).fetchone()
    if not row:
        conn.close(); raise ValueError("student_not_found")
    conn.execute(
        "UPDATE student_web_login_codes SET used_at=? WHERE student_id=? AND used_at IS NULL",
        (database.now_iso(), student_id),
    )
    while True:
        code = _code()
        if not conn.execute("SELECT 1 FROM student_web_login_codes WHERE code=?", (code,)).fetchone():
            break
    conn.execute(
        "INSERT INTO student_web_login_codes(student_id,code,expires_at,created_at) VALUES(?,?,?,?)",
        (student_id, code, _expiry(), database.now_iso()),
    )
    conn.commit(); conn.close(); return code


def issue_teacher_code(telegram_id: int) -> str:
    ensure_tables(); telegram_id = int(telegram_id)
    if not admin_roles.is_admin_id(telegram_id):
        raise PermissionError("not_admin")
    conn = database.connect()
    conn.execute(
        "UPDATE teacher_web_login_codes SET used_at=? WHERE admin_telegram_id=? AND used_at IS NULL",
        (database.now_iso(), telegram_id),
    )
    while True:
        code = _code()
        if not conn.execute("SELECT 1 FROM teacher_web_login_codes WHERE code=?", (code,)).fetchone():
            break
    conn.execute(
        "INSERT INTO teacher_web_login_codes(admin_telegram_id,code,expires_at,created_at) VALUES(?,?,?,?)",
        (telegram_id, code, _expiry(), database.now_iso()),
    )
    conn.commit(); conn.close(); return code


async def student_code(update, context):
    q = update.callback_query
    await q.answer()
    user = database.get_user_by_telegram_id(update.effective_user.id)
    if not user or not user["active"]:
        await q.answer("Активный профиль ученика не найден.", show_alert=True); return
    code = issue_student_code(int(user["id"]))
    await q.edit_message_text(
        "🌐 ЛИЧНЫЙ КАБИНЕТ\n\n"
        f"Код для входа: {code}\n\n"
        "Он действует 10 минут и только один раз.\n"
        "На компьютере открой сайт и введи этот код. На телефоне можно сразу нажать кнопку ниже.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Открыть личный кабинет", url=f"{SITE_URL}/app/")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")],
        ]),
    )


async def teacher_code(update, context):
    q = update.callback_query
    await q.answer()
    tid = int(update.effective_user.id)
    if not admin_roles.is_admin_id(tid):
        await q.answer("Доступ только преподавателю.", show_alert=True); return
    code = issue_teacher_code(tid)
    await q.edit_message_text(
        "🌐 КАБИНЕТ ПРЕПОДАВАТЕЛЯ\n\n"
        f"Код для входа: {code}\n\n"
        "Код действует 10 минут и только один раз.\n"
        "На компьютере введи его на сайте, а на телефоне просто открой кабинет кнопкой ниже.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Открыть кабинет", url=f"{SITE_URL}/teacher/")],
            [InlineKeyboardButton("⬅️ Админка", callback_data="admin_main")],
        ]),
    )


def handlers():
    return [
        CallbackQueryHandler(student_code, pattern=r"^web_student_code$"),
        CallbackQueryHandler(teacher_code, pattern=r"^web_teacher_code$"),
    ]
