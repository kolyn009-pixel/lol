"""Shared web lesson entry flow for teacher and student.

Teacher entry opens the lesson. The factual timer starts after the first valid
student join or when the teacher explicitly confirms that a student who entered
through VK/Telegram/direct Telemost link has arrived.
"""
from __future__ import annotations

from database import connect, now_iso
from integrations.telemost_lifecycle import ensure_individual_conference
from web_backend.lesson_link_delivery import send_individual
from web_backend.lesson_workspace import start_lesson
from web_backend import telemost_settings

_BLOCKED={"CANCELLED","REJECTED","NO_SHOW","LATE_CANCELLED","SICKNESS","COMPLETED"}
_PAID_ACCESS={"PAID","FREE","WAIVED","COVERED"}
_VALID_RSVP={"UNKNOWN","GOING","MAYBE","NOT_GOING"}

def ensure_schema():
    conn=connect()
    conn.execute("""CREATE TABLE IF NOT EXISTS lesson_join_events(id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER NOT NULL,user_id INTEGER NOT NULL,actor_role TEXT NOT NULL,event_type TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'WEB',created_at TEXT NOT NULL,FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_join_events_lesson ON lesson_join_events(lesson_id,created_at)")
    cols={r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()}
    if "attendance_intent_status" not in cols:conn.execute("ALTER TABLE lessons ADD COLUMN attendance_intent_status TEXT NOT NULL DEFAULT 'UNKNOWN'")
    if "attendance_intent_at" not in cols:conn.execute("ALTER TABLE lessons ADD COLUMN attendance_intent_at TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_attendance_intent ON lessons(attendance_intent_status,attendance_intent_at)")
    conn.commit();conn.close()

def _row(lesson_id):
    ensure_schema();conn=connect();row=conn.execute("SELECT l.*,u.name,u.grade,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?",(int(lesson_id),)).fetchone();conn.close();return row

def _paid(row):return str(row["payment_status"] or "").upper() in _PAID_ACCESS or bool(row["is_trial"])

def _event_once(lesson_id,user_id,actor,event_type,source="WEB"):
    conn=connect();old=conn.execute("SELECT id FROM lesson_join_events WHERE lesson_id=? AND user_id=? AND actor_role=? AND event_type=? LIMIT 1",(int(lesson_id),int(user_id),actor,event_type)).fetchone()
    if old:conn.close();return False
    conn.execute("INSERT INTO lesson_join_events(lesson_id,user_id,actor_role,event_type,source,created_at) VALUES(?,?,?,?,?,?)",(int(lesson_id),int(user_id),actor,event_type,str(source or 'WEB').upper(),now_iso()));conn.commit();conn.close();return True

def set_attendance_intent(lesson_id,user_id,status):
    ensure_schema();lid=int(lesson_id);uid=int(user_id);value=str(status or "").upper()
    if value not in _VALID_RSVP:raise ValueError("invalid_attendance_intent")
    row=_row(lid)
    if not row or int(row["user_id"])!=uid:raise PermissionError("lesson_not_found")
    lesson_status=str(row["lesson_status"] or "").upper()
    if lesson_status in _BLOCKED or row["finished_at"]:raise ValueError("attendance_intent_closed")
    now=now_iso();conn=connect();conn.execute("UPDATE lessons SET attendance_intent_status=?,attendance_intent_at=?,updated_at=? WHERE id=? AND user_id=?",(value,now,now,lid,uid));conn.commit();conn.close()
    return {"status":"ok","lesson_id":lid,"attendance_intent_status":value,"attendance_intent_at":now}

def teacher_open_entry(lesson_id):
    ensure_schema();row=_row(lesson_id)
    if not row:return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in _BLOCKED or row["finished_at"]:return {"status":"invalid_status","lesson_status":status}
    if telemost_settings.auto_on_start():
        meeting=ensure_individual_conference(int(lesson_id))
        if meeting.get("status") not in {"ok","disabled"}:return {"status":"meeting_create_failed"}
    else:meeting={"status":"disabled_by_teacher","conference_id":None,"join_url":None,"reused":False}
    row=_row(lesson_id);already=bool(row["meeting_link_sent_at"]);opened=row["meeting_link_sent_at"] or now_iso()
    if not already:
        conn=connect();conn.execute("UPDATE lessons SET meeting_link_sent_at=?,updated_at=? WHERE id=? AND meeting_link_sent_at IS NULL",(opened,now_iso(),int(lesson_id)));conn.commit();conn.close();_event_once(lesson_id,row["user_id"],"TEACHER","ENTRY_OPENED","TEACHER")
        if meeting.get("status")=="ok":
            try:send_individual(int(lesson_id))
            except Exception:pass
    row=_row(lesson_id);return {"status":"ok","entry_open":True,"opened_at":opened,"started_at":row["started_at"],"meeting_url":row["meeting_url"] if meeting.get("status")=="ok" else None,"board_url":row["board_url"],"student_access":_paid(row),"already_open":already,"telemost":meeting,"telemost_auto_on_start":telemost_settings.auto_on_start()}

def teacher_mark_arrived(lesson_id):
    """Manual factual start for a student who joined outside the website/app."""
    row=_row(lesson_id)
    if not row:return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in _BLOCKED or row["finished_at"]:return {"status":"invalid_status","lesson_status":status}
    if not row["meeting_link_sent_at"]:return {"status":"entry_closed"}
    result=start_lesson(int(lesson_id))
    if result.get("status")!="ok":return result
    _event_once(lesson_id,row["user_id"],"TEACHER","STUDENT_ARRIVED","TEACHER")
    now=now_iso();conn=connect();conn.execute("UPDATE lessons SET attendance_intent_status='GOING',attendance_intent_at=COALESCE(attendance_intent_at,?),updated_at=? WHERE id=?",(now,now,int(lesson_id)));conn.commit();conn.close()
    return {"status":"ok","lesson_id":int(lesson_id),"started_at":result.get("started_at"),"already_started":bool(result.get("already_started"))}

def student_workspace(lesson_id,user_id):
    ensure_schema();row=_row(lesson_id)
    if not row or int(row["user_id"])!=int(user_id):return None
    status=str(row["lesson_status"] or "").upper();entry_open=bool(row["meeting_link_sent_at"]) and status not in _BLOCKED and not row["finished_at"];paid=_paid(row);meeting_visible=entry_open and paid
    return {"lesson":{"id":int(row["id"]),"subject":row["subject"],"study_goal":row["study_goal"],"start_time":row["start_time"],"end_time":row["end_time"],"duration_minutes":row["duration_minutes"],"lesson_status":row["lesson_status"],"payment_status":row["payment_status"],"started_at":row["started_at"],"finished_at":row["finished_at"],"entry_open":entry_open,"entry_opened_at":row["meeting_link_sent_at"],"payment_required":not paid,"attendance_intent_status":row["attendance_intent_status"],"attendance_intent_at":row["attendance_intent_at"]},"student":{"id":int(row["user_id"]),"name":row["name"],"grade":row["grade"]},"meeting_url":row["meeting_url"] if meeting_visible else None,"board_url":row["board_url"]}

def student_join(lesson_id,user_id):
    ensure_schema();row=_row(lesson_id)
    if not row or int(row["user_id"])!=int(user_id):return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in _BLOCKED or row["finished_at"]:return {"status":"invalid_status","lesson_status":status}
    if not row["meeting_link_sent_at"]:return {"status":"entry_closed"}
    if not _paid(row):return {"status":"payment_required","payment_status":row["payment_status"],"board_url":row["board_url"]}
    started=row["started_at"]
    if not started:
        result=start_lesson(int(lesson_id))
        if result.get("status")!="ok":return result
        started=result.get("started_at")
    first_join=_event_once(lesson_id,user_id,"STUDENT","JOIN_CLICKED","WEB")
    conn=connect();conn.execute("UPDATE lessons SET attendance_intent_status='GOING',attendance_intent_at=COALESCE(attendance_intent_at,?),updated_at=? WHERE id=?",(now_iso(),now_iso(),int(lesson_id)));conn.commit();conn.close()
    row=_row(lesson_id);return {"status":"ok","joined_at":now_iso(),"started_at":started,"meeting_url":row["meeting_url"],"board_url":row["board_url"],"first_join":first_join}

def join_events(lesson_id,limit=30):
    ensure_schema();conn=connect();rows=conn.execute("SELECT * FROM lesson_join_events WHERE lesson_id=? ORDER BY created_at DESC,id DESC LIMIT ?",(int(lesson_id),max(1,min(int(limit),100)))).fetchall();conn.close();return [dict(r) for r in rows]
