"""Durable lesson markers for teacher-created schedule exceptions.

Markers intentionally survive deletion of the schedule exception so students keep
the penalty-free cancel/reschedule rights they were already given.
"""
from __future__ import annotations

import database


def ensure_schema():
    conn=database.connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS teacher_day_off_lessons (
                lesson_id INTEGER PRIMARY KEY,
                exception_id INTEGER,
                marked_at TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT 'TEACHER_DAY_OFF'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_teacher_day_off_exception ON teacher_day_off_lessons(exception_id)")
        conn.commit()
    finally:
        conn.close()


def mark_lessons(exception_id,lesson_ids):
    ensure_schema();now=database.now_iso();ids=sorted({int(x) for x in lesson_ids});exception_id=int(exception_id) if exception_id is not None else None
    if not ids:return 0
    conn=database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        for lesson_id in ids:
            conn.execute("""
                INSERT INTO teacher_day_off_lessons(lesson_id,exception_id,marked_at,reason)
                VALUES(?,?,?,'TEACHER_DAY_OFF')
                ON CONFLICT(lesson_id) DO UPDATE SET
                    exception_id=COALESCE(excluded.exception_id,teacher_day_off_lessons.exception_id),
                    marked_at=excluded.marked_at,
                    reason=excluded.reason
            """,(lesson_id,exception_id,now))
        conn.commit();return len(ids)
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()


def mark_lesson(lesson_id,exception_id=None):
    return mark_lessons(exception_id,[lesson_id])


def is_marked(lesson_id):
    ensure_schema();conn=database.connect()
    try:
        row=conn.execute("SELECT 1 FROM teacher_day_off_lessons WHERE lesson_id=? LIMIT 1",(int(lesson_id),)).fetchone()
        return bool(row)
    finally:
        conn.close()
