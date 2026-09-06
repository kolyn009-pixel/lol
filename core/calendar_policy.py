from __future__ import annotations

from datetime import datetime, timedelta

import database
from core.lesson_time import schedule_datetime, lesson_timezone

# Google Calendar event color ids:
# 3 grape/purple, 5 banana/yellow, 6 tangerine/orange,
# 8 graphite, 9 blueberry/blue, 10 basil/green, 11 tomato/red.
COLOR_IN_PROGRESS = "3"
COLOR_RECEIPT_WAITING = "5"
COLOR_TRIAL = "6"
COLOR_DAY_OFF = "8"
COLOR_PAID = "9"
COLOR_COMPLETED = "10"
COLOR_ATTENTION = "11"

DELETE_STATUSES = {
    "CANCELLED",
    "REJECTED",
    "UNPAID_CANCELLED",
    "TRANSFERRED",
}

KEEP_STATUSES = {
    "PENDING",
    "CONFIRMED",
    "IN_PROGRESS",
    "COMPLETED",
    "NO_SHOW",
    "LATE_CANCELLED",
    "SICKNESS",
}


def _get(row, key, default=None):
    try:
        return row[key]
    except Exception:
        return default


def is_trial(lesson) -> bool:
    return bool(_get(lesson, "is_trial", 0))


def should_keep_lesson_event(lesson) -> bool:
    """Keep history; remove only rows that are truly cancelled/moved."""
    status = str(_get(lesson, "lesson_status", "") or "").upper()
    payment_status = str(_get(lesson, "payment_status", "") or "").upper()
    if status in DELETE_STATUSES or payment_status == "TRANSFERRED":
        return False
    return status in KEEP_STATUSES or bool(_get(lesson, "finished_at"))


def should_delete_lesson_event(lesson) -> bool:
    return not should_keep_lesson_event(lesson)


def _waiting_receipt_for_lesson(lesson):
    """Return a waiting receipt only when it belongs to this exact lesson.

    Package/general receipts are intentionally not projected onto every future
    lesson, because that would paint unrelated lessons yellow/red.
    """
    lesson_id = int(_get(lesson, "id", 0) or 0)
    if not lesson_id:
        return None
    c = database.connect()
    try:
        return c.execute(
            """
            SELECT r.id,r.created_at,r.source_platform,p.id AS payment_id
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            WHERE p.lesson_id=?
              AND r.status='WAITING'
              AND p.status='RECEIPT_SENT'
            ORDER BY r.created_at DESC,r.id DESC
            LIMIT 1
            """,
            (lesson_id,),
        ).fetchone()
    except Exception:
        return None
    finally:
        c.close()


def receipt_waiting(lesson) -> bool:
    if is_trial(lesson):
        return False
    return _waiting_receipt_for_lesson(lesson) is not None


def payment_confirmation_overdue(lesson, now=None) -> bool:
    """Red after a lesson receipt has waited for teacher confirmation for 24h."""
    if is_trial(lesson):
        return False
    row = _waiting_receipt_for_lesson(lesson)
    if not row:
        return False
    try:
        sent = datetime.fromisoformat(str(row["created_at"]))
        current = now or datetime.now()
        if sent.tzinfo and not current.tzinfo:
            current = current.replace(tzinfo=sent.tzinfo)
        elif current.tzinfo and not sent.tzinfo:
            sent = sent.replace(tzinfo=current.tzinfo)
        return current - sent >= timedelta(hours=24)
    except Exception:
        return False


def payment_due_within_24h(lesson, now=None) -> bool:
    """Urgent red state when a normal lesson is <=24h away and still unpaid."""
    if is_trial(lesson):
        return False
    if str(_get(lesson, "lesson_status", "") or "").upper() != "CONFIRMED":
        return False
    if str(_get(lesson, "payment_status", "") or "").upper() not in {
        "AWAITING_PAYMENT",
        "UNPAID",
    }:
        return False
    # If a receipt has already arrived, the receipt state takes precedence.
    if receipt_waiting(lesson):
        return False
    try:
        start = schedule_datetime(_get(lesson, "start_time"))
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
    if is_trial(lesson):
        return None
    if payment_confirmation_overdue(lesson, now=now):
        return "RECEIPT_UNCONFIRMED_24H"
    if payment_due_within_24h(lesson, now=now):
        return "PAYMENT_DUE_24H"
    if receipt_waiting(lesson):
        return "RECEIPT_WAITING"
    return None


def lesson_state(lesson, now=None):
    """Canonical Calendar visual state with deliberate priority."""
    status = str(_get(lesson, "lesson_status", "") or "").upper()
    payment_status = str(_get(lesson, "payment_status", "") or "").upper()
    attention = payment_attention_reason(lesson, now=now)

    if attention in {"RECEIPT_UNCONFIRMED_24H", "PAYMENT_DUE_24H"}:
        return "ATTENTION"
    if status == "IN_PROGRESS":
        return "IN_PROGRESS"
    if status == "COMPLETED" or _get(lesson, "finished_at"):
        return "COMPLETED"
    if is_trial(lesson):
        return "TRIAL"
    if attention == "RECEIPT_WAITING":
        return "RECEIPT_WAITING"
    if payment_status in {"PAID", "RESERVED_BALANCE", "FREE"}:
        return "PAID"
    return "PLANNED"


def lesson_color_id(lesson, now=None):
    state = lesson_state(lesson, now=now)
    return {
        "ATTENTION": COLOR_ATTENTION,
        "IN_PROGRESS": COLOR_IN_PROGRESS,
        "COMPLETED": COLOR_COMPLETED,
        "TRIAL": COLOR_TRIAL,
        "RECEIPT_WAITING": COLOR_RECEIPT_WAITING,
        "PAID": COLOR_PAID,
    }.get(state)


def lesson_summary_prefix(lesson, now=None):
    reason = payment_attention_reason(lesson, now=now)
    state = lesson_state(lesson, now=now)
    if reason == "RECEIPT_UNCONFIRMED_24H":
        return "🔴 ЧЕК >24Ч • "
    if reason == "PAYMENT_DUE_24H":
        return "🔴 НЕТ ОПЛАТЫ • "
    if state == "IN_PROGRESS":
        return "🟣 ИДЁТ • "
    if state == "COMPLETED":
        return "✅ "
    if state == "TRIAL":
        return "🧪 ПРОБНОЕ • "
    if state == "RECEIPT_WAITING":
        return "🧾 ЧЕК • "
    if state == "PAID":
        return "💳 "
    return ""


def lesson_payment_note(lesson, now=None):
    reason = payment_attention_reason(lesson, now=now)
    if is_trial(lesson):
        return "🎁 Пробное занятие бесплатное. Оплата и чек не требуются."
    if reason == "RECEIPT_UNCONFIRMED_24H":
        return (
            "🔴 ВНИМАНИЕ: чек по этому занятию получен, но преподаватель "
            "не подтвердил его больше 24 часов."
        )
    if reason == "PAYMENT_DUE_24H":
        return (
            "🔴 ВНИМАНИЕ: до занятия осталось меньше 24 часов, а оплата/чек "
            "ещё не получены. Проверьте, нужно ли напомнить ученику."
        )
    if reason == "RECEIPT_WAITING":
        return "🧾 Чек получен и ждёт проверки преподавателем."
    payment_status = str(_get(lesson, "payment_status", "") or "").upper()
    if payment_status in {"PAID", "RESERVED_BALANCE", "FREE"}:
        return "💳 Оплата: подтверждена / занятие обеспечено балансом."
    return "💳 Оплата: пока не подтверждена."


def lesson_status_note(lesson):
    state = lesson_state(lesson)
    return {
        "ATTENTION": "🔴 Требует внимания",
        "IN_PROGRESS": "🟣 Занятие идёт",
        "COMPLETED": "✅ Занятие проведено",
        "TRIAL": "🧪 Бесплатное пробное занятие",
        "RECEIPT_WAITING": "🧾 Чек ждёт проверки",
        "PAID": "💳 Оплачено",
        "PLANNED": "📅 Запланировано",
    }.get(state, "📅 Запланировано")


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
