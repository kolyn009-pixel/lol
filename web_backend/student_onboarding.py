"""Permanent-student onboarding for returning TutorBot students.

The browser owns the visual flow. Telegram/VK only prove channel ownership.
A canonical user is never selected by name alone: an existing channel identity
must resolve it, otherwise the session goes to NEED_TEACHER_MATCH.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import secrets
import string

import database
from web_backend import student_auth, web_sessions

SESSION_TTL_MINUTES = 60
TG_BOT_URL = "https://t.me/AdeliaTutorBot"
VK_MESSAGES_URL = "https://vk.me/club241263797"


def _now():
    return datetime.now()


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _token(prefix="JOIN"):
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "-" + "".join(secrets.choice(alphabet) for _ in range(10))


def ensure_schema():
    c = database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS student_onboarding_sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      token TEXT NOT NULL UNIQUE,
      mode TEXT NOT NULL DEFAULT 'RETURNING',
      preferred_channel TEXT,
      claimed_profile_url TEXT,
      status TEXT NOT NULL DEFAULT 'WAIT_CHANNEL',
      external_id TEXT,
      external_username TEXT,
      external_display_name TEXT,
      linked_user_id INTEGER,
      region TEXT,
      timezone TEXT,
      schedule_json TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      completed_at TEXT,
      FOREIGN KEY(linked_user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE INDEX IF NOT EXISTS idx_student_onboarding_token ON student_onboarding_sessions(token);
    CREATE INDEX IF NOT EXISTS idx_student_onboarding_status ON student_onboarding_sessions(status,expires_at);
    """)
    c.commit()
    c.close()


def _row(token):
    ensure_schema()
    c = database.connect()
    try:
        r = c.execute("SELECT * FROM student_onboarding_sessions WHERE token=? LIMIT 1", (str(token or '').strip().upper(),)).fetchone()
        return dict(r) if r else None
    finally:
        c.close()


def _active(row):
    if not row:
        raise ValueError("onboarding_not_found")
    if datetime.fromisoformat(row["expires_at"]) < _now():
        raise ValueError("onboarding_expired")
    return row


def _find_existing_user(channel, external_id):
    channel = str(channel or '').upper()
    external_id = str(external_id or '').strip()
    c = database.connect()
    try:
        if channel == "TELEGRAM":
            r = c.execute("SELECT id FROM users WHERE telegram_id=? LIMIT 1", (int(external_id),)).fetchone()
            if r:
                return int(r["id"])
        try:
            r = c.execute("SELECT user_id FROM channel_identities WHERE channel=? AND external_id=? AND enabled=1 LIMIT 1", (channel, external_id)).fetchone()
            if r:
                return int(r["user_id"])
        except Exception:
            pass
        return None
    finally:
        c.close()


def start_returning(preferred_channel, profile_url=None):
    ensure_schema()
    channel = str(preferred_channel or '').strip().upper()
    if channel not in {"TELEGRAM", "VK"}:
        raise ValueError("invalid_channel")
    token = _token()
    now = _now()
    expires = now + timedelta(minutes=SESSION_TTL_MINUTES)
    c = database.connect()
    c.execute("""INSERT INTO student_onboarding_sessions(token,mode,preferred_channel,claimed_profile_url,status,created_at,updated_at,expires_at)
                 VALUES(?, 'RETURNING', ?, ?, 'WAIT_CHANNEL', ?, ?, ?)""",
              (token, channel, str(profile_url or '').strip()[:500] or None, _iso(now), _iso(now), _iso(expires)))
    c.commit();c.close()
    return {
        "token": token,
        "preferred_channel": channel,
        "telegram_url": f"{TG_BOT_URL}?start=join_{token}",
        "vk_url": VK_MESSAGES_URL,
        "vk_code": token,
        "expires_at": _iso(expires),
    }


def confirm_channel(token, channel, external_id, username=None, display_name=None):
    row = _active(_row(token))
    channel = str(channel or '').strip().upper()
    if channel != str(row["preferred_channel"] or '').upper():
        raise ValueError("wrong_channel")
    uid = _find_existing_user(channel, external_id)
    status = "CHANNEL_VERIFIED" if uid else "NEED_TEACHER_MATCH"
    now = _iso()
    c = database.connect()
    c.execute("""UPDATE student_onboarding_sessions
                 SET status=?,external_id=?,external_username=?,external_display_name=?,linked_user_id=?,updated_at=?
                 WHERE id=?""",
              (status,str(external_id),str(username or '').strip()[:100] or None,str(display_name or '').strip()[:160] or None,uid,now,int(row['id'])))
    c.commit();c.close()
    return status_payload(token)


def teacher_match(token, user_id):
    row = _active(_row(token));uid=int(user_id)
    if not database.get_user(uid):
        raise ValueError("student_not_found")
    c=database.connect();c.execute("UPDATE student_onboarding_sessions SET linked_user_id=?,status='CHANNEL_VERIFIED',updated_at=? WHERE id=?",(uid,_iso(),int(row['id'])));c.commit();c.close()
    return status_payload(token)


def save_region(token, region, timezone):
    row = _active(_row(token))
    if row["status"] not in {"CHANNEL_VERIFIED","REGION_SET","SCHEDULE_SET"}:
        raise ValueError("channel_not_verified")
    region = str(region or '').strip()[:100]
    timezone = str(timezone or '').strip()[:80]
    if not region or not timezone:
        raise ValueError("region_required")
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try: ZoneInfo(timezone)
    except ZoneInfoNotFoundError: raise ValueError("invalid_timezone")
    c=database.connect();c.execute("UPDATE student_onboarding_sessions SET region=?,timezone=?,status='REGION_SET',updated_at=? WHERE id=?",(region,timezone,_iso(),int(row['id'])));c.commit();c.close()
    return status_payload(token)


def save_schedule(token, selections):
    row = _active(_row(token))
    if row["status"] not in {"REGION_SET","SCHEDULE_SET"}:
        raise ValueError("region_not_set")
    values = selections if isinstance(selections,list) else []
    clean=[]
    for x in values[:4]:
        if not isinstance(x,dict): continue
        day=str(x.get('weekday') or '').strip()[:20]
        time=str(x.get('time') or '').strip()[:8]
        duration=int(x.get('duration_minutes') or 60)
        if day and time and 30 <= duration <= 180:
            clean.append({'weekday':day,'time':time,'duration_minutes':duration})
    if not clean:
        raise ValueError("schedule_required")
    c=database.connect();c.execute("UPDATE student_onboarding_sessions SET schedule_json=?,status='SCHEDULE_SET',updated_at=? WHERE id=?",(json.dumps(clean,ensure_ascii=False),_iso(),int(row['id'])));c.commit();c.close()
    return status_payload(token)


def complete(token, login, password):
    row = _active(_row(token))
    if row["status"] != "SCHEDULE_SET" or not row.get("linked_user_id"):
        raise ValueError("onboarding_incomplete")
    uid=int(row['linked_user_id'])
    # Returning students can have been archived/inactive between school years.
    c=database.connect();c.execute("UPDATE users SET active=1,updated_at=? WHERE id=?",(_iso(),uid));c.commit();c.close()
    result=student_auth.set_student_credentials(uid,login,password,revoke_existing=True)
    session=web_sessions.create_session('student',uid)
    c=database.connect();c.execute("UPDATE student_onboarding_sessions SET status='COMPLETED',completed_at=?,updated_at=? WHERE id=?",(_iso(),_iso(),int(row['id'])));c.commit();c.close()
    return {'status':'ok','user_id':uid,'login':result['login'],'session_token':session,'redirect':'/app/'}


def status_payload(token):
    row = _active(_row(token))
    user=None
    if row.get('linked_user_id'):
        u=database.get_user(int(row['linked_user_id']))
        if u:user={'id':int(u['id']),'name':u['name'],'grade':u['grade'],'main_subject':u['main_subject'],'study_goal':u['study_goal']}
    try:schedule=json.loads(row.get('schedule_json') or '[]')
    except Exception:schedule=[]
    return {
        'token':row['token'],'mode':row['mode'],'preferred_channel':row['preferred_channel'],'status':row['status'],
        'region':row.get('region'),'timezone':row.get('timezone'),'schedule':schedule,'user':user,
        'external_username':row.get('external_username'),'external_display_name':row.get('external_display_name'),
        'expires_at':row['expires_at']
    }
