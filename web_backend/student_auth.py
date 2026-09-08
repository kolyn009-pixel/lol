"""One-time student login codes for the web portal.

Codes are generated for an existing TutorBot student, expire quickly and are
consumed once. The bot can call issue_student_login_code() and send the code to
the student; the website exchanges it for the student's internal id.
"""

import secrets
from datetime import datetime, timedelta

from database import connect, now_iso, table_exists


CODE_TTL_MINUTES = 10


def ensure_student_web_login_table():
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS student_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_student_web_login_code ON student_web_login_codes(code)"
    )
    conn.commit()
    conn.close()


def _new_code():
    # 6 digits are easy to type on a phone. Security comes from short TTL,
    # one-time use and rate limiting in the HTTP layer.
    return f"{secrets.randbelow(1_000_000):06d}"


def issue_student_login_code(student_id, ttl_minutes=CODE_TTL_MINUTES):
    ensure_student_web_login_table()
    student_id = int(student_id)
    ttl_minutes = max(1, min(int(ttl_minutes), 30))
    expires_at = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")

    conn = connect()
    student = conn.execute(
        "SELECT id FROM users WHERE id = ? AND active = 1",
        (student_id,),
    ).fetchone()
    if not student:
        conn.close()
        raise ValueError("student_not_found")

    conn.execute(
        "UPDATE student_web_login_codes SET used_at = ? WHERE student_id = ? AND used_at IS NULL",
        (now_iso(), student_id),
    )

    while True:
        code = _new_code()
        exists = conn.execute(
            "SELECT 1 FROM student_web_login_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not exists:
            break

    conn.execute(
        """
        INSERT INTO student_web_login_codes(student_id, code, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (student_id, code, expires_at, now_iso()),
    )
    conn.commit()
    conn.close()
    return code


def consume_student_login_code(code):
    ensure_student_web_login_table()
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        return {"status": "invalid", "student": None}

    conn = connect()
    row = conn.execute(
        """
        SELECT c.id AS code_id, c.expires_at, c.used_at,
               u.id, u.name, u.telegram_username, u.grade
        FROM student_web_login_codes c
        JOIN users u ON u.id = c.student_id
        WHERE c.code = ? AND u.active = 1
        LIMIT 1
        """,
        (code,),
    ).fetchone()

    if not row or row["used_at"]:
        conn.close()
        return {"status": "invalid", "student": None}

    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        conn.close()
        return {"status": "expired", "student": None}

    conn.execute(
        "UPDATE student_web_login_codes SET used_at = ? WHERE id = ?",
        (now_iso(), int(row["code_id"])),
    )
    conn.commit()
    student = {
        "id": int(row["id"]),
        "name": row["name"],
        "telegram_username": row["telegram_username"],
        "grade": row["grade"],
    }
    conn.close()
    return {"status": "ok", "student": student}
