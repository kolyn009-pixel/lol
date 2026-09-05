from __future__ import annotations

from datetime import datetime, timedelta

import database

# Google Calendar event color ids.
# 11 = tomato/red, 8 = graphite, 10 = basil/green.
COLOR_PAYMENT_OVERDUE = "11"
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


def lesson_color_id(lesson, now=None):
    if payment_confirmation_overdue(lesson, now=now):
        return COLOR_PAYMENT_OVERDUE
    if str(lesson["lesson_status"] or "").upper() == "COMPLETED" or lesson["finished_at"]:
        return COLOR_COMPLETED
    return None


def lesson_summary_prefix(lesson):
    if payment_confirmation_overdue(lesson):
        return "🔴 ОПЛАТА НЕ ПОДТВЕРЖДЕНА • "
    if str(lesson["lesson_status"] or "").upper() == "COMPLETED" or lesson["finished_at"]:
        return "✅ "
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
