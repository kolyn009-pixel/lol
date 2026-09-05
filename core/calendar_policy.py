from __future__ import annotations

from datetime import datetime, timedelta

import database
from core.lesson_time import schedule_datetime, lesson_timezone

# Google Calendar event color ids.
# 11 = tomato/red, 8 = graphite, 10 = basil/green.
COLOR_PAYMENT_OVERDUE = "11"
COLOR_PAYMENT_URGENT = "11"
COLOR_COMPLETED = "10"
COLOR_DAY_OFF = "8"

DELETE_STATUSES = {
    "CANCELLED",
    "REJECTED",
    "UNPAID_CANCELLED",
    "TRANSFERRED",
}

KEEP_STATUSES = {
    "CONFIRMED",
    "IN_PROGRESS",
    "COMPLETED",
    "NO_SHOW",
    "LATE_CANCELLED",
    "SICKNESS",
}


def should_keep_lesson_event(lesson) -> bool:
    """Completed lessons stay in Calendar; only cancelled/moved rows disappear."""
    status = str(lesson["lesson_status"] or "").upper()
    payment_status = str(lesson["payment_status"] or "").upper()
    if status in DELETE_STATUSES or payment_status == "TRANSFERRED":
        return False
    return status in KEEP_STATUSES or bool(lesson["finished_at"])


def should_delete_lesson_event(lesson) -> bool:
    return not should_keep_lesson_event(lesson)


def _latest_waiting_receipt_created_at(user_id: int):
    c = database.connect()
    try:
        row = c.execute(
            """
            SELECT r.created_at
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            WHERE r.user_id=?
              AND r.status='WAITING'
              AND p.status='RECEIPT_SENT'
            ORDER BY r.created_at DESC,r.id DESC
            LIMIT 1
            """,
            (int(user_id),),
        ).fetchone()
        return row["created_at"] if row else None
    except Exception:
        return None
    finally:
        c.close()


def payment_confirmation_overdue(lesson, now=None) -> bool:
    """Red after a receipt has waited for teacher confirmation for 24h."""
    raw = _latest_waiting_receipt_created_at(int(lesson["user_id"]))
    if not raw:
        return False
    try:
        sent = datetime.fromisoformat(str(raw))
        current = now or datetime.now()
        if sent.tzinfo and not current.tzinfo:
            current = current.replace(tzinfo=sent.tzinfo)
        elif current.tzinfo and not sent.tzinfo:
            sent = sent.replace(tzinfo=current.tzinfo)
        return current - sent >= timedelta(hours=24)
    except Exception:
        return False


def payment_due_within_24h(lesson, now=None) -> bool:
    """Urgent red state when payment is still missing and lesson is <=24h away."""
    if str(lesson["lesson_status"] or "").upper() != "CONFIRMED":
        return False
    if str(lesson["payment_status"] or "").upper() not in {
        "AWAITING_PAYMENT",
        "UNPAID",
    }:
        return False
    try:
        start = schedule_datetime(lesson["start_time"])
        current = now or datetime.now(lesson_timezone())
        if current.tzinfo is None:
            current = current.replace(tzinfo=lesson_timezone())
        else:
            current = current.astimezone(lesson_timezone())
        seconds = (start - current).total_seconds()
        return 0 <= seconds <= 24 * 60 * 60
    except Exception:
        return False


def payment_attention_reason(lesson, now=None):
    """Return the strongest teacher-facing payment warning for Calendar."""
    if payment_confirmation_overdue(lesson, now=now):
        return "RECEIPT_UNCONFIRMED_24H"
    if payment_due_within_24h(lesson, now=now):
        return "PAYMENT_DUE_24H"
    return None


def lesson_color_id(lesson, now=None):
    reason = payment_attention_reason(lesson, now=now)
    if reason:
        return COLOR_PAYMENT_OVERDUE
    if str(lesson["lesson_status"] or "").upper() == "COMPLETED" or lesson["finished_at"]:
        return COLOR_COMPLETED
    return None


def lesson_summary_prefix(lesson, now=None):
    reason = payment_attention_reason(lesson, now=now)
    if reason == "RECEIPT_UNCONFIRMED_24H":
        return "🔴 ЧЕК >24Ч БЕЗ ПОДТВЕРЖДЕНИЯ • "
    if reason == "PAYMENT_DUE_24H":
        return "🔴 ДО ЗАНЯТИЯ <24Ч • НЕТ ОПЛАТЫ • "
    if str(lesson["lesson_status"] or "").upper() == "COMPLETED" or lesson["finished_at"]:
        return "✅ "
    return ""


def lesson_payment_note(lesson, now=None):
    reason = payment_attention_reason(lesson, now=now)
    if reason == "RECEIPT_UNCONFIRMED_24H":
        return (
            "🔴 ВНИМАНИЕ: ученик уже прислал чек, но оплата не подтверждена "
            "преподавателем больше 24 часов."
        )
    if reason == "PAYMENT_DUE_24H":
        return (
            "🔴 ВНИМАНИЕ: до занятия осталось меньше 24 часов, а оплата/чек "
            "ещё не получены. Проверьте, нужно ли напомнить ученику."
        )
    return ""


def closed_dates():
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT id,date,comment,created_at
            FROM schedule_exceptions
            WHERE exception_type='CLOSED'
            ORDER BY date,id
            """
        ).fetchall())
    finally:
        c.close()


def day_off_event_key(exception_id: int) -> str:
    return f"tutorbot-day-off-{int(exception_id)}"


def day_off_summary(row) -> str:
    comment = str(row["comment"] or "").strip()
    return "🚫 ВЫХОДНОЙ" + (f" • {comment}" if comment else "")


def day_off_event_body(row):
    """Google Calendar all-day body for an explicit CLOSED date."""
    day = datetime.fromisoformat(str(row["date"])).date()
    return {
        "summary": day_off_summary(row),
        "description": (
            "Выходной / исключение TutorBot.\n"
            f"Exception #{row['id']}"
        ),
        "start": {"date": day.isoformat()},
        "end": {"date": (day + timedelta(days=1)).isoformat()},
        "colorId": COLOR_DAY_OFF,
        "transparency": "opaque",
        "extendedProperties": {
            "private": {
                "tutorbot_type": "DAY_OFF",
                "tutorbot_exception_id": str(row["id"]),
            }
        },
    }
