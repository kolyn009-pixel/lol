"""Finalize an interactive homework review after auto-check and teacher overrides."""
from __future__ import annotations

from database import connect, now_iso
from web_backend.assessment import ensure_tables as ensure_assessment_tables
from web_backend.homework_notifications import enqueue

FINAL_RESULTS={"ACCEPTED","REVISION"}


def _latest_submission(conn, homework_id, user_id, attempt_number=None):
    if attempt_number not in (None, ""):
        return conn.execute(
            "SELECT * FROM homework_submissions WHERE homework_id=? AND user_id=? AND attempt_number=? ORDER BY id DESC LIMIT 1",
            (int(homework_id), int(user_id), int(attempt_number)),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM homework_submissions WHERE homework_id=? AND user_id=? ORDER BY attempt_number DESC,id DESC LIMIT 1",
        (int(homework_id), int(user_id)),
    ).fetchone()


def _score(conn, homework_id, user_id, attempt_number):
    rows=conn.execute(
        """
        SELECT r.task_id,r.is_correct,r.points_awarded,
               COALESCE(s.points,1) max_points,
               f.override_correct,f.override_points
          FROM homework_task_responses r
          LEFT JOIN homework_task_settings s
            ON s.homework_id=r.homework_id AND s.task_id=r.task_id
          LEFT JOIN homework_task_feedback f
            ON f.homework_id=r.homework_id AND f.task_id=r.task_id
           AND f.user_id=r.user_id AND f.attempt_number=r.attempt_number
         WHERE r.homework_id=? AND r.user_id=? AND r.attempt_number=?
         ORDER BY r.id
        """,
        (int(homework_id),int(user_id),int(attempt_number)),
    ).fetchall()
    total=earned=0.0; correct=checked=0
    for row in rows:
        max_points=float(row['max_points'] or 0)
        total+=max_points
        is_correct=row['override_correct'] if row['override_correct'] is not None else row['is_correct']
        points=row['override_points'] if row['override_points'] is not None else row['points_awarded']
        if points is not None: earned+=max(0.0,min(float(points),max_points if max_points>0 else float(points)))
        if is_correct is not None:
            checked+=1
            if int(is_correct): correct+=1
    percent=round((earned/total*100.0),1) if total>0 else 0.0
    return {'total_tasks':len(rows),'checked_tasks':checked,'correct_tasks':correct,'total_points':round(total,2),'earned_points':round(earned,2),'accuracy_percent':percent}


def finalize(homework_id,user_id,result,comment="",attempt_number=None):
    ensure_assessment_tables();result=str(result or '').upper()
    if result not in FINAL_RESULTS:return {'status':'invalid_result'}
    hid=int(homework_id);uid=int(user_id);comment=str(comment or '').strip()
    conn=connect()
    try:
        hw=conn.execute("SELECT h.*,u.name FROM homework h JOIN users u ON u.id=h.user_id WHERE h.id=? AND h.user_id=?",(hid,uid)).fetchone()
        if not hw:return {'status':'homework_not_found'}
        sub=_latest_submission(conn,hid,uid,attempt_number)
        if not sub:return {'status':'submission_not_found'}
        attempt=int(sub['attempt_number'] or 1);score=_score(conn,hid,uid,attempt);now=now_iso()
        existing=conn.execute("SELECT id FROM homework_reviews WHERE homework_id=? AND submission_id=? ORDER BY id DESC LIMIT 1",(hid,int(sub['id']))).fetchone()
        if existing:
            conn.execute("UPDATE homework_reviews SET result=?,tutor_comment=?,reviewed_at=?,total_tasks=?,correct_tasks=?,accuracy_percent=? WHERE id=?",(result,comment,now,score['total_tasks'],score['correct_tasks'],score['accuracy_percent'],int(existing['id'])))
            review_id=int(existing['id'])
        else:
            cur=conn.execute("INSERT INTO homework_reviews(homework_id,submission_id,result,tutor_comment,reviewed_at,total_tasks,correct_tasks,accuracy_percent) VALUES(?,?,?,?,?,?,?,?)",(hid,int(sub['id']),result,comment,now,score['total_tasks'],score['correct_tasks'],score['accuracy_percent']))
            review_id=int(cur.lastrowid)
        sub_status='REVIEWED' if result=='ACCEPTED' else 'REVISION'
        hw_status='COMPLETED' if result=='ACCEPTED' else 'REVISION'
        conn.execute("UPDATE homework_submissions SET status=?,reviewed_at=? WHERE id=?",(sub_status,now,int(sub['id'])))
        conn.execute("UPDATE homework SET status=?,reviewed_at=?,updated_at=? WHERE id=?",(hw_status,now,now,hid))
        conn.execute("UPDATE homework_auto_results SET review_id=?,score_percent=?,earned_points=?,total_points=?,correct_tasks=?,total_tasks=? WHERE homework_id=? AND user_id=? AND attempt_number=?",(review_id,score['accuracy_percent'],score['earned_points'],score['total_points'],score['correct_tasks'],score['total_tasks'],hid,uid,attempt))
        conn.commit()
    finally:
        conn.close()
    title=hw['title'] or 'Домашнее задание';accepted=result=='ACCEPTED'
    text=(f"✅ Домашняя работа «{title}» проверена\n\nРезультат: {score['accuracy_percent']:g}% · {score['earned_points']:g}/{score['total_points']:g} баллов" if accepted else f"📝 Домашняя работа «{title}» отправлена на доработку\n\nТекущий результат: {score['accuracy_percent']:g}% · {score['earned_points']:g}/{score['total_points']:g} баллов")
    if comment:text+=f"\n\nКомментарий преподавателя:\n{comment}"
    if not accepted:text+="\n\nМожно открыть ДЗ в Аделии и попробовать ещё раз 💜"
    enqueue(f"homework-review:{hid}:{uid}:{attempt}:{result}",'STUDENT','HOMEWORK_REVIEWED' if accepted else 'HOMEWORK_REVISION',text,uid,f"/app/?tab=homework&homework={hid}",'Открыть ДЗ',{'homework_id':hid,'attempt_number':attempt,'result':result,'score':score})
    return {'status':'ok','homework_id':hid,'attempt_number':attempt,'result':result,'review_id':review_id,**score}
