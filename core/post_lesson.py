from __future__ import annotations

import json
from datetime import datetime

import database
from final_features import progress_quick
from formula_library import FORMULA_LIBRARY


LEVEL_LABELS = {
    "STARTED": "⚪ Только начали",
    "NEEDS_WORK": "🔴 Есть сложности",
    "GOOD": "🟡 Нужно закрепить",
    "MASTERED": "🟢 Усвоено",
}


def _columns(c, table: str) -> set[str]:
    return {str(r["name"]) for r in c.execute(f"PRAGMA table_info({table})").fetchall()}


def initialize():
    c = database.connect()
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS post_lesson_review_sync (
                lesson_id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                started_channel TEXT,
                completed_channel TEXT,
                homework_status TEXT NOT NULL DEFAULT 'PENDING',
                homework_id INTEGER,
                selected_json TEXT NOT NULL DEFAULT '[]',
                selected_at TEXT,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS unified_lesson_event_log (
                event_key TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            """
        )
        cols = _columns(c, "post_lesson_review_sync")
        if "selected_json" not in cols:
            c.execute("ALTER TABLE post_lesson_review_sync ADD COLUMN selected_json TEXT NOT NULL DEFAULT '[]'")
        if "selected_at" not in cols:
            c.execute("ALTER TABLE post_lesson_review_sync ADD COLUMN selected_at TEXT")
        c.execute("UPDATE post_lesson_review_sync SET selected_json='[]' WHERE selected_json IS NULL OR selected_json='' ")
        c.commit()
    finally:
        c.close()


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def claim(event_key: str) -> bool:
    initialize()
    c = database.connect()
    try:
        cur = c.execute(
            "INSERT OR IGNORE INTO unified_lesson_event_log(event_key,created_at) VALUES(?,?)",
            (str(event_key), now_iso()),
        )
        c.commit()
        return cur.rowcount > 0
    finally:
        c.close()


def ensure_sync(lesson_id: int, user_id: int, channel: str | None = None):
    initialize()
    lesson_id = int(lesson_id)
    user_id = int(user_id)
    channel = (str(channel).upper() if channel else None)
    c = database.connect()
    try:
        c.execute(
            """
            INSERT INTO post_lesson_review_sync(
                lesson_id,user_id,status,started_channel,updated_at
            ) VALUES(?,?,'OPEN',?,?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                user_id=excluded.user_id,
                started_channel=COALESCE(post_lesson_review_sync.started_channel,excluded.started_channel),
                updated_at=excluded.updated_at
            """,
            (lesson_id, user_id, channel, now_iso()),
        )
        c.commit()
    finally:
        c.close()


def sync_row(lesson_id: int):
    initialize()
    c = database.connect()
    try:
        return c.execute(
            "SELECT * FROM post_lesson_review_sync WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
    finally:
        c.close()


def _normalize_marks(marks):
    result = []
    for item in marks or []:
        try:
            topic_id, level, comment = item
            result.append((int(topic_id), str(level), comment if comment is None else str(comment)))
        except Exception:
            continue
    return result


def draft_marks(lesson_id: int):
    row = sync_row(int(lesson_id))
    if not row:
        return []
    try:
        raw = json.loads(row["selected_json"] or "[]")
    except Exception:
        return []
    return _normalize_marks(raw)


def save_draft_marks(lesson_id: int, user_id: int, marks, channel: str | None = None):
    ensure_sync(int(lesson_id), int(user_id), channel)
    normalized = _normalize_marks(marks)
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE post_lesson_review_sync
            SET selected_json=?,selected_at=?,updated_at=?
            WHERE lesson_id=?
            """,
            (
                json.dumps(normalized, ensure_ascii=False),
                now_iso(),
                now_iso(),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()
    return normalized


def clear_draft_marks(lesson_id: int):
    initialize()
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE post_lesson_review_sync
            SET selected_json='[]',selected_at=NULL,updated_at=?
            WHERE lesson_id=?
            """,
            (now_iso(), int(lesson_id)),
        )
        c.commit()
    finally:
        c.close()


def review_completed(lesson_id: int) -> bool:
    c = database.connect()
    try:
        row = c.execute(
            "SELECT COALESCE(post_lesson_reviewed,0) AS done FROM lessons WHERE id=?",
            (int(lesson_id),),
        ).fetchone()
        if row and int(row["done"] or 0):
            return True
        return bool(
            c.execute(
                "SELECT 1 FROM post_lesson_reviews WHERE lesson_id=? LIMIT 1",
                (int(lesson_id),),
            ).fetchone()
        )
    finally:
        c.close()


def mark_completed(
    lesson_id: int,
    user_id: int,
    channel: str,
    homework_status: str = "PENDING",
    homework_id: int | None = None,
):
    ensure_sync(lesson_id, user_id, channel)
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE post_lesson_review_sync
            SET status='COMPLETED',
                completed_channel=?,
                homework_status=?,
                homework_id=?,
                selected_json='[]',
                selected_at=NULL,
                updated_at=?
            WHERE lesson_id=?
            """,
            (
                str(channel).upper(),
                str(homework_status).upper(),
                int(homework_id) if homework_id else None,
                now_iso(),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()


def set_homework_status(lesson_id: int, status: str, homework_id: int | None = None):
    initialize()
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE post_lesson_review_sync
            SET homework_status=?,homework_id=?,updated_at=?
            WHERE lesson_id=?
            """,
            (
                str(status).upper(),
                int(homework_id) if homework_id else None,
                now_iso(),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()


def topics_for_student(user_id: int, lesson_id: int):
    return list(progress_quick.topics_for_student(int(user_id), int(lesson_id)))


def sections_for_student(user_id: int, lesson_id: int):
    sections = []
    for row in topics_for_student(user_id, lesson_id):
        key = (str(row["subject"]), str(row["section"]))
        if key not in sections:
            sections.append(key)
    return sections


def topics_for_section(user_id: int, lesson_id: int, subject: str, section: str):
    return [
        r
        for r in topics_for_student(user_id, lesson_id)
        if str(r["subject"]) == str(subject) and str(r["section"]) == str(section)
    ]


def topic_row(topic_id: int):
    c = database.connect()
    try:
        return c.execute(
            "SELECT id,subject,study_goal,grade,section,topic FROM learning_topics WHERE id=?",
            (int(topic_id),),
        ).fetchone()
    finally:
        c.close()


def upsert_mark(marks, topic_id: int, level: str, comment=None):
    result = [x for x in (marks or []) if int(x[0]) != int(topic_id)]
    result.append((int(topic_id), str(level), comment))
    return result


def mark_lines(marks):
    lines = []
    for topic_id, level, _comment in marks or []:
        row = topic_row(topic_id)
        title = row["topic"] if row else f"Тема #{topic_id}"
        icon = LEVEL_LABELS.get(str(level), "•").split(" ", 1)[0]
        lines.append(f"{icon} {title}")
    return lines


def save_review(lesson_id: int, user_id: int, marks, actor=None, channel="TG"):
    review_id = progress_quick.save_review(
        int(lesson_id),
        int(user_id),
        list(marks or []),
        actor=actor,
    )
    mark_completed(lesson_id, user_id, channel, homework_status="PENDING")
    try:
        c = database.connect()
        c.execute(
            "UPDATE smart_actions SET status='DONE',resolved_at=? WHERE action_type='POST_LESSON_REVIEW' AND source_type='lesson' AND source_id=? AND status='OPEN'",
            (now_iso(), int(lesson_id)),
        )
        c.commit()
        c.close()
    except Exception:
        pass
    return review_id


def _subject_code(value):
    raw = str(value or "").strip().upper()
    if raw in {"ФИЗИКА", "PHYSICS"}:
        return "PHYSICS"
    if raw in {"ХИМИЯ", "CHEMISTRY"}:
        return "CHEMISTRY"
    return raw


def formula_mapping_for_marks(marks):
    mapped = []
    for topic_id, _level, _comment in marks or []:
        row = topic_row(topic_id)
        if not row:
            continue
        try:
            grade = int(row["grade"])
        except Exception:
            continue
        subject = _subject_code(row["subject"])
        library = FORMULA_LIBRARY.get(grade, {}).get(subject, {})
        wanted = str(row["topic"] or "").strip().casefold()
        found = None
        for key, item in library.items():
            title = str((item or {}).get("title") or key).strip()
            if str(key).strip().casefold() == wanted or title.casefold() == wanted:
                found = str(key)
                break
        if found:
            mapped.append((grade, subject, found))
    return mapped


def prepare_homework_draft(admin_telegram_id: int, lesson_id: int, user_id: int, marks):
    from learning import homework_flow

    did = homework_flow._new_draft(
        int(admin_telegram_id),
        int(user_id),
        int(lesson_id),
    )
    mapped = formula_mapping_for_marks(marks)
    if mapped:
        grade, subject, topic = mapped[0]
        repeats = [f"{g}|{s}|{t}" for g, s, t in mapped[1:]]
        homework_flow._touch(
            did,
            topic_grade=grade,
            topic_subject=subject,
            topic_key=topic,
            repeat_topics_json=json.dumps(repeats, ensure_ascii=False),
            formula_topics_json="[]",
            formula_decision=None,
        )
    set_homework_status(lesson_id, "DRAFT")
    return did


def link_homework_topics(homework_id: int, marks):
    mapped = formula_mapping_for_marks(marks)
    if not mapped:
        return 0
    c = database.connect()
    try:
        count = 0
        for i, (grade, subject, topic) in enumerate(mapped):
            c.execute(
                """
                INSERT INTO homework_topic_links(homework_id,grade,subject,topic,role)
                VALUES(?,?,?,?,?)
                """,
                (int(homework_id), int(grade), str(subject), str(topic), "MAIN" if i == 0 else "REVIEW"),
            )
            count += 1
        c.commit()
        return count
    finally:
        c.close()


def review_summary(lesson_id: int):
    c = database.connect()
    try:
        review = c.execute(
            "SELECT id,user_id FROM post_lesson_reviews WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
        if not review:
            return {"count": 0, "topics": []}
        rows = c.execute(
            """
            SELECT m.topic_id,m.level,m.comment,t.topic
            FROM post_lesson_topic_marks m
            LEFT JOIN learning_topics t ON t.id=m.topic_id
            WHERE m.review_id=?
            ORDER BY m.id
            """,
            (int(review["id"]),),
        ).fetchall()
        return {
            "count": len(rows),
            "topics": [r["topic"] or f"Тема #{r['topic_id']}" for r in rows],
        }
    finally:
        c.close()
