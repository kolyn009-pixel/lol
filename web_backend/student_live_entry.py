"""Student live-entry helpers for group lessons and open events.

A successful app/web entry is the canonical automatic attendance signal. Access
is checked first; only admitted/paid participants can generate JOIN events.
Repeated opens while already present are idempotent. Manual teacher attendance
uses the same timeline and remains available as a fallback.

For group lessons and open events the factual timer starts when the first
admitted student presses "Join". Merely opening access as a teacher does not
start that timer.
"""
from __future__ import annotations

import database
from web_backend import attendance_tracking, group_lesson_access, group_portal


def _mark_event_actual_start(event_id):
    eid=int(event_id);now=database.now_iso();c=database.connect();cols={r[1] for r in c.execute("PRAGMA table_info(open_learning_events)").fetchall()}
    if "started_at" not in cols:c.execute("ALTER TABLE open_learning_events ADD COLUMN started_at TEXT")
    c.execute("UPDATE open_learning_events SET started_at=COALESCE(started_at,?),updated_at=? WHERE id=?",(now,now,eid));c.commit();row=c.execute("SELECT started_at FROM open_learning_events WHERE id=?",(eid,)).fetchone();c.close();return row["started_at"] if row else now


def group_entry(lesson_id, user_id, source="APP"):
    lid=int(lesson_id);uid=int(user_id)
    access=group_lesson_access.student_lesson_access(lid,uid)
    if not access.get("links_visible") or not access.get("telemost_join_url"):
        raise PermissionError("group_lesson_not_open")
    started_at=group_lesson_access.mark_actual_start(lid,uid)
    result=attendance_tracking.record(
        "GROUP_LESSON",lid,uid,"JOIN",source=str(source or "APP").upper()
    )
    summary=attendance_tracking.summary("GROUP_LESSON",lid,uid)
    return {
        "status":"ok",
        "lesson_id":lid,
        "started_at":started_at,
        "meeting_url":access.get("telemost_join_url"),
        "board_url":access.get("board_url"),
        "attendance":summary,
        "join_event":result,
    }


def event_entry(event_id, user_id, source="APP"):
    eid=int(event_id);uid=int(user_id)
    access=group_portal.open_event_access(eid,uid)
    if not access.get("allowed") or not access.get("meeting_url"):
        raise PermissionError("event_not_open")
    started_at=_mark_event_actual_start(eid)
    result=attendance_tracking.record(
        "OPEN_EVENT",eid,uid,"JOIN",source=str(source or "APP").upper()
    )
    summary=attendance_tracking.summary("OPEN_EVENT",eid,uid)
    return {
        "status":"ok",
        "event_id":eid,
        "started_at":started_at,
        "meeting_url":access.get("meeting_url"),
        "board_url":access.get("board_url"),
        "attendance":summary,
        "join_event":result,
    }


def leave_group(lesson_id,user_id,source="APP"):
    lid=int(lesson_id);uid=int(user_id)
    result=attendance_tracking.record(
        "GROUP_LESSON",lid,uid,"LEAVE",source=str(source or "APP").upper()
    )
    return {"status":"ok","lesson_id":lid,"attendance":attendance_tracking.summary("GROUP_LESSON",lid,uid),"leave_event":result}


def leave_event(event_id,user_id,source="APP"):
    eid=int(event_id);uid=int(user_id)
    result=attendance_tracking.record(
        "OPEN_EVENT",eid,uid,"LEAVE",source=str(source or "APP").upper()
    )
    return {"status":"ok","event_id":eid,"attendance":attendance_tracking.summary("OPEN_EVENT",eid,uid),"leave_event":result}
