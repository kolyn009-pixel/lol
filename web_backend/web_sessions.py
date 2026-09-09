"""Persistent web sessions for Adelia.

Raw bearer tokens are returned only to the browser cookie. SQLite stores only a
SHA-256 digest, so a database copy cannot be used as an active session cookie.
Sessions survive API restarts and can be revoked explicitly on logout.
"""
from __future__ import annotations

import hashlib
import secrets
import time

from database import connect, now_iso
from core import admin_roles

SESSION_TTL = 60 * 60 * 24 * 30


def _digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def ensure_table() -> None:
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS web_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_seen_at TEXT,
            revoked_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_web_sessions_token
            ON web_sessions(token_hash);
        CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry
            ON web_sessions(expires_at);
        """
    )
    conn.commit()
    conn.close()


def _identity_active(conn, role, entity_id):
    role = str(role or "").lower()
    entity_id = int(entity_id)
    if role == "student":
        row = conn.execute(
            "SELECT id FROM users WHERE id=? AND active=1 LIMIT 1",
            (entity_id,),
        ).fetchone()
        return bool(row)
    if role == "teacher":
        try:
            return admin_roles.role_for(entity_id) in {"OWNER", "ADMIN"}
        except Exception:
            return False
    return False


def create_session(role, entity_id, ttl_seconds=SESSION_TTL):
    ensure_table()
    role = str(role or "").strip().lower()
    if role not in {"student", "teacher"}:
        raise ValueError("invalid_session_role")
    entity_id = int(entity_id)
    ttl_seconds = max(300, min(int(ttl_seconds), SESSION_TTL))
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + ttl_seconds
    conn = connect()
    if not _identity_active(conn, role, entity_id):
        conn.close()
        raise PermissionError("session_identity_inactive")
    conn.execute(
        """
        INSERT INTO web_sessions(
            token_hash, role, entity_id, expires_at, created_at, last_seen_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (_digest(token), role, entity_id, expires, now_iso(), now_iso()),
    )
    conn.execute(
        "DELETE FROM web_sessions WHERE expires_at < ? OR revoked_at IS NOT NULL",
        (int(time.time()) - 86400,),
    )
    conn.commit()
    conn.close()
    return token


def read_session(token):
    if not token:
        return None
    ensure_table()
    now = int(time.time())
    conn = connect()
    row = conn.execute(
        """
        SELECT id, role, entity_id, expires_at
        FROM web_sessions
        WHERE token_hash = ? AND revoked_at IS NULL AND expires_at >= ?
        LIMIT 1
        """,
        (_digest(token), now),
    ).fetchone()
    if not row:
        conn.execute("DELETE FROM web_sessions WHERE expires_at < ?", (now,))
        conn.commit()
        conn.close()
        return None
    if not _identity_active(conn, row["role"], row["entity_id"]):
        conn.execute(
            "UPDATE web_sessions SET revoked_at=? WHERE id=?",
            (now_iso(), int(row["id"])),
        )
        conn.commit()
        conn.close()
        return None
    conn.execute(
        "UPDATE web_sessions SET last_seen_at=? WHERE id=?",
        (now_iso(), int(row["id"])),
    )
    conn.commit()
    item = {
        "role": str(row["role"]),
        "id": int(row["entity_id"]),
        "expires": int(row["expires_at"]),
    }
    conn.close()
    return item


def revoke_session(token):
    if not token:
        return False
    ensure_table()
    conn = connect()
    cur = conn.execute(
        "UPDATE web_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
        (now_iso(), _digest(token)),
    )
    conn.commit()
    changed = bool(cur.rowcount)
    conn.close()
    return changed
