"""Channel-neutral lesson workspace actions for the teacher portal.

This module only owns lifecycle timestamps/state. Existing TutorBot post-lesson
processing remains authoritative for charging, homework and notifications and
will be wired through a shared core service before production enablement.
"""
from datetime import datetime
from database import connect, now_iso


def start_lesson(lesson_id):
    conn=connect(); row=conn.execute("SELECT * FROM lessons WHERE id=?",(int(lesson_id),)).fetchone()
    if not row: conn.close(); return {"status":"not_found"}
    if row['lesson_status']=='CANCELLED': conn.close(); return {"status":"cancelled"}
    if row['finished_at'] if 'finished_at' in row.keys() else None: conn.close(); return {"status":"already_finished"}
    started=(row['started_at'] if 'started_at' in row.keys() else None) or now_iso()
    conn.execute("UPDATE lessons SET started_at=?,lesson_status='IN_PROGRESS',updated_at=? WHERE id=?",(started,now_iso(),int(lesson_id)))
    conn.commit(); conn.close(); return {"status":"ok","started_at":started}


def finish_lesson(lesson_id,attendance_status="PRESENT",tutor_comment=None):
    conn=connect(); row=conn.execute("SELECT * FROM lessons WHERE id=?",(int(lesson_id),)).fetchone()
    if not row: conn.close(); return {"status":"not_found"}
    started=row['started_at'] if 'started_at' in row.keys() else None
    if not started: conn.close(); return {"status":"not_started"}
    if row['finished_at'] if 'finished_at' in row.keys() else None: conn.close(); return {"status":"already_finished"}
    finished=now_iso()
    try: minutes=max(0,int((datetime.fromisoformat(finished)-datetime.fromisoformat(started)).total_seconds()//60))
    except Exception: minutes=int(row['duration_minutes'] or 0)
    planned=int(row['duration_minutes'] or 0); extra=max(0,minutes-planned); under=max(0,planned-minutes)
    conn.execute("""UPDATE lessons SET finished_at=?,actual_duration_minutes=?,extra_minutes=?,underworked_minutes=?,attendance_status=?,tutor_comment=COALESCE(?,tutor_comment),lesson_status='COMPLETED',updated_at=? WHERE id=?""",(finished,minutes,extra,under,str(attendance_status or 'PRESENT').upper(),str(tutor_comment).strip() if tutor_comment else None,now_iso(),int(lesson_id)))
    conn.commit(); conn.close()
    return {"status":"ok","finished_at":finished,"actual_duration_minutes":minutes,"extra_minutes":extra,"underworked_minutes":under,"post_lesson_required":True}


def workspace(lesson_id):
    conn=connect(); row=conn.execute("""SELECT l.*,u.name,u.grade,u.telegram_username FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.id=?""",(int(lesson_id),)).fetchone()
    if not row: conn.close(); return None
    hw=conn.execute("SELECT * FROM homework WHERE user_id=? ORDER BY assigned_at DESC LIMIT 5",(int(row['user_id']),)).fetchall()
    notes=conn.execute("SELECT * FROM lesson_notes WHERE lesson_id=? ORDER BY created_at",(int(lesson_id),)).fetchall()
    conn.close(); return {"lesson":dict(row),"homework":[dict(x) for x in hw],"notes":[dict(x) for x in notes]}
