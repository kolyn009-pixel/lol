"""Web facade over TutorBot's canonical post-lesson review flow.

This module intentionally delegates topic/progress persistence to core.post_lesson
from the live TutorBot code. The website is only another channel (WEB), not a
parallel review system.
"""
from database import connect, get_lesson, get_user, skip_homework_for_lesson
from core import post_lesson

LEVELS = ("STARTED", "NEEDS_WORK", "GOOD", "MASTERED")


def _dict(row):
    return dict(row) if row else None


def state(lesson_id):
    lesson_id = int(lesson_id)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return None
    user = get_user(int(lesson["user_id"]))
    post_lesson.ensure_sync(lesson_id, int(lesson["user_id"]), "WEB")
    topics = [dict(r) for r in post_lesson.topics_for_student(int(lesson["user_id"]), lesson_id)]
    draft = {int(topic_id): {"level": level, "comment": comment} for topic_id, level, comment in post_lesson.draft_marks(lesson_id)}
    summary = post_lesson.review_summary(lesson_id)
    sync = post_lesson.sync_row(lesson_id)
    return {
        "lesson": _dict(lesson),
        "student": _dict(user),
        "topics": topics,
        "draft": draft,
        "review_completed": bool(post_lesson.review_completed(lesson_id)),
        "review_summary": summary,
        "homework_status": str(sync["homework_status"] if sync else "PENDING"),
        "homework_id": int(sync["homework_id"]) if sync and sync["homework_id"] else None,
        "levels": list(LEVELS),
    }


def save_marks(lesson_id, marks):
    lesson_id = int(lesson_id)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return {"status": "lesson_not_found"}
    normalized = []
    for item in marks or []:
        try:
            topic_id = int(item.get("topic_id"))
            level = str(item.get("level") or "").upper()
            comment = str(item.get("comment") or "").strip() or None
        except Exception:
            continue
        if level not in LEVELS:
            continue
        normalized.append((topic_id, level, comment))
    post_lesson.save_draft_marks(lesson_id, int(lesson["user_id"]), normalized, channel="WEB")
    return {"status": "ok", "count": len(normalized)}


def complete_review(lesson_id, marks, actor="WEB_TEACHER"):
    lesson_id = int(lesson_id)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return {"status": "lesson_not_found"}
    saved = save_marks(lesson_id, marks)
    if saved["status"] != "ok":
        return saved
    normalized = post_lesson.draft_marks(lesson_id)
    if not normalized:
        return {"status": "marks_required"}
    review_id = post_lesson.save_review(
        lesson_id,
        int(lesson["user_id"]),
        normalized,
        actor=actor,
        channel="WEB",
    )
    return {"status": "ok", "review_id": int(review_id), "count": len(normalized)}


def skip_homework(lesson_id):
    lesson_id = int(lesson_id)
    lesson = get_lesson(lesson_id)
    if not lesson:
        return {"status": "lesson_not_found"}
    skip_homework_for_lesson(lesson_id)
    post_lesson.set_homework_status(lesson_id, "SKIPPED")
    return {"status": "ok", "homework_status": "SKIPPED"}


def link_created_homework(lesson_id, homework_id):
    lesson_id = int(lesson_id)
    homework_id = int(homework_id)
    conn = connect()
    conn.execute(
        "UPDATE lessons SET homework_required=1,homework_assigned=1,homework_skipped=0,updated_at=datetime('now') WHERE id=?",
        (lesson_id,),
    )
    conn.commit(); conn.close()
    post_lesson.set_homework_status(lesson_id, "ASSIGNED", homework_id=homework_id)
    try:
        marks = post_lesson.draft_marks(lesson_id)
        if marks:
            post_lesson.link_homework_topics(homework_id, marks)
    except Exception:
        pass
    return {"status": "ok", "homework_id": homework_id}
