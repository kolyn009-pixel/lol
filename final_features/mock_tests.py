from __future__ import annotations
from datetime import datetime
import database
from learning import exam_results, curriculum
from . import schema


def assign(user_id, program_id, title, deadline=None, file_id=None, url=None, comment=None, actor=None):
    schema.initialize(); p=database.get_student_program(int(program_id)); now=datetime.now().isoformat(timespec='seconds'); c=database.connect()
    try:
        cur=c.execute('''INSERT INTO mock_tests(user_id,program_id,subject,exam_type,title,deadline,file_id,url,teacher_comment,status,assigned_by,assigned_at)
                         VALUES(?,?,?,?,?,?,?,?,?,'ASSIGNED',?,?)''',(int(user_id),int(program_id),p['subject'] if p else '',p['study_goal'] if p else 'EGE',title,deadline,file_id,url,comment,actor,now)); c.commit(); return cur.lastrowid
    finally:c.close()

def complete(mock_id, primary_score=None, test_score=None, duration_minutes=None, result_comment=None, topic_errors=None):
    schema.initialize(); c=database.connect(); now=datetime.now().isoformat(timespec='seconds')
    try:
        m=c.execute('SELECT * FROM mock_tests WHERE id=?',(int(mock_id),)).fetchone()
        if not m: raise ValueError('Пробник не найден')
        c.execute("UPDATE mock_tests SET status='REVIEWED',primary_score=?,test_score=?,duration_minutes=?,result_comment=?,reviewed_at=? WHERE id=?",(primary_score,test_score,duration_minutes,result_comment,now,int(mock_id)))
        for topic_id,severity,note in (topic_errors or []):
            c.execute('INSERT OR REPLACE INTO mock_test_topic_errors(mock_test_id,topic_id,severity,note) VALUES(?,?,?,?)',(int(mock_id),int(topic_id),severity,note))
            level='REVIEW' if severity in ('WEAK','MEDIUM') else 'LEARNING'
            # update using existing learning API after commit below
        c.commit()
    finally:c.close()
    if test_score is not None:
        exam_results.add(m['user_id'],m['subject'],test_score,primary_score=primary_score,exam_type=m['exam_type'],exam_date=now[:10],notes=result_comment)
    return True

def list_for_user(user_id, limit=30):
    schema.initialize(); c=database.connect()
    try:return c.execute('SELECT * FROM mock_tests WHERE user_id=? ORDER BY id DESC LIMIT ?',(int(user_id),int(limit))).fetchall()
    finally:c.close()
