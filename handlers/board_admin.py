from __future__ import annotations

from urllib.parse import urlparse

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    ApplicationHandlerStop,
    filters,
)

import database
from core import admin_roles


STATE_KEY = "admin_board_user_id"


def _is_admin(update: Update) -> bool:
    return bool(
        update.effective_user
        and admin_roles.is_admin_id(update.effective_user.id)
    )


def _valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value.strip())
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.netloc)
        )
    except Exception:
        return False


def _save_board(user_id: int, url: str) -> None:
    conn = database.connect()
    try:
        conn.execute(
            """
            UPDATE users
            SET board_url=?,
                updated_at=?
            WHERE id=?
            """,
            (
                url.strip(),
                database.now_iso(),
                int(user_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if not q:
        return

    if not _is_admin(update):
        await q.answer(
            "Нет доступа",
            show_alert=True,
        )
        return

    try:
        user_id = int(
            str(q.data).split("|", 1)[1]
        )
    except Exception:
        await q.answer(
            "Не удалось определить ученика",
            show_alert=True,
        )
        return

    user = database.get_user(user_id)

    if not user:
        await q.answer(
            "Ученик не найден",
            show_alert=True,
        )
        return

    context.user_data[STATE_KEY] = user_id

    await q.answer()

    await q.message.reply_text(
        "🖥 ДОБАВИТЬ ДОСКУ\n\n"
        f"👤 {user['name']}\n\n"
        "Отправьте ссылку на постоянную доску "
        "одним сообщением.\n\n"
        "Например:\n"
        "https://..."
    )


async def receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return

    user_id = context.user_data.get(STATE_KEY)

    if not user_id:
        return

    if not update.message or not update.message.text:
        return

    value = update.message.text.strip()

    if not _valid_url(value):
        await update.message.reply_text(
            "⚠️ Это не похоже на ссылку.\n\n"
            "Отправьте полный адрес, начинающийся "
            "с https:// или http://"
        )
        return

    user = database.get_user(int(user_id))

    if not user:
        context.user_data.pop(STATE_KEY, None)

        await update.message.reply_text(
            "❌ Ученик больше не найден."
        )
        return

    _save_board(
        int(user_id),
        value,
    )

    context.user_data.pop(STATE_KEY, None)

    await update.message.reply_text(
        "✅ ДОСКА СОХРАНЕНА\n\n"
        f"👤 {user['name']}\n"
        f"🖥 {value}\n\n"
        "В следующих напоминаниях кнопка "
        "добавления доски больше не появится."
    )


def install(application):
    # Callback ставим раньше обычных admin callback-ов.
    application.add_handler(
        CallbackQueryHandler(
            start,
            pattern=r"^admin_add_board\|\d+$",
        ),
        group=-175,
    )

    # Текст перехватывается только если администратор перед этим
    # нажал «Добавить доску».
    async def guarded_receive(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ):
        if context.user_data.get(STATE_KEY):
            await receive(update, context)
            raise ApplicationHandlerStop

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            guarded_receive,
        ),
        group=-175,
    )
