"""Read models for the authenticated student web cabinet.

All screens are built from TutorBot's production data model; no demo values are
kept here. The functions are intentionally read-only and lightweight so the PWA
can render quickly on mobile connections.
"""
from __future__ import annotations

from datetime import datetime
from time import monotonic
from threading import Lock

from database import connect, get_user

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
        now = datetime.now().isoformat(timespec="seconds")
        next_lesson = conn.execute(
            """
            SELECT id,start_time,end_time,duration_minutes,subject,study_goal,
                   lesson_status,payment_status,price,started_at,finished_at,
                   meeting_url,homework_required,homework_assigned
              FROM lessons
             WHERE user_id=? AND start_time>=?
               AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
             ORDER BY start_time
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
        conn.close()
        lesson = _dict(next_lesson)
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
        item = dict(row)
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
