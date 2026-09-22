"""Teacher-created individual lesson booking using canonical TutorBot lesson lifecycle."""
from __future__ import annotations

from datetime import datetime, timedelta

import database
from integrations.lesson_sync import sync_lesson
from web_backend import push_events


_ALLOWED_PAYMENT_MODES = {"AWAITING_PAYMENT", "BALANCE", "FREE"}


def _student(user_id: int):
    user = database.get_user(int(user_id))
    if not user:
        raise ValueError("student_not_found")
    return user


def create(user_id, start_time, duration_minutes=60, payment_mode="AWAITING_PAYMENT"):
    uid = int(user_id)
    user = _student(uid)

    study_goal = str(user["study_goal"] or "SCHOOL").upper()
    subject = str(user["main_subject"] or "PHYSICS").upper()

    try:
        start = datetime.fromisoformat(str(start_time or "").strip())
    except Exception as exc:
        raise ValueError("invalid_start_time") from exc

    now = datetime.now()
    if start < now - timedelta(minutes=5):
        raise ValueError("start_time_in_past")

    duration = int(duration_minutes or 60)
    if duration < 30 or duration > 240:
        raise ValueError("invalid_duration")

    mode = str(payment_mode or "AWAITING_PAYMENT").upper()
    if mode not in _ALLOWED_PAYMENT_MODES:
        raise ValueError("invalid_payment_mode")

    rate = int(database.get_student_rate(uid, study_goal, subject))
    price = int(database.calculate_lesson_price(rate, duration))
    end = start + timedelta(minutes=duration)

    lesson_id = int(database.create_admin_lesson(
        uid,
        study_goal,
        subject,
        start.isoformat(timespec="seconds"),
        end.isoformat(timespec="seconds"),
        duration,
        rate,
        price,
        payment_mode=mode,
        is_trial=False,
    ))

    try:
        integrations = sync_lesson(lesson_id)
    except Exception as exc:
        integrations = {
            "google": {"status": "error", "error": type(exc).__name__},
            "telemost": {"status": "error", "error": type(exc).__name__},
        }

    payment_text = {
        "AWAITING_PAYMENT": "Оплата ожидается до занятия.",
        "BALANCE": "Минуты будут списаны из баланса по правилам TutorBot.",
        "FREE": "Занятие отмечено как бесплатное.",
    }[mode]
    when = start.strftime("%d.%m в %H:%M")
    delivery = push_events.student_and_parents(
        uid,
        "🗓️ Новое занятие в расписании",
        f"Преподаватель записал занятие на {when}. {payment_text}",
        f"/app/lesson/?id={lesson_id}",
        "/app/parent/",
        f"teacher-manual-booking-{lesson_id}",
        {"type": "schedule", "lesson_id": lesson_id, "reason": "teacher_manual_booking"},
        mirror_messengers=True,
    )

    lesson = database.get_lesson(lesson_id)
    return {
        "status": "ok",
        "lesson_id": lesson_id,
        "lesson": dict(lesson) if lesson else None,
        "hourly_rate": rate,
        "price": price,
        "payment_mode": mode,
        "integrations": integrations,
        "delivery": delivery,
    }
