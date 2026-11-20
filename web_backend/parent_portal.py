"""Stage 9 parent portal read model.

All reads are scoped through parent_student_links. A parent never receives data for
an unlinked student even if they guess an id. Private teacher notes, answers and
internal CRM fields are intentionally excluded from the parent read model.
"""
from __future__ import annotations
from core.lesson_time import lesson_timezone, schedule_datetime
from datetime import datetime, timedelta
from database import connect
from core import minute_balance
from web_backend.student_progress import topic_stats


def _limit(value, default=50, maximum=200):
    try:value=int(value)
    except Exception:value=default
    return max(1,min(value,maximum))


def parent(parent_id):
    conn=connect();row=conn.execute("SELECT id,name FROM parent_accounts WHERE id=? AND active=1",(int(parent_id),)).fetchone();conn.close();return dict(row) if row else None


def linked_students(parent_id):
    pid=int(parent_id);conn=connect();rows=conn.execute("""
      SELECT u.id,u.name,u.grade,u.study_goal,u.main_subject,u.active,
             COALESCE(u.education_type,'SCHOOL') education_type,
             u.education_level,l.notify_schedule
      FROM parent_student_links l
      JOIN users u ON u.id=l.student_id
      JOIN parent_accounts p ON p.id=l.parent_id
      WHERE l.parent_id=? AND p.active=1 AND u.active=1
      ORDER BY u.name,u.id
    """,(pid,)).fetchall();conn.close();return [dict(r) for r in rows]


def _linked_ids(parent_id, requested_ids=None):
    pid=int(parent_id);conn=connect()
    if requested_ids:
        ids=sorted({int(x) for x in requested_ids});marks=','.join('?' for _ in ids)
        rows=conn.execute(f"""SELECT l.student_id FROM parent_student_links l
          JOIN parent_accounts p ON p.id=l.parent_id JOIN users u ON u.id=l.student_id
          WHERE l.parent_id=? AND p.active=1 AND u.active=1 AND l.student_id IN ({marks})""",(pid,*ids)).fetchall()
    else:
        rows=conn.execute("""SELECT l.student_id FROM parent_student_links l
          JOIN parent_accounts p ON p.id=l.parent_id JOIN users u ON u.id=l.student_id
          WHERE l.parent_id=? AND p.active=1 AND u.active=1""",(pid,)).fetchall()
    conn.close();return {int(r['student_id']) for r in rows}


def _assert_link(parent_id,student_id):
    uid=int(student_id)
    if uid not in _linked_ids(parent_id,[uid]):raise PermissionError('student_not_linked')
    return uid


def _programs(conn,uid):
    try:rows=conn.execute("SELECT id,study_goal,subject,is_primary,approval_status FROM student_programs WHERE user_id=? AND active=1 ORDER BY is_primary DESC,id",(uid,)).fetchall()
    except Exception:rows=[]
    return [dict(r) for r in rows]


def _package_summary(conn,uid):
    try:rows=conn.execute("SELECT id,study_goal,subject,lessons_total,lessons_used,price_per_lesson,discount_percent,status,created_at FROM lesson_packages WHERE user_id=? ORDER BY id DESC LIMIT 30",(uid,)).fetchall()
    except Exception:rows=[]
    items=[dict(r) for r in rows];left=sum(max(0,int(x.get('lessons_total') or 0)-int(x.get('lessons_used') or 0)) for x in items if str(x.get('status') or '').upper()=='ACTIVE')
    return {'lessons_left':left,'items':items}


def _minute_balance(uid):
    try:
        b=minute_balance.get_balance(int(uid)) or {}
        return {'paid':int(b.get('paid') or 0),'bonus':int(b.get('bonus') or 0),'total':int(b.get('total') or 0)}
    except Exception:
        return {'paid':0,'bonus':0,'total':0}


def _progress(conn,uid):
    out={'topics':{'total':0,'started':0,'mastered':0,'average_mastery':0},'goal':None,'exam_results':[],'diagnostics':[],'homework':{'assigned':0,'submitted':0,'completed':0,'overdue':0,'average_score':None}}
    try:
        t=topic_stats(conn,uid);out['topics']={'total':t['total'],'started':t['started'],'mastered':t['mastered'],'average_mastery':t['avg_mastery']}
    except Exception:pass
    try:
        row=conn.execute("SELECT subject,study_goal,target_text,target_score,target_date FROM student_goals WHERE user_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(uid,)).fetchone();out['goal']=dict(row) if row else None
    except Exception:pass
    try:
        rows=conn.execute("SELECT subject,exam_type,exam_date,primary_score,test_score,max_score FROM exam_results WHERE user_id=? ORDER BY exam_date DESC,id DESC LIMIT 8",(uid,)).fetchall();out['exam_results']=[dict(r) for r in rows]
    except Exception:pass
    try:
        rows=conn.execute("SELECT mode,subject,study_goal,score,target_score,summary,created_at FROM learning_diagnostics WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 5",(uid,)).fetchall();out['diagnostics']=[dict(r) for r in rows]
    except Exception:pass
    try:
        h=conn.execute("""SELECT COUNT(*) total,SUM(CASE WHEN status IN ('ASSIGNED','REVISION') THEN 1 ELSE 0 END) assigned,SUM(CASE WHEN status IN ('SUBMITTED','UNDER_REVIEW','REVIEWED') THEN 1 ELSE 0 END) submitted,SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) completed,SUM(CASE WHEN deadline IS NOT NULL AND datetime(deadline)<datetime('now') AND status NOT IN ('COMPLETED','CANCELLED') THEN 1 ELSE 0 END) overdue FROM homework WHERE user_id=?""",(uid,)).fetchone()
        score=conn.execute("SELECT AVG(score_percent) s FROM homework_auto_results WHERE user_id=?",(uid,)).fetchone()
        out['homework']={'total':int(h['total'] or 0),'assigned':int(h['assigned'] or 0),'submitted':int(h['submitted'] or 0),'completed':int(h['completed'] or 0),'overdue':int(h['overdue'] or 0),'average_score':round(float(score['s']),1) if score and score['s'] is not None else None}
    except Exception:pass
    return out


def student(parent_id,student_id):
    uid=_assert_link(parent_id,student_id);conn=connect();u=conn.execute("SELECT id,name,grade,study_goal,main_subject,active,COALESCE(education_type,'SCHOOL') education_type,education_level FROM users WHERE id=?",(uid,)).fetchone()
    if not u:conn.close();return None
    payments=conn.execute("SELECT id,study_goal,subject,lessons_count,total_amount,status,created_at,confirmed_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 20",(uid,)).fetchall()
    waiting=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) amount FROM payments WHERE user_id=? AND status IN ('WAITING','PENDING','RECEIPT_SENT')",(uid,)).fetchone()
    completed=conn.execute("SELECT COUNT(*) c,COALESCE(SUM(price),0) amount FROM lessons WHERE user_id=? AND lesson_status='COMPLETED'",(uid,)).fetchone()
    upcoming=conn.execute("SELECT COUNT(*) c FROM lessons WHERE user_id=? AND start_time>=? AND lesson_status NOT IN ('CANCELLED','REJECTED','COMPLETED')",(uid,datetime.now(lesson_timezone()).replace(tzinfo=None).isoformat(timespec='seconds'))).fetchone()
    recent_lessons=conn.execute("SELECT id,start_time,duration_minutes,subject,study_goal,lesson_status,payment_status FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 12",(uid,)).fetchall()
    out={'student':dict(u),'programs':_programs(conn,uid),'payments':[dict(r) for r in payments],'payment_summary':{'waiting_count':int(waiting['c'] or 0),'waiting_amount':int(waiting['amount'] or 0)},'minute_balance':_minute_balance(uid),'lessons':{'completed':int(completed['c'] or 0),'completed_value':int(completed['amount'] or 0),'upcoming':int(upcoming['c'] or 0),'recent':[_schedule_times(dict(r)) for r in recent_lessons]},'packages':_package_summary(conn,uid),'progress':_progress(conn,uid)};conn.close();return out


def schedule(parent_id,student_id=None,days=45,limit=120):
    pid=int(parent_id)
    if student_id is not None:
        requested=[int(student_id)];linked=_linked_ids(pid,requested)
        if set(requested)!=linked:raise PermissionError('student_not_linked')
        uids=requested
    else:uids=sorted(_linked_ids(pid))
    if not uids:return []
    now=datetime.now(lesson_timezone()).replace(tzinfo=None);end=now+timedelta(days=max(1,min(int(days or 45),180)));start=now.isoformat(timespec='seconds');stop=end.isoformat(timespec='seconds');cap=_limit(limit,120,500);marks=','.join('?' for _ in uids);conn=connect();items=[]
    rows=conn.execute(f"""SELECT l.id,l.user_id,u.name,l.start_time,l.end_time,l.duration_minutes,l.subject,l.study_goal,l.lesson_status,l.payment_status,l.price FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.user_id IN ({marks}) AND l.start_time>=? AND l.start_time<? AND l.lesson_status NOT IN ('CANCELLED','REJECTED') ORDER BY l.start_time LIMIT ?""",(*uids,start,stop,cap)).fetchall()
    for row in rows:
        item=dict(row);item['kind']='INDIVIDUAL';items.append(item)
    try:
        rows=conn.execute(f"""SELECT gl.id,p.user_id,u.name,gl.start_time,gl.end_time,CAST((julianday(gl.end_time)-julianday(gl.start_time))*1440 AS INTEGER) duration_minutes,g.subject,g.study_goal,gl.status lesson_status,p.payment_status,g.name group_name,p.attendance_status FROM group_lesson_participants p JOIN group_lessons gl ON gl.id=p.lesson_id JOIN study_groups g ON g.id=gl.group_id JOIN users u ON u.id=p.user_id WHERE p.user_id IN ({marks}) AND gl.start_time>=? AND gl.start_time<? AND gl.status NOT IN ('CANCELLED','QUORUM_FAILED') ORDER BY gl.start_time LIMIT ?""",(*uids,start,stop,cap)).fetchall()
        for row in rows:
            item=dict(row);item['kind']='GROUP';item['name']=f"{item.pop('group_name')} · {item['name']}";items.append(item)
    except Exception:pass
    try:
        rows=conn.execute(f"""SELECT e.id,p.user_id,u.name,e.starts_at start_time,e.ends_at end_time,CAST((julianday(e.ends_at)-julianday(e.starts_at))*1440 AS INTEGER) duration_minutes,e.subject,NULL study_goal,e.status lesson_status,p.payment_status,e.title event_title,p.status registration_status,p.teacher_decision FROM open_event_participants p JOIN open_learning_events e ON e.id=p.event_id JOIN users u ON u.id=p.user_id WHERE p.user_id IN ({marks}) AND p.status='REGISTERED' AND e.starts_at>=? AND e.starts_at<? AND e.status NOT IN ('CANCELLED','CLOSED') ORDER BY e.starts_at LIMIT ?""",(*uids,start,stop,cap)).fetchall()
        for row in rows:
            item=dict(row);item['kind']='OPEN_EVENT';item['name']=f"{item.pop('event_title')} · {item['name']}";items.append(item)
    except Exception:pass
    conn.close();items.sort(key=lambda x:str(x.get('start_time') or ''));return [_schedule_times(x) for x in items[:cap]]


def dashboard(parent_id):
    pid=int(parent_id);p=parent(pid)
    if not p:return None
    students=linked_students(pid);uids=[int(x['id']) for x in students]
    if not uids:return {'parent':p,'students':[],'summary':{'students':0,'upcoming_lessons':0,'waiting_payments':0,'waiting_amount':0,'balance_minutes':0},'upcoming':[]}
    marks=','.join('?' for _ in uids);conn=connect();waiting=conn.execute(f"SELECT COUNT(*) c,COALESCE(SUM(total_amount),0) amount FROM payments WHERE user_id IN ({marks}) AND status IN ('WAITING','PENDING','RECEIPT_SENT')",uids).fetchone();conn.close();upcoming_items=schedule(pid,None,21,120)
    total_minutes=sum(_minute_balance(uid)['total'] for uid in uids)
    return {'parent':p,'students':students,'summary':{'students':len(students),'upcoming_lessons':len(upcoming_items),'waiting_payments':int(waiting['c'] or 0),'waiting_amount':int(waiting['amount'] or 0),'balance_minutes':int(total_minutes)},'upcoming':upcoming_items[:40]}


def _schedule_times(item):
    for key in ('start_time','end_time'):
        if item.get(key):item[key]=schedule_datetime(item[key]).isoformat(timespec='seconds')
    return item
