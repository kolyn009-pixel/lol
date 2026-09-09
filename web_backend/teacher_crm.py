"""Teacher CRM read models and safe student profile mutations."""
from __future__ import annotations

from datetime import datetime, timedelta

from database import connect, get_user, now_iso

RATE_FIELDS = {
    "ege_physics_rate", "oge_physics_rate", "oge_chemistry_rate",
    "olympiad_physics_rate", "school_physics_rate", "school_chemistry_rate",
}
PROFILE_FIELDS = {
    "grade", "study_goal", "main_subject", "phone", "board_url",
    "parent_name", "parent_phone", "education_type", "education_level",
}
EDITABLE_FIELDS = RATE_FIELDS | PROFILE_FIELDS


def _dict(row):
    return dict(row) if row else None


def _iso(value, fallback):
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value)).isoformat(timespec="seconds")
    except Exception:
        return fallback


def schedule(start=None, end=None, limit=300):
    now = datetime.now()
    monday = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
    start = _iso(start, monday.isoformat(timespec="seconds"))
    end = _iso(end, (monday + timedelta(days=7)).isoformat(timespec="seconds"))
    limit = max(1, min(int(limit), 500))
    conn = connect()
    rows = conn.execute(
        """
        SELECT l.id,l.user_id,l.start_time,l.end_time,l.duration_minutes,
               l.subject,l.study_goal,l.lesson_status,l.payment_status,l.price,
               l.started_at,l.finished_at,l.actual_duration_minutes,
               l.meeting_link_sent_at,u.name,u.grade,u.board_url
          FROM lessons l
          JOIN users u ON u.id=l.user_id
         WHERE l.start_time>=? AND l.start_time<?
         ORDER BY l.start_time,l.id
         LIMIT ?
        """,
        (start, end, limit),
    ).fetchall()
    conn.close()
    return {"start": start, "end": end, "items": [dict(r) for r in rows]}


def student(user_id):
    uid = int(user_id)
    user = get_user(uid)
    if not user:
        return None
    conn = connect()
    now = datetime.now().isoformat(timespec="seconds")
    stats = conn.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM lessons WHERE user_id=? AND lesson_status='COMPLETED') lessons_completed,
          (SELECT COUNT(*) FROM homework WHERE user_id=? AND status IN ('ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION')) homework_open,
          (SELECT COUNT(*) FROM homework_submissions WHERE user_id=? AND status='SUBMITTED') submissions_waiting,
          (SELECT COALESCE(SUM(total_amount),0) FROM payments WHERE user_id=? AND status IN ('WAITING','PENDING')) payment_waiting
        """,
        (uid, uid, uid, uid),
    ).fetchone()
    next_lesson = conn.execute(
        """
        SELECT id,start_time,end_time,duration_minutes,subject,study_goal,
               lesson_status,payment_status,price
          FROM lessons
         WHERE user_id=? AND start_time>=?
           AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')
         ORDER BY start_time LIMIT 1
        """,
        (uid, now),
    ).fetchone()
    recent = conn.execute(
        """
        SELECT id,start_time,duration_minutes,actual_duration_minutes,subject,
               study_goal,lesson_status,payment_status,price
          FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 8
        """,
        (uid,),
    ).fetchall()
    conn.close()
    allowed = [
        "id","name","grade","study_goal","main_subject","telegram_username",
        "phone","board_url","parent_name","parent_phone","education_type",
        "education_level","extra_minutes_balance","bonus_lessons_earned",
        *sorted(RATE_FIELDS),
    ]
    profile = {k: user[k] for k in allowed if k in user.keys()}
    return {
        "student": profile,
        "stats": dict(stats),
        "next_lesson": _dict(next_lesson),
        "recent_lessons": [dict(r) for r in recent],
    }


def update_student(user_id, fields):
    uid = int(user_id)
    user = get_user(uid)
    if not user:
        return {"status": "student_not_found"}
    fields = fields or {}
    updates = []
    params = []
    for key, raw in fields.items():
        if key not in EDITABLE_FIELDS or key not in user.keys():
            continue
        value = raw
        if key in RATE_FIELDS:
            if value in (None, ""):
                value = None
            else:
                try:
                    value = int(value)
                except Exception:
                    return {"status": "invalid_rate", "field": key}
                if value < 0 or value > 100000:
                    return {"status": "invalid_rate", "field": key}
        elif key == "grade":
            if value in (None, ""):
                value = None
            else:
                try:
                    value = int(value)
                except Exception:
                    return {"status": "invalid_grade"}
                if value < 1 or value > 14:
                    return {"status": "invalid_grade"}
        else:
            value = str(value or "").strip() or None
        updates.append(f"{key}=?")
        params.append(value)
    if not updates:
        return {"status": "ok", "changed": 0}
    if "updated_at" in user.keys():
        updates.append("updated_at=?")
        params.append(now_iso())
    params.append(uid)
    conn = connect()
    conn.execute(f"UPDATE users SET {','.join(updates)} WHERE id=?", params)
    conn.commit()
    conn.close()
    return {"status": "ok", "changed": 1, "student": student(uid)["student"]}
