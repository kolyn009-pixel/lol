"""One-time login codes for the teacher web cabinet.

The bot can call issue_teacher_login_code(admin_telegram_id) and send the code
to the teacher. Codes are short-lived, one-time, and stored in tutor.db.
Only active OWNER and ADMIN accounts may enter the teacher web cabinet.
"""

import secrets
from datetime import datetime, timedelta

from database import connect, now_iso
from core import admin_roles

TTL_MINUTES = 10
TEACHER_WEB_ROLES = {"OWNER", "ADMIN"}


def _can_use_teacher_web(telegram_id):
    if telegram_id is None:
        return False
    try:
        return admin_roles.role_for(int(telegram_id)) in TEACHER_WEB_ROLES
    except (TypeError, ValueError):
        return False


def ensure_table():
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teacher_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_telegram_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_teacher_web_code ON teacher_web_login_codes(code)"
    )
    conn.commit()
    conn.close()


def issue_teacher_login_code(admin_telegram_id, ttl_minutes=TTL_MINUTES):
    admin_telegram_id = int(admin_telegram_id)
    if not _can_use_teacher_web(admin_telegram_id):
        raise PermissionError("teacher_web_access_denied")

    ensure_table()
    ttl_minutes = max(1, min(int(ttl_minutes), 30))
    expires_at = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")
    conn = connect()
    conn.execute(
        "UPDATE teacher_web_login_codes SET used_at=? WHERE admin_telegram_id=? AND used_at IS NULL",
        (now_iso(), admin_telegram_id),
    )
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        exists = conn.execute("SELECT 1 FROM teacher_web_login_codes WHERE code=?", (code,)).fetchone()
        if not exists:
            break
    conn.execute(
        "INSERT INTO teacher_web_login_codes(admin_telegram_id,code,expires_at,created_at) VALUES(?,?,?,?)",
        (admin_telegram_id, code, expires_at, now_iso()),
    )
    conn.commit()
    conn.close()
    return code


def consume_teacher_login_code(code):
    ensure_table()
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code) != 6:
        return {"status": "invalid"}
    conn = connect()
    row = conn.execute(
        "SELECT * FROM teacher_web_login_codes WHERE code=? LIMIT 1",
        (code,),
    ).fetchone()
    if not row or row["used_at"]:
        conn.close()
        return {"status": "invalid"}
    if datetime.fromisoformat(row["expires_at"]) < datetime.now():
        conn.close()
        return {"status": "expired"}
    admin_tid = int(row["admin_telegram_id"])
    if not _can_use_teacher_web(admin_tid):
        conn.close()
        return {"status": "invalid"}
    conn.execute("UPDATE teacher_web_login_codes SET used_at=? WHERE id=?", (now_iso(), int(row["id"])))
    conn.commit()
    conn.close()
    return {"status": "ok", "admin_telegram_id": admin_tid}
