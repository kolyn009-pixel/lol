"""Teacher lesson workspace backed by TutorBot's canonical lifecycle.

The website must not maintain a second lesson-finishing implementation. Finish
operations are delegated to core.lesson_lifecycle/database.finish_lesson so the
same minute accounting, bonus/underwork logic and downstream post-lesson flow
stay authoritative for WEB, Telegram and VK.
"""
from database import connect, now_iso, get_lesson
from core import lesson_lifecycle


def _ensure_workspace_schema(conn):
    """Keep lesson cards readable even on older production databases."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS lesson_notes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            user_id INTEGER,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_notes_lesson ON lesson_notes(lesson_id,created_at)")
    conn.commit()


def _finished_payload(lesson, already_finished=False):
    return {
        "status":"ok",
        "already_finished":bool(already_finished),
        "finished_at":lesson["finished_at"],
        "started_at":lesson["started_at"],
        "lesson_status":lesson["lesson_status"],
        "actual_duration_minutes":lesson["actual_duration_minutes"],
        "extra_minutes":lesson["extra_minutes"],
        "underworked_minutes":lesson["underworked_minutes"],
        "payment_status":lesson["payment_status"],
        "channel":"WEB",
        "post_lesson_required":True,
    }


def start_lesson(lesson_id):
    """Start once; repeated WEB clicks return the existing start timestamp."""
    lesson_id=int(lesson_id)
    conn=connect();row=conn.execute("SELECT * FROM lessons WHERE id=?",(lesson_id,)).fetchone()
    if not row:conn.close();return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in {"CANCELLED","REJECTED","NO_SHOW","LATE_CANCELLED","SICKNESS","COMPLETED"}:
        conn.close();return {"status":"invalid_status","lesson_status":status}
    if row["finished_at"]:
        conn.close();return {"status":"already_finished"}
    if row["started_at"]:
        started=row["started_at"]
        if status!="IN_PROGRESS":
            conn.execute("UPDATE lessons SET lesson_status='IN_PROGRESS',updated_at=? WHERE id=?",(now_iso(),lesson_id));conn.commit()
        conn.close();return {"status":"ok","started_at":started,"lesson_status":"IN_PROGRESS","channel":"WEB","already_started":True}
    started=now_iso();conn.execute("UPDATE lessons SET started_at=?,lesson_status='IN_PROGRESS',updated_at=? WHERE id=? AND started_at IS NULL AND finished_at IS NULL",(started,now_iso(),lesson_id));conn.commit();fresh=conn.execute("SELECT started_at,lesson_status,finished_at FROM lessons WHERE id=?",(lesson_id,)).fetchone();conn.close()
    if fresh["finished_at"]:return {"status":"already_finished"}
    return {"status":"ok","started_at":fresh["started_at"] or started,"lesson_status":fresh["lesson_status"],"channel":"WEB","already_started":bool(fresh["started_at"] and fresh["started_at"]!=started)}


def finish_lesson(lesson_id,attendance_status="PRESENT",tutor_comment=None,mode="NOW"):
    """Finish through TutorBot once; repeated clicks return the persisted result."""
    lesson_id=int(lesson_id);lesson=get_lesson(lesson_id)
    if not lesson:return {"status":"not_found"}
    if not lesson["started_at"]:return {"status":"not_started"}
    if lesson["finished_at"]:return _finished_payload(lesson,True)
    try:result=(lesson_lifecycle.finish_at_plan(lesson_id) if str(mode).upper()=="PLAN" else lesson_lifecycle.finish_now(lesson_id))
    except Exception as exc:
        latest=get_lesson(lesson_id)
        if latest and latest["finished_at"]:return _finished_payload(latest,True)
        return {"status":"error","detail":str(exc)}
    conn=connect();comment=str(tutor_comment or "").strip();conn.execute("UPDATE lessons SET attendance_status=COALESCE(?,attendance_status),tutor_comment=CASE WHEN ? IS NULL OR ?='' THEN tutor_comment ELSE ? END,updated_at=? WHERE id=?",(str(attendance_status or "PRESENT").upper(),comment or None,comment,comment or None,now_iso(),lesson_id));conn.commit();conn.close();out=dict(result or {});out.update({"status":"ok","channel":"WEB","post_lesson_required":True,"already_finished":False});return out


def finish_preview(lesson_id):
    try:
        info,actual_at_plan,missing=lesson_lifecycle.finish_preview(int(lesson_id));return {"status":"ok","actual_at_plan":actual_at_plan,"missing_minutes":missing,"late_minutes":info["late"],"early_minutes":info["early"],"planned_minutes":info["duration"]}
    except Exception as exc:return {"status":"error","detail":str(exc)}


def workspace(lesson_id):
    conn=connect();_ensure_workspace_schema(conn)
    row=conn.execute("""SELECT l.*,u.name,u.grade,u.telegram_username,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(int(lesson_id),)).fetchone()
    if not row:conn.close();return None
    hw=conn.execute("SELECT * FROM homework WHERE user_id=? ORDER BY assigned_at DESC LIMIT 5",(int(row['user_id']),)).fetchall()
    notes=conn.execute("SELECT id,lesson_id,user_id,text,created_at FROM lesson_notes WHERE lesson_id=? ORDER BY created_at,id",(int(lesson_id),)).fetchall()
    conn.close()
    preview=finish_preview(int(lesson_id)) if row["started_at"] and not row["finished_at"] else None
    return {"lesson":dict(row),"homework":[dict(x) for x in hw],"notes":[dict(x) for x in notes],"finish_preview":preview}
