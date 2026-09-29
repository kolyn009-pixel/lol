"""Read models for the authenticated student web cabinet.

All screens are built from TutorBot's production data model; no demo values are
kept here. The functions are intentionally read-only and lightweight so the PWA
can render quickly on mobile connections.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from time import monotonic
from threading import Lock

from database import connect, get_user, get_user_timezone
from core.lesson_time import lesson_timezone, schedule_datetime
from core.user_timezone import fixed_zone_name_from_msk_offset

_ZONE_LABELS = {
    "Europe/Moscow": "Москва",
    "Europe/Samara": "Самара",
    "Asia/Yekaterinburg": "Екатеринбург",
    "Asia/Omsk": "Омск",
    "Asia/Krasnoyarsk": "Красноярск",
    "Asia/Irkutsk": "Иркутск",
    "Europe/Istanbul": "Стамбул",
    "Asia/Dubai": "Дубай",
    "Asia/Tbilisi": "Тбилиси",
    "Europe/Berlin": "Берлин",
    "Asia/Bangkok": "Бангкок",
}


def _valid_zone(name):
    try:
        value = str(name or "")
        ZoneInfo(value)
        return value
    except Exception:
        return None


def _student_timezone(user, conn):
    """Resolve an authenticated student's saved region, never the device timezone."""
    telegram_id = user["telegram_id"] if "telegram_id" in user.keys() else None
    pref = get_user_timezone(telegram_id) if telegram_id else None
    chosen = []
    if pref and int(pref["configured"] or 0):
        offset = int(pref["msk_offset"] or 0)
        zone = _valid_zone(pref["zone_name"]) or _valid_zone(fixed_zone_name_from_msk_offset(offset))
        if zone:
            chosen.append((str(pref["updated_at"] or ""), {
                "zone": zone,
                "label": _ZONE_LABELS.get(zone, f"МСК {offset:+d}" if offset else "Москва"),
                "selected": True,
            }))
    desktop_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_desktop_timezones'"
    ).fetchone()
    if desktop_exists:
        desktop = conn.execute(
            "SELECT zone_name, label, updated_at FROM student_desktop_timezones WHERE user_id=?",
            (int(user["id"]),),
        ).fetchone()
        zone = _valid_zone(desktop["zone_name"]) if desktop else None
        if zone:
            chosen.append((str(desktop["updated_at"] or ""), {
                "zone": zone,
                "label": str(desktop["label"] or _ZONE_LABELS.get(zone) or zone).strip()[:80],
                "selected": True,
            }))
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_onboarding_sessions'"
    ).fetchone()
    if exists:
        row = conn.execute(
            """SELECT region, timezone, completed_at, updated_at FROM student_onboarding_sessions
               WHERE linked_user_id=? AND timezone IS NOT NULL AND timezone!=''
               ORDER BY updated_at DESC, id DESC LIMIT 1""",
            (int(user["id"]),),
        ).fetchone()
        zone = _valid_zone(row["timezone"]) if row else None
        if zone:
            chosen.append((str(row["updated_at"] or row["completed_at"] or ""), {
                "zone": zone,
                "label": str(row["region"] or _ZONE_LABELS.get(zone) or zone).strip()[:80],
                "selected": True,
            }))
    if chosen:
        return max(chosen, key=lambda item: item[0])[1]
    return {"zone": "Europe/Moscow", "label": "Москва", "selected": False}


def set_student_timezone(user_id, zone_name):
    """Save a student's explicit desktop choice; never infer it from an IP address."""
    uid = int(user_id)
    user = get_user(uid)
    if not user or not user["active"]:
        raise PermissionError("student_not_found")
    raw = str(zone_name or "").strip()
    if len(raw) > 80 or not _valid_zone(raw):
        raise ValueError("invalid_timezone")
    label = _ZONE_LABELS.get(raw) or raw.rsplit("/", 1)[-1].replace("_", " ")
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
    conn = connect()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS student_desktop_timezones (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            zone_name TEXT NOT NULL,
            label TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""")
        conn.execute("""INSERT INTO student_desktop_timezones(user_id,zone_name,label,updated_at)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            zone_name=excluded.zone_name,label=excluded.label,updated_at=excluded.updated_at""",
            (uid, raw, label, now))
        conn.commit()
    finally:
        conn.close()
    with _CACHE_LOCK:
        _CACHE.pop(("dashboard", uid), None)
    return {"timezone": {"zone": raw, "label": label, "selected": True}}


def _lesson_instant(item):
    for field in ("start_time", "end_time"):
        if item.get(field):
            try:
                item[field.replace("_time", "_at")] = schedule_datetime(item[field]).isoformat()
            except (TypeError, ValueError):
                pass
    return item


_CACHE = {}
_CACHE_LOCK = Lock()


def _dict(row):
    return dict(row) if row else None


def _cached(key, ttl, loader):
    now = monotonic()
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item and now - item[0] < ttl:
            return item[1]
    value = loader()
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
    return value


def _lesson_state(row):
    status = str(row.get("lesson_status") or "").upper()
    if row.get("finished_at") or status in {"COMPLETED", "DONE", "HELD"}:
        return "completed"
    if status in {"CANCELLED", "REJECTED"}:
        return "cancelled"
    if row.get("started_at"):
        return "in_progress"
    return "upcoming"


def dashboard(user_id):
    uid = int(user_id)

    def load():
        user = get_user(uid)
        if not user or not user["active"]:
            return None
        conn = connect()
        now = datetime.now(lesson_timezone()).replace(tzinfo=None).isoformat(timespec="seconds")
        next_lesson = conn.execute(
            """
            SELECT id,start_time,end_time,duration_minutes,subject,study_goal,
                   lesson_status,payment_status,price,started_at,finished_at,
                   meeting_url,homework_required,homework_assigned
              FROM lessons
             WHERE user_id=? AND (start_time>=? OR (lesson_status='IN_PROGRESS' AND finished_at IS NULL))
               AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
             ORDER BY CASE WHEN lesson_status='IN_PROGRESS' AND finished_at IS NULL THEN 0 ELSE 1 END,start_time
             LIMIT 1
            """,
            (uid, now),
        ).fetchone()
        active_hw = conn.execute(
            "SELECT COUNT(*) n FROM homework WHERE user_id=? AND status NOT IN ('COMPLETED','CHECKED','REVIEWED','CANCELLED')",
            (uid,),
        ).fetchone()["n"]
        pending_payments = conn.execute(
            "SELECT COUNT(*) n,COALESCE(SUM(total_amount),0) amount FROM payments WHERE user_id=? AND status IN ('WAITING','PENDING')",
            (uid,),
        ).fetchone()
        unified_exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='unified_messages'").fetchone()
        unread = conn.execute(
            "SELECT COUNT(*) n FROM unified_messages WHERE student_id=? AND participant_type='STUDENT' AND direction='OUT' AND read_at IS NULL",
            (uid,),
        ).fetchone()["n"] if unified_exists else 0
        recent_result = conn.execute(
            """
            SELECT r.result,r.accuracy_percent,r.reviewed_at,h.title
              FROM homework_reviews r
              JOIN homework h ON h.id=r.homework_id
             WHERE h.user_id=?
             ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 1
            """,
            (uid,),
        ).fetchone()
        timezone = _student_timezone(user, conn)
        conn.close()
        lesson = _lesson_instant(_dict(next_lesson)) if next_lesson else None
        if lesson:
            lesson["ui_state"] = _lesson_state(lesson)
        return {
            "student": {
                "id": int(user["id"]),
                "name": user["name"],
                "grade": user["grade"],
                "study_goal": user["study_goal"],
                "main_subject": user["main_subject"],
                "extra_minutes_balance": int(user["extra_minutes_balance"] or 0),
                "bonus_lessons_earned": int(user["bonus_lessons_earned"] or 0),
                "board_url": user["board_url"],
                "timezone": timezone,
            },
            "next_lesson": lesson,
            "active_homework": int(active_hw or 0),
            "unread_messages": int(unread or 0),
            "payments_waiting": int(pending_payments["n"] or 0),
            "payments_waiting_amount": int(pending_payments["amount"] or 0),
            "recent_result": _dict(recent_result),
        }

    return _cached(("dashboard", uid), 8.0, load)


def schedule(user_id, limit=40):
    uid = int(user_id)
    limit = max(1, min(int(limit), 100))
    conn = connect()
    rows = conn.execute(
        """
        SELECT id,start_time,end_time,duration_minutes,subject,study_goal,
               lesson_status,payment_status,price,started_at,finished_at,
               actual_duration_minutes,meeting_url,cancelled_at,cancellation_reason
          FROM lessons
         WHERE user_id=?
         ORDER BY start_time DESC
         LIMIT ?
        """,
        (uid, limit),
    ).fetchall()
    conn.close()
    items = []
    for row in rows:
        item = _lesson_instant(dict(row))
        item["ui_state"] = _lesson_state(item)
        items.append(item)
    return items


def payments(user_id, limit=50):
    uid = int(user_id)
    limit = max(1, min(int(limit), 100))
    user = get_user(uid)
    if not user:
        return None
    conn = connect()
    rows = conn.execute(
        """
        SELECT id,payment_type,lessons_count,price_per_lesson,subtotal,
               discount_percent,package_discount_amount,promo_code,
               promo_discount_amount,total_amount,status,created_at,confirmed_at,
               lesson_id,minutes_total,base_duration_minutes,hourly_rate,subject,study_goal
          FROM payments
         WHERE user_id=?
         ORDER BY created_at DESC,id DESC
         LIMIT ?
        """,
        (uid, limit),
    ).fetchall()
    receipts = conn.execute(
        "SELECT id,payment_id,file_type,status,source_platform,created_at,reviewed_at FROM receipts WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 50",
        (uid,),
    ).fetchall()
    conn.close()
    return {
        "balance": {
            "extra_minutes": int(user["extra_minutes_balance"] or 0),
            "bonus_lessons": int(user["bonus_lessons_earned"] or 0),
        },
        "items": [dict(x) for x in rows],
        "receipts": [dict(x) for x in receipts],
    }


def profile(user_id):
    user = get_user(int(user_id))
    if not user or not user["active"]:
        return None
    allowed = [
        "name","grade","study_goal","main_subject","education_type","education_level",
        "extra_minutes_balance","bonus_lessons_earned","board_url",
        "ege_physics_rate","oge_physics_rate","oge_chemistry_rate",
        "olympiad_physics_rate","school_physics_rate","school_chemistry_rate",
    ]
    return {k: user[k] for k in allowed if k in user.keys()}


def conversation_for_student(user_id, limit=100):
    """Return canonical Adelia chat history and mark teacher messages as read."""
    from web_backend import unified_messaging as um
    from web_backend.unified_messages import conversation
    uid=int(user_id)
    conv=um.conversation(uid,'STUDENT',None)
    # For students, OUT means teacher -> student. The generic teacher-side
    # mark_read() handles IN, so mark the student-facing direction explicitly.
    now=datetime.now().isoformat(timespec='seconds')
    conn=connect()
    try:
        conn.execute("UPDATE unified_messages SET read_at=COALESCE(read_at,?),status=CASE WHEN status IN ('DELIVERED','SENT') THEN 'READ' ELSE status END WHERE conversation_id=? AND direction='OUT' AND read_at IS NULL",(now,int(conv['id'])))
        conn.execute("UPDATE unified_message_deliveries SET status='READ',read_at=COALESCE(read_at,?),updated_at=? WHERE message_id IN (SELECT id FROM unified_messages WHERE conversation_id=? AND direction='OUT' AND read_at IS NOT NULL) AND channel='WEB' AND recipient_type='STUDENT' AND status IN ('SENT','DELIVERED')",(now,now,int(conv['id'])))
        conn.commit()
    finally:
        conn.close()
    with _CACHE_LOCK:
        _CACHE.pop(("dashboard",uid),None)
    return conversation(uid,max(1,min(int(limit),200)))
