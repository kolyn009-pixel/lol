"""Student web authentication for Adelia.

Telegram one-time codes are the trusted first-link/recovery channel. After the
first successful code login a student can create a permanent login/password.
Passwords are never stored in plaintext: only PBKDF2-SHA256 hashes are kept.
One-time Telegram codes are also stored only as SHA-256 digests.

The existing /api/auth/student/code HTTP endpoint is intentionally kept for
backward compatibility. It accepts three payload forms in its single `code`
field:
- 123456                           -> legacy one-time-code login
- login:<login>:<password>         -> permanent credential login
- setup:<code>:<login>:<password>  -> verify Telegram code and create/reset credentials
"""

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from database import connect, now_iso
from web_backend.web_sessions import revoke_identity_sessions

CODE_TTL_MINUTES = 10
PBKDF2_ITERATIONS = 600_000
_LOGIN_RE = re.compile(r"^[a-z0-9._-]{4,32}$")
_DUMMY_SALT = b"adelia-auth-dummy"


def ensure_student_web_login_table():
    conn = connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS student_web_login_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_student_web_login_code ON student_web_login_codes(code);
        CREATE TABLE IF NOT EXISTS student_web_credentials (
            student_id INTEGER PRIMARY KEY,
            login TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_student_web_credentials_login ON student_web_credentials(login COLLATE NOCASE);
    """)
    conn.commit();conn.close()


def _new_code():return f"{secrets.randbelow(1_000_000):06d}"
def _code_digest(code):return hashlib.sha256(str(code or "").strip().encode("utf-8")).hexdigest()

def _normalize_login(login):
    value=str(login or "").strip().lower()
    if not _LOGIN_RE.fullmatch(value):raise ValueError("invalid_login")
    return value

def _validate_password(password):
    value=str(password or "")
    if len(value)<8:raise ValueError("password_too_short")
    if len(value)>128:raise ValueError("password_too_long")
    return value

def _password_hash(password):
    password=_validate_password(password);salt=secrets.token_bytes(16);digest=hashlib.pbkdf2_hmac("sha256",password.encode("utf-8"),salt,PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(PBKDF2_ITERATIONS,base64.urlsafe_b64encode(salt).decode("ascii"),base64.urlsafe_b64encode(digest).decode("ascii"))

def _password_matches(password,encoded):
    try:
        scheme,iterations,salt_text,digest_text=str(encoded).split("$",3)
        if scheme!="pbkdf2_sha256":return False
        salt=base64.urlsafe_b64decode(salt_text.encode("ascii"));expected=base64.urlsafe_b64decode(digest_text.encode("ascii"));actual=hashlib.pbkdf2_hmac("sha256",str(password or "").encode("utf-8"),salt,int(iterations));return hmac.compare_digest(actual,expected)
    except Exception:return False

def _dummy_password_work(password):hashlib.pbkdf2_hmac("sha256",str(password or "").encode("utf-8"),_DUMMY_SALT,PBKDF2_ITERATIONS)

def has_student_credentials(student_id):
    ensure_student_web_login_table();conn=connect();row=conn.execute("SELECT 1 FROM student_web_credentials WHERE student_id=? LIMIT 1",(int(student_id),)).fetchone();conn.close();return bool(row)


def _validate_credential_change(student_id,login,password):
    """Cheap validation before consuming a one-time recovery code."""
    ensure_student_web_login_table();student_id=int(student_id);login=_normalize_login(login);password=_validate_password(password)
    conn=connect();student=conn.execute("SELECT id FROM users WHERE id=? AND active=1 LIMIT 1",(student_id,)).fetchone()
    if not student:conn.close();raise ValueError("student_not_found")
    owner=conn.execute("SELECT student_id FROM student_web_credentials WHERE login=? COLLATE NOCASE LIMIT 1",(login,)).fetchone();conn.close()
    if owner and int(owner["student_id"])!=student_id:raise ValueError("login_taken")
    return login,password


def set_student_credentials(student_id,login,password,revoke_existing=True):
    ensure_student_web_login_table();student_id=int(student_id);login,password=_validate_credential_change(student_id,login,password);password_hash=_password_hash(password);conn=connect()
    existing=conn.execute("SELECT student_id FROM student_web_credentials WHERE student_id=? LIMIT 1",(student_id,)).fetchone()
    if existing:conn.execute("UPDATE student_web_credentials SET login=?, password_hash=?, updated_at=? WHERE student_id=?",(login,password_hash,now_iso(),student_id))
    else:conn.execute("INSERT INTO student_web_credentials(student_id, login, password_hash, created_at) VALUES(?,?,?,?)",(student_id,login,password_hash,now_iso()))
    conn.commit();conn.close()
    if revoke_existing:revoke_identity_sessions("student",student_id)
    return {"status":"ok","login":login}


def authenticate_student(login,password):
    ensure_student_web_login_table()
    try:login=_normalize_login(login)
    except ValueError:_dummy_password_work(password);return {"status":"invalid","student":None}
    conn=connect();row=conn.execute("""SELECT u.id,u.name,u.telegram_username,u.grade,c.password_hash FROM student_web_credentials c JOIN users u ON u.id=c.student_id WHERE c.login=? COLLATE NOCASE AND u.active=1 LIMIT 1""",(login,)).fetchone()
    if not row:conn.close();_dummy_password_work(password);return {"status":"invalid","student":None}
    if not _password_matches(password,row["password_hash"]):conn.close();return {"status":"invalid","student":None}
    student={"id":int(row["id"]),"name":row["name"],"telegram_username":row["telegram_username"],"grade":row["grade"]};conn.close();return {"status":"ok","student":student}


def issue_student_login_code(student_id,ttl_minutes=CODE_TTL_MINUTES):
    ensure_student_web_login_table();student_id=int(student_id);ttl_minutes=max(1,min(int(ttl_minutes),30));expires_at=(datetime.now()+timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds");conn=connect();student=conn.execute("SELECT id FROM users WHERE id=? AND active=1",(student_id,)).fetchone()
    if not student:conn.close();raise ValueError("student_not_found")
    conn.execute("UPDATE student_web_login_codes SET used_at=? WHERE student_id=? AND used_at IS NULL",(now_iso(),student_id))
    while True:
        code=_new_code();digest=_code_digest(code);exists=conn.execute("SELECT 1 FROM student_web_login_codes WHERE code=?",(digest,)).fetchone()
        if not exists:break
    conn.execute("INSERT INTO student_web_login_codes(student_id,code,expires_at,created_at) VALUES(?,?,?,?)",(student_id,digest,expires_at,now_iso()));conn.commit();conn.close();return code


def _peek_plain_code(code):
    code="".join(ch for ch in str(code or "") if ch.isdigit())
    if len(code)!=6:return {"status":"invalid","student":None}
    conn=connect();row=conn.execute("""SELECT c.id AS code_id,c.expires_at,c.used_at,u.id,u.name,u.telegram_username,u.grade FROM student_web_login_codes c JOIN users u ON u.id=c.student_id WHERE c.code=? AND u.active=1 LIMIT 1""",(_code_digest(code),)).fetchone();conn.close()
    if not row or row["used_at"]:return {"status":"invalid","student":None}
    if datetime.fromisoformat(row["expires_at"])<datetime.now():return {"status":"expired","student":None}
    return {"status":"ok","code_id":int(row["code_id"]),"student":{"id":int(row["id"]),"name":row["name"],"telegram_username":row["telegram_username"],"grade":row["grade"]}}


def _consume_plain_code(code):
    result=_peek_plain_code(code)
    if result.get("status")!="ok":return result
    conn=connect();cur=conn.execute("UPDATE student_web_login_codes SET used_at=? WHERE id=? AND used_at IS NULL",(now_iso(),int(result["code_id"])));conn.commit();conn.close()
    if not cur.rowcount:return {"status":"invalid","student":None}
    return {"status":"ok","student":result["student"]}


def consume_student_login_code(payload):
    ensure_student_web_login_table();raw=str(payload or "")
    if raw.startswith("login:"):
        parts=raw.split(":",2)
        if len(parts)!=3:return {"status":"invalid","student":None}
        return authenticate_student(parts[1],parts[2])
    if raw.startswith("setup:"):
        parts=raw.split(":",3)
        if len(parts)!=4:return {"status":"invalid","student":None}
        preview=_peek_plain_code(parts[1])
        if preview.get("status")!="ok":return preview
        try:_validate_credential_change(preview["student"]["id"],parts[2],parts[3])
        except ValueError as exc:return {"status":str(exc),"student":None}
        result=_consume_plain_code(parts[1])
        if result.get("status")!="ok":return result
        try:set_student_credentials(result["student"]["id"],parts[2],parts[3],revoke_existing=True)
        except ValueError as exc:return {"status":str(exc),"student":None}
        return result
    return _consume_plain_code(raw)
