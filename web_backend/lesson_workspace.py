"""Teacher lesson workspace backed by TutorBot's canonical lifecycle.

The website must not maintain a second lesson-finishing implementation. Finish
operations are delegated to core.lesson_lifecycle/database.finish_lesson so the
same minute accounting, bonus/underwork logic and downstream post-lesson flow
stay authoritative for WEB, Telegram and VK.
"""
from database import connect, now_iso, get_lesson
from core import lesson_lifecycle


def start_lesson(lesson_id):
    """Start a lesson using the same state conventions as TutorBot.

    TutorBot currently has no separate channel-neutral start helper, so this
    performs the minimal canonical transition only: CONFIRMED -> IN_PROGRESS
    and sets started_at once. All finish/accounting logic remains delegated to
    TutorBot's existing lifecycle.
    """
    lesson_id=int(lesson_id)
    conn=connect(); row=conn.execute("SELECT * FROM lessons WHERE id=?",(lesson_id,)).fetchone()
    if not row: conn.close(); return {"status":"not_found"}
    status=str(row["lesson_status"] or "").upper()
    if status in {"CANCELLED","REJECTED","NO_SHOW","LATE_CANCELLED","SICKNESS","COMPLETED"}:
        conn.close(); return {"status":"invalid_status","lesson_status":status}
    if row["finished_at"]:
        conn.close(); return {"status":"already_finished"}
    started=row["started_at"] or now_iso()
    conn.execute("UPDATE lessons SET started_at=?,lesson_status='IN_PROGRESS',updated_at=? WHERE id=?",(started,now_iso(),lesson_id))
    conn.commit(); conn.close()
    return {"status":"ok","started_at":started,"lesson_status":"IN_PROGRESS","channel":"WEB"}


def finish_lesson(lesson_id,attendance_status="PRESENT",tutor_comment=None,mode="NOW"):
    """Finish via TutorBot's canonical database.finish_lesson path.

    mode=NOW finishes at current time; PLAN uses the planned end time, matching
    the existing Telegram teacher-end workflow.
    """
    lesson_id=int(lesson_id)
    lesson=get_lesson(lesson_id)
    if not lesson: return {"status":"not_found"}
    if not lesson["started_at"]: return {"status":"not_started"}
    if lesson["finished_at"]: return {"status":"already_finished"}
    try:
        result=(lesson_lifecycle.finish_at_plan(lesson_id) if str(mode).upper()=="PLAN" else lesson_lifecycle.finish_now(lesson_id))
    except Exception as exc:
        return {"status":"error","detail":str(exc)}
    # Non-financial metadata can be safely layered on top of canonical finish.
    conn=connect()
    conn.execute("UPDATE lessons SET attendance_status=COALESCE(?,attendance_status),tutor_comment=CASE WHEN ? IS NULL OR ?='' THEN tutor_comment ELSE ? END,updated_at=? WHERE id=?",(
        str(attendance_status or "PRESENT").upper(),
        str(tutor_comment or "").strip() or None,
        str(tutor_comment or "").strip(),
        str(tutor_comment or "").strip() or None,
        now_iso(),lesson_id))
    conn.commit(); conn.close()
    out=dict(result or {})
    out.update({"status":"ok","channel":"WEB","post_lesson_required":True})
    return out


def finish_preview(lesson_id):
    try:
        info,actual_at_plan,missing=lesson_lifecycle.finish_preview(int(lesson_id))
        return {"status":"ok","actual_at_plan":actual_at_plan,"missing_minutes":missing,"late_minutes":info["late"],"early_minutes":info["early"],"planned_minutes":info["duration"]}
    except Exception as exc:
        return {"status":"error","detail":str(exc)}


def workspace(lesson_id):
    conn=connect(); row=conn.execute("""SELECT l.*,u.name,u.grade,u.telegram_username,u.board_url FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(int(lesson_id),)).fetchone()
    if not row: conn.close(); return None
    hw=conn.execute("SELECT * FROM homework WHERE user_id=? ORDER BY assigned_at DESC LIMIT 5",(int(row['user_id']),)).fetchall()
    notes=conn.execute("SELECT * FROM lesson_notes WHERE lesson_id=? ORDER BY created_at",(int(lesson_id),)).fetchall()
    conn.close()
    preview=finish_preview(int(lesson_id)) if row["started_at"] and not row["finished_at"] else None
    return {"lesson":dict(row),"homework":[dict(x) for x in hw],"notes":[dict(x) for x in notes],"finish_preview":preview}
