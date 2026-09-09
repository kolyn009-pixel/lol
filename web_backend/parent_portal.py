"""Stage 9 parent portal read model.

All reads are scoped through parent_student_links. A parent never receives data for
an unlinked student even if they guess an id. This module is intentionally read-only;
write actions will be added separately after parent web authentication is in place.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from database import connect


def _limit(value, default=50, maximum=200):
    try:value=int(value)
    except Exception:value=default
    return max(1,min(value,maximum))


def parent(parent_id):
    conn=connect();row=conn.execute("SELECT id,name,phone,telegram_id,telegram_username,active,created_at,updated_at FROM parent_accounts WHERE id=? AND active=1",(int(parent_id),)).fetchone();conn.close();return dict(row) if row else None


def linked_students(parent_id):
    pid=int(parent_id);conn=connect();rows=conn.execute("""
      SELECT u.id,u.name,u.grade,u.study_goal,u.main_subject,u.active,
             COALESCE(u.education_type,'SCHOOL') education_type,
             u.education_level,l.notify_schedule
      FROM parent_student_links l
      JOIN users u ON u.id=l.student_id
      WHERE l.parent_id=? AND u.active=1
      ORDER BY u.name,u.id
    """,(pid,)).fetchall();conn.close();return [dict(r) for r in rows]


def _assert_link(parent_id,student_id):
    pid=int(parent_id);uid=int(student_id);conn=connect();row=conn.execute("SELECT 1 FROM parent_student_links l JOIN parent_accounts p ON p.id=l.parent_id WHERE l.parent_id=? AND l.student_id=? AND p.active=1",(pid,uid)).fetchone();conn.close()
    if not row:raise PermissionError('student_not_linked')
    return uid


def _programs(conn,uid):
    try:rows=conn.execute("SELECT id,study_goal,subject,custom_hourly_rate,is_primary,approval_status FROM student_programs WHERE user_id=? AND active=1 ORDER BY is_primary DESC,id",(uid,)).fetchall()
    except Exception:rows=[]
    return [dict(r) for r in rows]


def _package_summary(conn,uid):
    try:rows=conn.execute("SELECT id,study_goal,subject,lessons_total,lessons_used,price_per_lesson,discount_percent,status,created_at FROM lesson_packages WHERE user_id=? ORDER BY id DESC LIMIT 30",(uid,)).fetchall()
    except Exception:rows=[]
    items=[dict(r) for r in rows];left=sum(max(0,int(x.get('lessons_total') or 0)-int(x.get('lessons_used') or 0)) for x in items if str(x.get('status') or '').upper()=='ACTIVE')
    return {'lessons_left':left,'items':items}


def student(parent_id,student_id):
    uid=_assert_link(parent_id,student_id);conn=connect();u=conn.execute("SELECT id,name,grade,study_goal,main_subject,active,COALESCE(education_type,'SCHOOL') education_type,education_level FROM users WHERE id=?",(uid,)).fetchone()
    if not u:conn.close();return None
    payments=conn.execute("SELECT id,study_goal,subject,lessons_count,total_amount,status,created_at,confirmed_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 20",(uid,)).fetchall()
    completed=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(price),0) amount FROM lessons WHERE user_id=? AND lesson_status='COMPLETED'",(uid,)).fetchone()
    upcoming=conn.execute("SELECT COUNT(*) c FROM lessons WHERE user_id=? AND start_time>=? AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')",(uid,datetime.now().isoformat(timespec='seconds'))).fetchone()
    out={'student':dict(u),'programs':_programs(conn,uid),'payments':[dict(r) for r in payments],'lessons':{'completed':int(completed['c'] or 0),'completed_value':int(completed['amount'] or 0),'upcoming':int(upcoming['c'] or 0)},'packages':_package_summary(conn,uid)};conn.close();return out


def schedule(parent_id,student_id=None,days=45,limit=120):
    pid=int(parent_id);uids=[int(student_id)] if student_id is not None else [int(x['id']) for x in linked_students(pid)]
    for uid in uids:_assert_link(pid,uid)
    if not uids:return []
    now=datetime.now();end=now+timedelta(days=max(1,min(int(days or 45),180)));marks=','.join('?' for _ in uids);params=[*uids,now.isoformat(timespec='seconds'),end.isoformat(timespec='seconds'),_limit(limit,120,500)];conn=connect();rows=conn.execute(f"""
      SELECT l.id,l.user_id,u.name,l.start_time,l.end_time,l.duration_minutes,l.subject,l.study_goal,l.lesson_status,l.payment_status,l.price
      FROM lessons l JOIN users u ON u.id=l.user_id
      WHERE l.user_id IN ({marks}) AND l.start_time>=? AND l.start_time<?
        AND l.lesson_status NOT IN ('CANCELLED','REJECTED')
      ORDER BY l.start_time LIMIT ?
    """,params).fetchall();conn.close();return [dict(r) for r in rows]


def dashboard(parent_id):
    pid=int(parent_id);p=parent(pid)
    if not p:return None
    students=linked_students(pid);uids=[int(x['id']) for x in students]
    if not uids:return {'parent':p,'students':[],'summary':{'students':0,'upcoming_lessons':0,'waiting_payments':0,'waiting_amount':0,'lessons_left':0},'upcoming':[]}
    marks=','.join('?' for _ in uids);now=datetime.now().isoformat(timespec='seconds');conn=connect();upcoming=conn.execute(f"SELECT COUNT(*) c FROM lessons WHERE user_id IN ({marks}) AND start_time>=? AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')",(*uids,now)).fetchone();waiting=conn.execute(f"SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) amount FROM payments WHERE user_id IN ({marks}) AND status IN ('WAITING','PENDING')",uids).fetchone();left=conn.execute(f"SELECT COALESCE(SUM(CASE WHEN status='ACTIVE' THEN lessons_total-lessons_used ELSE 0 END),0) c FROM lesson_packages WHERE user_id IN ({marks})",uids).fetchone();conn.close();return {'parent':p,'students':students,'summary':{'students':len(students),'upcoming_lessons':int(upcoming['c'] or 0),'waiting_payments':int(waiting['c'] or 0),'waiting_amount':int(waiting['amount'] or 0),'lessons_left':int(left['c'] or 0)},'upcoming':schedule(pid,None,21,40)}
