"""Finalize the web post-lesson workflow after canonical TutorBot finish/review.

This module never recalculates money or minutes. Those remain owned by
`database.finish_lesson`. It only verifies that the teacher finished the review
and made an explicit homework decision, marks the web workflow complete and
queues one idempotent summary message for the student.
"""
from __future__ import annotations

from database import connect, get_lesson, get_user, now_iso
from core import post_lesson
from web_backend.unified_messages import queue_teacher_reply


def _summary(lesson, user, homework_status, review_summary):
    actual = int(lesson["actual_duration_minutes"] or lesson["duration_minutes"] or 0)
    extra = int(lesson["extra_minutes"] or 0)
    under = int(lesson["underworked_minutes"] or 0)
    lines = [
        "✅ Занятие завершено",
        "",
        f"⏱ Фактически: {actual} мин.",
    ]
    if extra > 0:
        lines.append(f"➕ Дополнительное время: {extra} мин.")
    if under > 0:
        lines.append(f"⏳ Недоработка: {under} мин. учтена системой.")
    topics = list((review_summary or {}).get("topics") or [])
    if topics:
        lines += ["", "📈 Прогресс сохранён:", " · ".join(str(x) for x in topics[:5])]
    if str(homework_status).upper() == "ASSIGNED":
        lines += ["", "📚 Домашнее задание уже появилось в Аделии."]
    elif str(homework_status).upper() == "SKIPPED":
        lines += ["", "📚 На этот раз без домашнего задания."]
    return "\n".join(lines)


def state(lesson_id):
    lesson = get_lesson(int(lesson_id))
    if not lesson:
        return None
    sync = post_lesson.sync_row(int(lesson_id))
    homework_status = str(sync["homework_status"] if sync else "PENDING").upper()
    reviewed = bool(post_lesson.review_completed(int(lesson_id)))
    finished = bool(lesson["finished_at"])
    ready = finished and reviewed and homework_status in {"ASSIGNED", "SKIPPED"}
    return {
        "ready": ready,
        "finished": finished,
        "review_completed": reviewed,
        "homework_status": homework_status,
        "homework_id": int(sync["homework_id"]) if sync and sync["homework_id"] else None,
        "actual_duration_minutes": int(lesson["actual_duration_minutes"] or lesson["duration_minutes"] or 0),
        "extra_minutes": int(lesson["extra_minutes"] or 0),
        "underworked_minutes": int(lesson["underworked_minutes"] or 0),
        "payment_status": lesson["payment_status"],
        "price": int(lesson["price"] or 0),
        "review_summary": post_lesson.review_summary(int(lesson_id)),
    }


def complete(lesson_id):
    lesson_id = int(lesson_id)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return {"status": "lesson_not_found"}
    current = state(lesson_id)
    if not current["finished"]:
        return {"status": "lesson_not_finished"}
    if not current["review_completed"]:
        return {"status": "review_required"}
    if current["homework_status"] not in {"ASSIGNED", "SKIPPED"}:
        return {"status": "homework_decision_required"}

    user_id = int(lesson["user_id"])
    user = get_user(user_id)
    event_key = f"web:post_lesson_complete:{lesson_id}"
    first = post_lesson.claim(event_key)

    conn = connect()
    conn.execute(
        "UPDATE lessons SET post_lesson_reviewed=1,updated_at=? WHERE id=?",
        (now_iso(), lesson_id),
    )
    conn.commit(); conn.close()

    if first:
        text = _summary(lesson, user, current["homework_status"], current["review_summary"])
        queue_teacher_reply(user_id, text)

    current = state(lesson_id)
    return {"status": "ok", "notification_queued": bool(first), **current}
