"""Teacher web-cabinet queries and safe mutations over TutorBot's database."""
from datetime import datetime,timedelta
from time import monotonic
from threading import Lock
from database import connect,create_homework,get_user
from core import payment_wait_control
_CACHE={};_CACHE_LOCK=Lock()
def _dict(row):return dict(row) if row else None
def _cached(key,ttl,loader):
 now=monotonic()
 with _CACHE_LOCK:
  item=_CACHE.get(key)
  if item and now-item[0]<ttl:return item[1]
 value=loader()
 with _CACHE_LOCK:_CACHE[key]=(now,value)
 return value
def _week_bounds(now):
 monday=now.date()-timedelta(days=now.weekday());start=datetime.combine(monday,datetime.min.time());end=start+timedelta(days=7);return start.isoformat(timespec='seconds'),end.isoformat(timespec='seconds')
def dashboard():
 def load():
  from web_backend import lesson_join
  lesson_join.ensure_schema();payment_wait_control.ensure_schema();conn=connect();now=datetime.now();today=now.date().isoformat();tomorrow=(now.date()+timedelta(days=1)).date().isoformat();week_start,week_end=_week_bounds(now)
  counters=conn.execute("SELECT (SELECT COUNT(*) FROM users WHERE active=1) students,(SELECT COUNT(*) FROM lessons WHERE start_time>=? AND start_time<? AND lesson_status!='CANCELLED') lessons_today,(SELECT COUNT(*) FROM homework_submissions WHERE status='SUBMITTED') submissions",(today,tomorrow)).fetchone();expected_week=conn.execute("SELECT COALESCE(SUM(COALESCE(price,0)),0) n FROM lessons WHERE start_time>=? AND start_time<? AND lesson_status NOT IN ('CANCELLED','REJECTED','SICKNESS') AND payment_status IN ('AWAITING_PAYMENT','UNPAID')",(week_start,week_end)).fetchone()['n'];next_lessons=conn.execute("SELECT l.id,l.start_time,l.end_time,l.subject,l.study_goal,l.lesson_status,l.payment_status,l.price,l.attendance_intent_status,l.attendance_intent_at,l.meeting_url,l.meeting_link_sent_at,u.id user_id,u.name,u.grade,pw.risk_notified_at payment_risk_notified_at,pw.teacher_wait_confirmed_at payment_wait_confirmed_at FROM lessons l JOIN users u ON u.id=l.user_id LEFT JOIN lesson_payment_wait_overrides pw ON pw.lesson_id=l.id WHERE l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','COMPLETED') ORDER BY l.start_time LIMIT 8",(now.isoformat(timespec='seconds'),)).fetchall();pending=conn.execute("SELECT s.id submission_id,s.homework_id,s.submitted_at,s.student_comment,h.title,h.subject,u.id user_id,u.name FROM homework_submissions s JOIN homework h ON h.id=s.homework_id JOIN users u ON u.id=s.user_id WHERE s.status='SUBMITTED' ORDER BY s.submitted_at ASC LIMIT 12").fetchall();conn.close();return {'stats':{'students':counters['students'],'lessons_today':counters['lessons_today'],'submissions':counters['submissions'],'unpaid':expected_week,'expected_week':expected_week},'next_lessons':[_dict(x) for x in next_lessons],'pending_reviews':[_dict(x) for x in pending]}
 return _cached('dashboard',8.0,load)
def students():
 def load():
  conn=connect();now=datetime.now().isoformat(timespec='seconds');rows=conn.execute("SELECT u.id,u.name,u.grade,u.study_goal,u.main_subject,u.telegram_username,MIN(CASE WHEN l.start_time>=? AND l.lesson_status NOT IN ('CANCELLED','COMPLETED') THEN l.start_time END) next_lesson,COUNT(DISTINCT CASE WHEN h.status IN ('ASSIGNED','SUBMITTED','UNDER_REVIEW','REVISION') THEN h.id END) homework_open FROM users u LEFT JOIN lessons l ON l.user_id=u.id LEFT JOIN homework h ON h.user_id=u.id WHERE u.active=1 GROUP BY u.id ORDER BY u.name COLLATE NOCASE",(now,)).fetchall();conn.close();return [_dict(x) for x in rows]
 return _cached('students',15.0,load)
def student_card(user_id):
 user=get_user(int(user_id))
 if not user:return None
 conn=connect();lessons=conn.execute('SELECT * FROM lessons WHERE user_id=? ORDER BY start_time DESC LIMIT 20',(int(user_id),)).fetchall();homework=conn.execute('SELECT * FROM homework WHERE user_id=? ORDER BY assigned_at DESC LIMIT 30',(int(user_id),)).fetchall();payments=conn.execute('SELECT * FROM payments WHERE user_id=? ORDER BY created_at DESC LIMIT 20',(int(user_id),)).fetchall();submissions=conn.execute('SELECT * FROM homework_submissions WHERE user_id=? ORDER BY submitted_at DESC LIMIT 20',(int(user_id),)).fetchall();conn.close();return {'student':_dict(user),'lessons':[_dict(x) for x in lessons],'homework':[_dict(x) for x in homework],'payments':[_dict(x) for x in payments],'submissions':[_dict(x) for x in submissions]}
def create_simple_homework(user_id,title,description,deadline=None,lesson_id=None):
 user=get_user(int(user_id))
 if not user:return {'status':'student_not_found'}
 description=str(description or '').strip()
 if not description:return {'status':'description_required'}
 title=str(title or 'Домашнее задание').strip()[:160];hid=create_homework(int(user_id),user['study_goal'] or 'GENERAL',user['main_subject'] or 'PHYSICS',description,title=title,lesson_id=int(lesson_id) if lesson_id else None,deadline=str(deadline).strip() or None if deadline is not None else None);_CACHE.clear();return {'status':'ok','homework_id':int(hid)}
def review_submission(submission_id,result,comment='',total_tasks=None,correct_tasks=None):
 """Compatibility entrypoint. All legacy reviews now use the canonical finalizer."""
 result=str(result or '').upper()
 if result=='PARTIAL':result='REVISION'
 if result not in {'ACCEPTED','REVISION'}:return {'status':'invalid_result'}
 conn=connect();sub=conn.execute('SELECT homework_id,user_id,attempt_number FROM homework_submissions WHERE id=?',(int(submission_id),)).fetchone();conn.close()
 if not sub:return {'status':'submission_not_found'}
 from web_backend.homework_review_flow import finalize
 response=finalize(int(sub['homework_id']),int(sub['user_id']),result,str(comment or '').strip(),int(sub['attempt_number'] or 1));_CACHE.clear();return response
