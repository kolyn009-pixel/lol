"""Unified teacher request center for lesson, public-trial and recurring schedule requests."""
from __future__ import annotations
import database
from web_backend import public_trial,student_onboarding,student_regular_booking


def _lesson_requests(limit=100):
 c=database.connect()
 try:
  rows=c.execute("""SELECT l.id,l.user_id,l.program_id,l.study_goal,l.subject,l.start_time,l.end_time,l.duration_minutes,l.price,l.is_trial,l.lesson_status,l.request_source,l.created_at,u.name,u.grade,u.telegram_username FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.lesson_status='PENDING' AND l.request_source='STUDENT' ORDER BY l.start_time ASC LIMIT ?""",(max(1,min(int(limit),200)),)).fetchall();return [dict(r) for r in rows]
 finally:c.close()


def _schedule_requests(limit=100):
 student_onboarding.ensure_schema();student_regular_booking.ensure_schema();c=database.connect()
 try:
  rows=c.execute("""SELECT r.id,r.user_id,r.study_goal,r.subject,r.weekday,r.start_time,r.duration_minutes,r.start_date,r.end_date,r.status,r.active,r.request_source,r.student_timezone,r.student_local_weekday,r.student_local_start_time,r.onboarding_session_id,r.request_group,r.created_at,u.name,u.grade,s.region,s.timezone FROM regular_schedules r JOIN users u ON u.id=r.user_id LEFT JOIN student_onboarding_sessions s ON s.id=r.onboarding_session_id WHERE r.status='PENDING' AND r.request_source='STUDENT' ORDER BY r.created_at ASC,r.id ASC LIMIT ?""",(max(1,min(int(limit),300)),)).fetchall();return [dict(r) for r in rows]
 finally:c.close()


def _schedule_groups(rows):
 groups=[];seen={}
 for row in rows:
  key=row.get('request_group') or f"LEGACY-{int(row['id'])}"
  group=seen.get(key)
  if group is None:
   group={'request_group':key,'grouped':bool(row.get('request_group')),'user_id':int(row['user_id']),'name':row.get('name'),'grade':row.get('grade'),'subject':row.get('subject'),'study_goal':row.get('study_goal'),'region':row.get('region'),'timezone':row.get('timezone'),'created_at':row.get('created_at'),'start_date':row.get('start_date'),'end_date':row.get('end_date'),'items':[]}
   seen[key]=group;groups.append(group)
  group['items'].append(row)
 for group in groups:group['weekly_count']=len(group['items'])
 return groups


def list_all(limit=100):
 from web_backend import public_group_registration
 group_registrations=public_group_registration.list_for_teacher(limit)
 trials=public_trial.list_for_teacher(limit=limit);lessons=_lesson_requests(limit);schedules=_schedule_requests(limit);groups=_schedule_groups(schedules)
 return {'group_registrations':group_registrations,'counts':{'group':len(group_registrations),'trial':sum(1 for x in trials if x.get('status') in {'NEW','CONTACTED'}),'lesson':len(lessons),'schedule':len(schedules),'schedule_groups':len(groups)},'trials':trials,'lesson_requests':lessons,'schedule_requests':schedules,'schedule_groups':groups}


def approve_lesson(lesson_id):
 lesson=database.get_lesson(int(lesson_id))
 if not lesson:raise ValueError('lesson_not_found')
 if lesson['lesson_status']!='PENDING':raise ValueError('lesson_not_pending')
 database.approve_lesson_request(int(lesson_id))
 try:
  from integrations.lesson_sync import sync_lesson
  integrations=sync_lesson(int(lesson_id))
 except Exception as exc:
  integrations={'google':{'status':'error','error':str(exc)},'telemost':{'status':'error','error':str(exc)}}
 return {'status':'ok','lesson_id':int(lesson_id),'lesson_status':'CONFIRMED','integrations':integrations}


def reject_lesson(lesson_id,reason=None):
 lesson=database.get_lesson(int(lesson_id))
 if not lesson:raise ValueError('lesson_not_found')
 if lesson['lesson_status']!='PENDING':raise ValueError('lesson_not_pending')
 database.reject_lesson_request(int(lesson_id),str(reason or '').strip()[:500] or None);return {'status':'ok','lesson_id':int(lesson_id),'lesson_status':'REJECTED'}


def approve_schedule(schedule_id):
 sid=int(schedule_id);row=database.get_regular_schedule(sid)
 if not row:raise ValueError('schedule_not_found')
 if row['status']!='PENDING':raise ValueError('schedule_not_pending')
 if not row['start_date'] or not row['end_date']:raise ValueError('schedule_dates_missing')
 database.approve_regular_schedule(sid)
 conn=database.connect()
 try:
  conn.execute("UPDATE regular_schedules SET active=1,updated_at=? WHERE id=? AND status='APPROVED'",(database.now_iso(),sid));conn.commit()
 finally:conn.close()
 activated=database.get_regular_schedule(sid)
 if not activated or not int(activated['active'] or 0):raise ValueError('schedule_activation_failed')
 generation=database.generate_regular_lessons(sid)
 created=[int(x) for x in (generation.get('created') or [])]
 sync={'synced_lesson_ids':[],'failed':[]}
 if created:
  try:
   from core import schedule_sync
   sync=schedule_sync.sync_lessons_blocking(created)
  except Exception as exc:
   sync={'synced_lesson_ids':[],'failed':[{'reason':'schedule_sync_error','detail':type(exc).__name__}]}
 return {'status':'ok','schedule_id':sid,'schedule_status':'APPROVED','active':True,'start_date':activated['start_date'],'end_date':activated['end_date'],'generation':generation,'sync':sync}


def reject_schedule(schedule_id,reason=None):
 row=database.get_regular_schedule(int(schedule_id))
 if not row:raise ValueError('schedule_not_found')
 if row['status']!='PENDING':raise ValueError('schedule_not_pending')
 database.reject_regular_schedule(int(schedule_id),str(reason or '').strip()[:500] or None);return {'status':'ok','schedule_id':int(schedule_id),'schedule_status':'REJECTED'}


def _group_rows(request_group):
 student_regular_booking.ensure_schema();group=str(request_group or '').strip()
 if not group:raise ValueError('request_group_required')
 c=database.connect()
 try:
  rows=c.execute("SELECT id,status FROM regular_schedules WHERE request_group=? ORDER BY id",(group,)).fetchall()
  return [dict(r) for r in rows]
 finally:c.close()


def approve_schedule_group(request_group):
 rows=_group_rows(request_group)
 if not rows:raise ValueError('schedule_group_not_found')
 if any(r['status']!='PENDING' for r in rows):raise ValueError('schedule_group_not_pending')
 results=[]
 for row in rows:results.append(approve_schedule(int(row['id'])))
 return {'status':'ok','request_group':str(request_group),'approved_count':len(results),'items':results}


def reject_schedule_group(request_group,reason=None):
 rows=_group_rows(request_group)
 if not rows:raise ValueError('schedule_group_not_found')
 if any(r['status']!='PENDING' for r in rows):raise ValueError('schedule_group_not_pending')
 results=[]
 for row in rows:results.append(reject_schedule(int(row['id']),reason))
 return {'status':'ok','request_group':str(request_group),'rejected_count':len(results),'items':results}
