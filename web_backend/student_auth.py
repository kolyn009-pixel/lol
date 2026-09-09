"""Student web authentication for Adelia.

Telegram one-time codes are the trusted first-link/recovery channel. After the
first successful code login a student can create a permanent login/password.
Passwords are never stored in plaintext: only PBKDF2-SHA256 hashes are kept.
"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from database import connect, now_iso


CODE_TTL_MINUTES = 10
PBKDF2_ITERATIONS = 600_000
_LOGIN_RE = re.compile(r"^[a-z0-9._-]{4,32}$")


def ensure_student_web_login_table():
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS student_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_student_web_login_code
            ON student_web_login_codes(code);

        CREATE TABLE IF NOT EXISTS student_web_credentials (
            student_id INTEGER PRIMARY KEY,
            login TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_student_web_credentials_login
            ON student_web_credentials(login COLLATE NOCASE);
        """
    )
    conn.commit()
    conn.close()


def _new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def _normalize_login(login):
    value = str(login or "").strip().lower()
    if not _LOGIN_RE.fullmatch(value):
        raise ValueError("invalid_login")
    return value


def _validate_password(password):
    value = str(password or "")
    if len(value) < 8:
        raise ValueError("password_too_short")
    if len(value) > 128:
        raise ValueError("password_too_long")
    return value


def _password_hash(password):
    password = _validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def _password_matches(password, encoded):
    try:
        scheme, iterations, salt_text, digest_text = str(encoded).split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256", str(password or "").encode("utf-8"), salt, int(iterations)
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def has_student_credentials(student_id):
    ensure_student_web_login_table()
    conn = connect()
    row = conn.execute(
        "SELECT 1 FROM student_web_credentials WHERE student_id=? LIMIT 1",
        (int(student_id),),
    ).fetchone()
    conn.close()
    return bool(row)


def set_student_credentials(student_id, login, password):
    ensure_student_web_login_table()
    student_id = int(student_id)
    login = _normalize_login(login)
    password_hash = _password_hash(password)
    conn = connect()
    student = conn.execute(
        "SELECT id FROM users WHERE id=? AND active=1 LIMIT 1", (student_id,)
    ).fetchone()
    if not student:
        conn.close()
        raise ValueError("student_not_found")
    owner = conn.execute(
        "SELECT student_id FROM student_web_credentials WHERE login=? COLLATE NOCASE LIMIT 1",
        (login,),
    ).fetchone()
    if owner and int(owner["student_id"]) != student_id:
        conn.close()
        raise ValueError("login_taken")
    existing = conn.execute(
        "SELECT student_id FROM student_web_credentials WHERE student_id=? LIMIT 1",
        (student_id,),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE student_web_credentials SET login=?, password_hash=?, updated_at=? WHERE student_id=?",
            (login, password_hash, now_iso(), student_id),
        )
    else:
        conn.execute(
            "INSERT INTO student_web_credentials(student_id, login, password_hash, created_at) VALUES(?,?,?,?)",
            (student_id, login, password_hash, now_iso()),
        )
    conn.commit()
    conn.close()
    return {"status": "ok", "login": login}


def authenticate_student(login, password):
    ensure_student_web_login_table()
    try:
        login = _normalize_login(login)
    except ValueError:
        return {"status": "invalid", "student": None}
    conn = connect()
    row = conn.execute(
        """
        SELECT u.id, u.name, u.telegram_username, u.grade, c.password_hash
        FROM student_web_credentials c
        JOIN users u ON u.id=c.student_id
        WHERE c.login=? COLLATE NOCASE AND u.active=1
        LIMIT 1
        """,
        (login,),
    ).fetchone()
    if not row or not _password_matches(password, row["password_hash"]):
        conn.close()
        return {"status": "invalid", "student": None}
    student = {
        "id": int(row["id"]),
        "name": row["name"],
        "telegram_username": row["telegram_username"],
        "grade": row["grade"],
    }
    conn.close()
    return {"status": "ok", "student": student}


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
