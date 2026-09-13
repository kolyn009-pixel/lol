from __future__ import annotations

import database
from core import user_timezone

_INSTALLED = False


def parent_telegram_ids(student_id, user=None):
    """Return active linked parent Telegram ids, with legacy fallback."""
    result = []
    seen = set()
    try:
        for parent in database.get_student_parents(int(student_id)):
            tid = parent["telegram_id"] if "telegram_id" in parent.keys() else None
            if tid is None:
                continue
            tid = int(tid)
            if tid not in seen:
                seen.add(tid)
                result.append(tid)
    except Exception:
        pass

    if not result:
        if user is None:
            try:
                user = database.get_user(int(student_id))
            except Exception:
                user = None
        try:
            legacy = user["parent_telegram_id"] if user is not None and "parent_telegram_id" in user.keys() else None
        except Exception:
            legacy = None
        if legacy:
            legacy = int(legacy)
            if legacy not in seen:
                result.append(legacy)
    return result


def has_parent_recipient(student_id, user=None):
    return bool(parent_telegram_ids(student_id, user=user))


def install():
    """Patch the legacy Telegram payment reminder without touching bot.py.

    When at least one active parent is linked to the student, payment reminders
    are sent only to the linked parent account(s). The student receives no
    payment reminder. Students without a parent keep the existing behavior.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    import __main__ as runtime

    original = getattr(runtime, "payment_reminder_job", None)
    if original is None or getattr(original, "_adelia_parent_payment_routing", False):
        return

    async def payment_reminder_job(context):
        data = getattr(context.job, "data", None) or {}
        lesson_id = data.get("lesson_id")
        reminder_type = data.get("reminder_type")
        if not lesson_id:
            return await original(context)

        lesson = database.get_lesson(int(lesson_id))
        if lesson is None:
            return await original(context)
        user = database.get_user(int(lesson["user_id"]))
        if user is None:
            return await original(context)

        recipients = parent_telegram_ids(int(user["id"]), user=user)
        if not recipients:
            return await original(context)

        if str(database.get_setting("notify_payment", "1")).lower() in ("0", "false", "off", "no"):
            return
        if database.reminder_was_sent(int(lesson_id), str(reminder_type)):
            return
        if str(lesson["lesson_status"] or "") != "CONFIRMED":
            return
        if str(lesson["payment_status"] or "") != "AWAITING_PAYMENT":
            return

        names = {
            "PAYMENT_24H": "До занятия осталось меньше суток.",
            "PAYMENT_8H": "До занятия осталось около 8 часов.",
        }
        try:
            amount = runtime.payments.money(lesson["price"])
        except Exception:
            amount = f"{int(lesson['price'] or 0):,} ₽".replace(",", " ")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        delivered = 0
        for parent_tid in recipients:
            try:
                when = user_timezone.format_day_time_for_user(
                    lesson["start_time"],
                    int(parent_tid),
                    runtime.TIMEZONE_NAME,
                    with_zone=True,
                )
            except Exception:
                when = runtime.format_datetime(lesson["start_time"])

            text = (
                "💳 Небольшое напоминание об оплате 💜\n\n"
                f"👤 Ученик: {user['name']}\n"
                f"📅 {when}\n"
                f"💰 {amount}\n\n"
                f"{names.get(str(reminder_type), '')}\n\n"
                "Пожалуйста, подтвердите оплату не позднее чем за 2 часа до занятия. "
                "Иначе слот будет автоматически освобождён."
            )
            try:
                await context.bot.send_message(
                    chat_id=int(parent_tid),
                    text=text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            "👤 Открыть кабинет ученика",
                            callback_data=f"parent_child|{int(user['id'])}",
                        )]
                    ]),
                )
                delivered += 1
            except Exception as exc:
                print("PARENT PAYMENT REMINDER ERROR:", user["id"], parent_tid, repr(exc), flush=True)

        # Parent linkage is authoritative: never fall back to the student here.
        # Mark only after at least one parent received the reminder.
        if delivered:
            database.mark_reminder_sent(int(lesson_id), str(reminder_type))

    payment_reminder_job._adelia_parent_payment_routing = True
    payment_reminder_job._adelia_original = original
    runtime.payment_reminder_job = payment_reminder_job
    _INSTALLED = True
