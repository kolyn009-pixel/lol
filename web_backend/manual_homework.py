"""Manual homework submission from the student web cabinet.

Manual assignments do not have structured task responses, but they still use the
same canonical homework_submissions/review lifecycle as interactive homework.
"""
from __future__ import annotations

from database import connect, now_iso
from web_backend.assessment import homework_lifecycle
from web_backend.homework_notifications import enqueue


def submit(homework_id, user_id, comment=""):
    hid=int(homework_id);uid=int(user_id);comment=str(comment or '').strip()
    life=homework_lifecycle(hid,uid)
    if not life.get('exists'):return {'status':'homework_not_found'}
    if not life.get('can_submit'):return {'status':life.get('reason') or 'submission_not_allowed'}
    conn=connect()
    hw=conn.execute("SELECT id,user_id,title,homework_type FROM homework WHERE id=? AND user_id=?",(hid,uid)).fetchone()
    if not hw:conn.close();return {'status':'homework_not_found'}
    if str(hw['homework_type'] or '').upper() in {'INTERACTIVE','EXTERNAL'}:
        conn.close();return {'status':'invalid_homework_mode'}
    attempt=int(life.get('next_attempt_number') or 1);now=now_iso()
    try:
        cur=conn.execute("INSERT INTO homework_submissions(homework_id,user_id,attempt_number,student_comment,status,submitted_from,submitted_at) VALUES(?,?,?,?, 'SUBMITTED','WEB_MANUAL',?)",(hid,uid,attempt,comment or None,now))
        sid=int(cur.lastrowid)
        conn.execute("UPDATE homework SET status='SUBMITTED',submitted_at=?,updated_at=? WHERE id=?",(now,now,hid))
        conn.commit()
    except Exception:
        conn.rollback();conn.close();raise
    conn.close()
    enqueue(f'manual-submitted:{hid}:{uid}:{attempt}','TEACHER','HOMEWORK_SUBMITTED',f"📝 Ученик отметил ДЗ «{hw['title'] or 'Домашнее задание'}» выполненным\n\nПопытка: {attempt}"+(f"\nКомментарий: {comment}" if comment else ''),uid,f'/teacher/?homework={hid}&student={uid}&attempt={attempt}','Открыть работу',{'homework_id':hid,'student_id':uid,'attempt_number':attempt,'submission_id':sid})
    return {'status':'ok','homework_id':hid,'attempt_number':attempt,'submission_id':sid}
