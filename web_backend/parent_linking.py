"""Parent/student linking helpers for the web portal.

This module reuses TutorBot's existing SQLite schema. It deliberately returns
only the minimum student identity needed before a link is confirmed.
"""

from database import connect, normalize_username, now_iso


def find_student_by_username(username):
    normalized = normalize_username(username)
    if not normalized:
        return None

    conn = connect()
    row = conn.execute(
        """
        SELECT id, name, telegram_username, grade
        FROM users
        WHERE active = 1
          AND lower(trim(telegram_username)) = ?
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    conn.close()
    return row


def link_parent_to_student_by_username(parent_id, username, max_parents=2):
    student = find_student_by_username(username)
    if not student:
        return {"status": "not_found", "student": None}

    student_id = int(student["id"])
    parent_id = int(parent_id)
    conn = connect()

    existing = conn.execute(
        "SELECT 1 FROM parent_student_links WHERE parent_id = ? AND student_id = ?",
        (parent_id, student_id),
    ).fetchone()
    if existing:
        conn.close()
        return {"status": "already_linked", "student": student}

    count = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM parent_student_links l
        JOIN parent_accounts p ON p.id = l.parent_id
        WHERE l.student_id = ? AND p.active = 1
        """,
        (student_id,),
    ).fetchone()["cnt"]

    if int(count or 0) >= int(max_parents):
        conn.close()
        return {"status": "limit_reached", "student": student}

    conn.execute(
        """
        INSERT INTO parent_student_links
            (parent_id, student_id, notify_schedule, created_at)
        VALUES (?, ?, 1, ?)
        """,
        (parent_id, student_id, now_iso()),
    )
    conn.commit()
    conn.close()
    return {"status": "linked", "student": student}
