from __future__ import annotations

from datetime import datetime, timedelta
import secrets
import string

import database


def initialize():
    c = database.connect()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS channel_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                external_id TEXT NOT NULL,
                username TEXT,
                display_name TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                blocked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(channel, external_id),
                UNIQUE(user_id, channel),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS channel_link_codes (
                code TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS channel_admin_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                external_id TEXT NOT NULL,
                username TEXT,
                display_name TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                UNIQUE(channel, external_id),
                UNIQUE(admin_telegram_id, channel)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS channel_admin_link_codes (
                code TEXT PRIMARY KEY,
                admin_telegram_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_identity_user ON channel_identities(user_id,channel,enabled)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_link_expiry ON channel_link_codes(expires_at,used_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_admin_identity ON channel_admin_identities(admin_telegram_id,channel,enabled)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_admin_link_expiry ON channel_admin_link_codes(expires_at,used_at)")
        c.commit()
    finally:
        c.close()


def _now():
    return datetime.now()


def _code(prefix):
    alphabet = string.digits
    return str(prefix) + "".join(secrets.choice(alphabet) for _ in range(6))


def create_link_code(user_id: int, minutes: int = 15) -> str:
    initialize()
    code = _code("ADELIA-")
    now = _now()
    expires = now + timedelta(minutes=int(minutes))
    c = database.connect()
    try:
        c.execute("DELETE FROM channel_link_codes WHERE user_id=? AND used_at IS NULL", (int(user_id),))
        c.execute(
            "INSERT INTO channel_link_codes(code,user_id,expires_at,created_at) VALUES(?,?,?,?)",
            (code, int(user_id), expires.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")),
        )
        c.commit()
    finally:
        c.close()
    return code


def create_admin_link_code(admin_telegram_id: int, minutes: int = 15) -> str:
    initialize()
    code = _code("ADELIA-ADMIN-")
    now = _now()
    expires = now + timedelta(minutes=int(minutes))
    c = database.connect()
    try:
        c.execute(
            "DELETE FROM channel_admin_link_codes WHERE admin_telegram_id=? AND used_at IS NULL",
            (int(admin_telegram_id),),
        )
        c.execute(
            "INSERT INTO channel_admin_link_codes(code,admin_telegram_id,expires_at,created_at) VALUES(?,?,?,?)",
            (code, int(admin_telegram_id), expires.isoformat(timespec="seconds"), now.isoformat(timespec="seconds")),
        )
        c.commit()
    finally:
        c.close()
    return code


def consume_link_code(code: str, channel: str, external_id: str, username=None, display_name=None):
    initialize()
    normalized = str(code or "").strip().upper().replace(" ", "")
    c = database.connect()
    try:
        row = c.execute(
            "SELECT * FROM channel_link_codes WHERE code=? AND used_at IS NULL",
            (normalized,),
        ).fetchone()
        if not row:
            return None, "Код не найден или уже использован."
        try:
            expires = datetime.fromisoformat(str(row["expires_at"]))
        except Exception:
            return None, "У кода некорректный срок действия."
        if expires < _now():
            return None, "Срок действия кода истёк. Получите новый код в Telegram."
        user_id = int(row["user_id"])
        c.execute("DELETE FROM channel_identities WHERE channel=? AND external_id=? AND user_id!=?", (str(channel), str(external_id), user_id))
        c.execute(
            """
            INSERT INTO channel_identities(user_id,channel,external_id,username,display_name,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,1,?,?)
            ON CONFLICT(user_id,channel) DO UPDATE SET
                external_id=excluded.external_id,
                username=excluded.username,
                display_name=excluded.display_name,
                enabled=1,
                blocked_at=NULL,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                str(channel).upper(),
                str(external_id),
                username,
                display_name,
                database.now_iso(),
                database.now_iso(),
            ),
        )
        c.execute("UPDATE channel_link_codes SET used_at=? WHERE code=?", (database.now_iso(), normalized))
        c.commit()
        return user_id, None
    finally:
        c.close()


def consume_admin_link_code(code: str, channel: str, external_id: str, username=None, display_name=None):
    initialize()
    normalized = str(code or "").strip().upper().replace(" ", "")
    c = database.connect()
    try:
        row = c.execute(
            "SELECT * FROM channel_admin_link_codes WHERE code=? AND used_at IS NULL",
            (normalized,),
        ).fetchone()
        if not row:
            return None, "Код преподавателя не найден или уже использован."
        try:
            expires = datetime.fromisoformat(str(row["expires_at"]))
        except Exception:
            return None, "У кода некорректный срок действия."
        if expires < _now():
            return None, "Срок действия кода истёк. Получите новый код в Telegram."
        admin_id = int(row["admin_telegram_id"])
        c.execute(
            "DELETE FROM channel_admin_identities WHERE channel=? AND external_id=? AND admin_telegram_id!=?",
            (str(channel).upper(), str(external_id), admin_id),
        )
        c.execute(
            """
            INSERT INTO channel_admin_identities(admin_telegram_id,channel,external_id,username,display_name,enabled,created_at,updated_at)
            VALUES(?,?,?,?,?,1,?,?)
            ON CONFLICT(admin_telegram_id,channel) DO UPDATE SET
                external_id=excluded.external_id,
                username=excluded.username,
                display_name=excluded.display_name,
                enabled=1,
                updated_at=excluded.updated_at
            """,
            (
                admin_id,
                str(channel).upper(),
                str(external_id),
                username,
                display_name,
                database.now_iso(),
                database.now_iso(),
            ),
        )
        c.execute(
            "UPDATE channel_admin_link_codes SET used_at=? WHERE code=?",
            (database.now_iso(), normalized),
        )
        c.commit()
        return admin_id, None
    finally:
        c.close()


def get_user_id(channel: str, external_id: str):
    initialize()
    c = database.connect()
    try:
        row = c.execute(
            "SELECT user_id FROM channel_identities WHERE channel=? AND external_id=? AND enabled=1",
            (str(channel).upper(), str(external_id)),
        ).fetchone()
        return int(row["user_id"]) if row else None
    finally:
        c.close()


def get_admin_telegram_id(channel: str, external_id: str):
    initialize()
    c = database.connect()
    try:
        row = c.execute(
            "SELECT admin_telegram_id FROM channel_admin_identities WHERE channel=? AND external_id=? AND enabled=1",
            (str(channel).upper(), str(external_id)),
        ).fetchone()
        return int(row["admin_telegram_id"]) if row else None
    finally:
        c.close()


def get_admin_external_ids(channel="VK"):
    initialize()
    c = database.connect()
    try:
        rows = c.execute(
            "SELECT external_id FROM channel_admin_identities WHERE channel=? AND enabled=1 ORDER BY id",
            (str(channel).upper(),),
        ).fetchall()
        return [int(r["external_id"]) for r in rows]
    finally:
        c.close()


def set_channel_enabled(channel: str, external_id: str, enabled: bool):
    initialize()
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE channel_identities
            SET enabled=?, blocked_at=?, updated_at=?
            WHERE channel=? AND external_id=?
            """,
            (
                1 if enabled else 0,
                None if enabled else database.now_iso(),
                database.now_iso(),
                str(channel).upper(),
                str(external_id),
            ),
        )
        c.commit()
    finally:
        c.close()
