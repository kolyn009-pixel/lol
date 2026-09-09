"""Shared web lesson entry flow for teacher and student.

The teacher explicitly opens entry. Only then can the owning student join.
The first valid student join starts the canonical TutorBot lesson once and logs
an immutable join event. Telemost and Moyadoska URLs remain ordinary providers;
this module only coordinates access and lifecycle state.
"""
from __future__ import annotations
from database import connect, now_iso
from web_backend.lesson_workspace import start_lesson
_BLOCKED={"CANCELLED","REJECTED","NO_SHOW","LATE_CANCELLED","SICKNESS","COMPLETED"}

def ensure_schema():
    conn=connect();conn.execute("""CREATE TABLE IF NOT EXISTS lesson_join_events (id INTEGER PRIMARY KEY AUTOINCREMENT,lesson_id INTEGER NOT NULL,user_id INTEGER NOT NULL,actor_role TEXT NOT NULL,event_type TEXT NOT NULL,source TEXT NOT NULL DEFAULT 'WEB',created_at TEXT NOT NULL,FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""");conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_join_events_lesson ON lesson_join_events(lesson_id,created_at)");conn.commit();conn.close()

def _row(lesson_id):
    conn=connect();row=conn.execute("SELECT l.*,u.name,u.grade,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?",(int(lesson_id),)).fetchone();conn.close();return row

def _event_once(lesson_id,user_id,actor,event_type):
    conn=connect();old=conn.execute("SELECT id FROM lesson_join_events WHERE lesson_id=? AND user_id=? AND actor_role=? AND event_type=? LIMIT 1",(int(lesson_id),int(user_id),actor,event_type)).fetchone()
    if old:conn.close();return False
    conn.execute("INSERT INTO lesson_join_events(lesson_id,user_id,actor_role,event_type,created_at) VALUES(?,?,?,?,?)",(int(lesson_id),int(user_id),actor,event_type,now_iso()));conn.commit();conn.close();return True

def teacher_open_entry(lesson_id):
    ensure_schema();row=_row(lesson_id)
    if not row:return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in _BLOCKED or row["finished_at"]:return {"status":"invalid_status","lesson_status":status}
    already=bool(row["meeting_link_sent_at"]);opened=row["meeting_link_sent_at"] or now_iso()
    if not already:
        conn=connect();conn.execute("UPDATE lessons SET meeting_link_sent_at=?,updated_at=? WHERE id=? AND meeting_link_sent_at IS NULL",(opened,now_iso(),int(lesson_id)));conn.commit();conn.close();_event_once(lesson_id,row["user_id"],"TEACHER","ENTRY_OPENED")
    return {"status":"ok","entry_open":True,"opened_at":opened,"meeting_url":row["meeting_url"],"board_url":row["board_url"],"already_open":already}

def student_workspace(lesson_id,user_id):
    ensure_schema();row=_row(lesson_id)
    if not row or int(row["user_id"])!=int(user_id):return None
    status=str(row["lesson_status"] or "").upper();return {"lesson":{"id":int(row["id"]),"subject":row["subject"],"study_goal":row["study_goal"],"start_time":row["start_time"],"end_time":row["end_time"],"duration_minutes":row["duration_minutes"],"lesson_status":row["lesson_status"],"payment_status":row["payment_status"],"started_at":row["started_at"],"finished_at":row["finished_at"],"entry_open":bool(row["meeting_link_sent_at"]) and status not in _BLOCKED and not row["finished_at"],"entry_opened_at":row["meeting_link_sent_at"]},"student":{"id":int(row["user_id"]),"name":row["name"],"grade":row["grade"]},"meeting_url":row["meeting_url"] if row["meeting_link_sent_at"] else None,"board_url":row["board_url"] if row["meeting_link_sent_at"] else None}

def student_join(lesson_id,user_id):
    ensure_schema();row=_row(lesson_id)
    if not row or int(row["user_id"])!=int(user_id):return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in _BLOCKED or row["finished_at"]:return {"status":"invalid_status","lesson_status":status}
    if not row["meeting_link_sent_at"]:return {"status":"entry_closed"}
    started=row["started_at"]
    if not started:
        r=start_lesson(int(lesson_id))
        if r.get("status")!="ok":return r
        started=r.get("started_at")
    first_join=_event_once(lesson_id,user_id,"STUDENT","JOIN_CLICKED")
    return {"status":"ok","joined_at":now_iso(),"started_at":started,"meeting_url":row["meeting_url"],"board_url":row["board_url"],"first_join":first_join}

def join_events(lesson_id,limit=30):
    ensure_schema();conn=connect();rows=conn.execute("SELECT * FROM lesson_join_events WHERE lesson_id=? ORDER BY created_at DESC,id DESC LIMIT ?",(int(lesson_id),max(1,min(int(limit),100)))).fetchall();conn.close();return [dict(r) for r in rows]
