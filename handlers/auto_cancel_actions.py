import asyncio
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database


def _ensure_schema():
    c = database.connect()
    try:
        cols = {
            row["name"]
            for row in c.execute("PRAGMA table_info(lessons)").fetchall()
        }

        if "allow_unpaid" not in cols:
            c.execute(
                "ALTER TABLE lessons "
                "ADD COLUMN allow_unpaid INTEGER NOT NULL DEFAULT 0"
            )

        if "auto_cancel_admin_decision" not in cols:
            c.execute(
                "ALTER TABLE lessons "
                "ADD COLUMN auto_cancel_admin_decision TEXT"
            )

        c.commit()
    finally:
        c.close()


def admin_keyboard(lesson_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "❌ Оставить отменённым",
                callback_data=f"autocancel_keep|{lesson_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "💳 Предложить ученику оплатить",
                callback_data=f"autocancel_offer|{lesson_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "🕓 Провести, ожидая оплаты",
                callback_data=f"autocancel_allow|{lesson_id}",
            )
        ],
    ])


def _restore(lesson_id, *, allow_unpaid, decision):
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE lessons
            SET lesson_status='CONFIRMED',
                payment_status='AWAITING_PAYMENT',
                cancelled_at=NULL,
                cancellation_reason=NULL,
                auto_cancelled_for_nonpayment=0,
                allow_unpaid=?,
                auto_cancel_admin_decision=?,
                updated_at=?
            WHERE id=?
            """,
            (
                1 if allow_unpaid else 0,
                decision,
                datetime.now().isoformat(timespec="seconds"),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()


def _keep_cancelled(lesson_id):
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE lessons
            SET allow_unpaid=0,
                auto_cancel_admin_decision='KEEP_CANCELLED',
                updated_at=?
            WHERE id=?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()


async def _ensure_calendar(lesson_id):
    try:
        import __main__ as runtime

        fn = getattr(runtime, "ensure_google_event", None)
        if fn:
            await fn(int(lesson_id))
    except Exception as exc:
        print("AUTOCANCEL CALENDAR RESTORE ERROR:", lesson_id, repr(exc))


async def callbacks(update, context):
    q = update.callback_query
    data = q.data or ""

    await q.answer()

    try:
        lesson_id = int(data.split("|", 1)[1])
    except Exception:
        await q.answer("Некорректное занятие", show_alert=True)
        return

    lesson = database.get_lesson(lesson_id)
    if not lesson:
        await q.answer("Занятие не найдено", show_alert=True)
        return

    user = database.get_user(int(lesson["user_id"]))

    if data.startswith("autocancel_keep|"):
        _keep_cancelled(lesson_id)

        await q.edit_message_text(
            (q.message.text or "")
            + "\n\n❌ Решение: оставить занятие отменённым."
        )
        return

    if data.startswith("autocancel_offer|"):
        _restore(
            lesson_id,
            allow_unpaid=False,
            decision="OFFER_PAYMENT",
        )

        await _ensure_calendar(lesson_id)

        if user and user["telegram_id"]:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=(
                    "💜 Преподаватель сохранил занятие.\n\n"
                    "Пожалуйста, оплати занятие перед началом. "
                    "После подтверждения оплаты запись останется активной."
                ),
            )

        await q.edit_message_text(
            (q.message.text or "")
            + "\n\n💳 Решение: предложить ученику оплатить.\n"
              "Занятие восстановлено."
        )
        return

    if data.startswith("autocancel_allow|"):
        _restore(
            lesson_id,
            allow_unpaid=True,
            decision="ALLOW_UNPAID",
        )

        await _ensure_calendar(lesson_id)

        if user and user["telegram_id"]:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=(
                    "💜 Занятие восстановлено.\n\n"
                    "Преподаватель разрешил провести его, "
                    "ожидая оплату. Запись остаётся активной."
                ),
            )

        await q.edit_message_text(
            (q.message.text or "")
            + "\n\n🕓 Решение: провести, ожидая оплаты.\n"
              "Занятие восстановлено и повторно "
              "автоматически отменено не будет."
        )
        return


def install(application):
    _ensure_schema()

    application.add_handler(
        CallbackQueryHandler(
            callbacks,
            pattern=r"^autocancel_(keep|offer|allow)\|",
        ),
        group=-190,
    )
