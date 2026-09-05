from __future__ import annotations

from datetime import timedelta

import database
from core.lesson_time import actual_datetime, actual_storage_iso, schedule_datetime
from vk_adapter import channel_delivery


def context(lesson_id: int):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        raise ValueError("Занятие не найдено.")
    plan_start = schedule_datetime(lesson["start_time"])
    plan_end = schedule_datetime(lesson["end_time"])
    actual_start = actual_datetime(lesson["started_at"]) if lesson["started_at"] else None
    duration = int(lesson["duration_minutes"] or round((plan_end-plan_start).total_seconds()/60))
    actual_end = actual_start + timedelta(minutes=duration) if actual_start else None
    delta = round((actual_start-plan_start).total_seconds()/60) if actual_start else 0
    return {
        "lesson": lesson,
        "plan_start": plan_start,
        "plan_end": plan_end,
        "actual_start": actual_start,
        "duration": duration,
        "actual_end": actual_end,
        "late": max(delta, 0),
        "early": max(-delta, 0),
    }


def next_lesson(lesson_id: int):
    info = context(lesson_id)
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT l.id,l.user_id,l.start_time,l.end_time,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.id<>? AND l.cancelled_at IS NULL
              AND l.lesson_status IN ('CONFIRMED','IN_PROGRESS')
            ORDER BY l.start_time
        """, (int(lesson_id),)).fetchall()
    finally:
        c.close()
    for row in rows:
        try:
            start = schedule_datetime(row["start_time"])
        except Exception:
            continue
        if start >= info["plan_end"]:
            return row, start
    return None, None


def conflict_delay(lesson_id: int):
    info = context(lesson_id)
    row, start = next_lesson(lesson_id)
    if not row or not info["actual_end"]:
        return row, 0
    return row, max(round((info["actual_end"]-start).total_seconds()/60), 0)


def finish_now(lesson_id: int):
    return database.finish_lesson(int(lesson_id))


def finish_at_plan(lesson_id: int):
    info = context(lesson_id)
    return database.finish_lesson(int(lesson_id), finished_at=actual_storage_iso(info["plan_end"]))


def finish_preview(lesson_id: int):
    info = context(lesson_id)
    if not info["actual_start"]:
        raise ValueError("Занятие ещё не начато.")
    actual_at_plan = max(round((info["plan_end"]-info["actual_start"]).total_seconds()/60), 0)
    missing = max(info["duration"]-actual_at_plan, 0)
    return info, actual_at_plan, missing


def warning_text(lesson_id: int, delay_minutes: int):
    row, start = next_lesson(lesson_id)
    if not row or not start:
        raise ValueError("Следующее занятие не найдено.")
    delay = max(int(delay_minutes), 1)
    expected = start + timedelta(minutes=delay)
    return row, (
        "⏳ Немного задерживаюсь.\n\n"
        f"Планировали начать в {start:%H:%M}, ориентировочно начнём в {expected:%H:%M}.\n"
        f"Задержка примерно {delay} минут 💜"
    )


def warn_next_student(lesson_id: int, delay_minutes: int):
    row, text = warning_text(lesson_id, delay_minutes)
    delivered = channel_delivery.send_student(int(row["user_id"]), text)
    c = database.connect()
    try:
        c.execute(
            "UPDATE lessons SET tutor_delay_minutes=?,tutor_delay_notified_at=? WHERE id=?",
            (max(int(delay_minutes), 1), database.now_iso(), int(lesson_id)),
        )
        c.commit()
    finally:
        c.close()
    return row, text, delivered
