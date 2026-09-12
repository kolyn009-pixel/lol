"""Unified collision guard for public trials, one-off lessons and recurring schedules."""
from __future__ import annotations
from datetime import datetime,timedelta
import database
from web_backend import public_trial

BLOCKING_LESSON_STATUSES={'PENDING','CONFIRMED','APPROVED','DONE','COMPLETED','HELD'}
BLOCKING_REGULAR_STATUSES={'PENDING','APPROVED'}
BLOCKING_TRIAL_STATUSES={'LINKING','NEW','CONTACTED','ACCEPTED'}

def _dt(v):return v if isinstance(v,datetime) else datetime.fromisoformat(str(v))
def overlaps(a_start,a_end,b_start,b_end):return _dt(a_start)<_dt(b_end) and _dt(b_start)<_dt(a_end)
def _clock_minutes(v):
 h,m=[int(x) for x in str(v)[:5].split(':')];return h*60+m

def conflicts(start_time,end_time,ignore_lesson_id=None,ignore_regular_id=None,ignore_trial_id=None,include_pending_regular=True,conn=None):
 start=_dt(start_time);end=_dt(end_time)
 if end<=start:raise ValueError('invalid_interval')
 out=[]
 if database.is_slot_reserved(start.isoformat(),end.isoformat()):out.append({'kind':'lesson','id':None})
 c=conn or database.connect();own_connection=conn is None
 try:
  try:
   rows=c.execute("SELECT id,start_time,end_time,lesson_status FROM lessons WHERE start_time < ? AND end_time > ? AND lesson_status NOT IN ('REJECTED','CANCELLED')",(end.isoformat(),start.isoformat())).fetchall()
   for r in rows:
    if ignore_lesson_id and int(r['id'])==int(ignore_lesson_id):continue
    out.append({'kind':'lesson','id':int(r['id']),'status':r['lesson_status']})
  except Exception:pass
  try:
   if own_connection:public_trial.ensure_schema()
   rows=c.execute("SELECT id,selected_slot_start,selected_slot_end,status FROM public_trial_requests WHERE selected_slot_start IS NOT NULL AND status IN ('LINKING','NEW','CONTACTED','ACCEPTED') AND (expires_at IS NULL OR expires_at>?)",(datetime.now().isoformat(timespec='seconds'),)).fetchall()
   for r in rows:
    if ignore_trial_id and int(r['id'])==int(ignore_trial_id):continue
    s=r['selected_slot_start'];e=r['selected_slot_end'] or (_dt(s)+timedelta(minutes=60)).isoformat()
    if overlaps(start,end,s,e):out.append({'kind':'public_trial','id':int(r['id']),'status':r['status']})
  except Exception:pass
  try:
   statuses="('PENDING','APPROVED')" if include_pending_regular else "('APPROVED')"
   rows=c.execute(f"SELECT id,weekday,start_time,duration_minutes,status FROM regular_schedules WHERE status IN {statuses} AND COALESCE(active,1)=1 OR status='PENDING'").fetchall()
   weekday=start.weekday();sm=start.hour*60+start.minute;em=end.hour*60+end.minute
   for r in rows:
    if ignore_regular_id and int(r['id'])==int(ignore_regular_id):continue
    if int(r['weekday'])!=weekday:continue
    rs=_clock_minutes(r['start_time']);re=rs+int(r['duration_minutes'] or 60)
    if sm<re and rs<em:out.append({'kind':'regular_schedule','id':int(r['id']),'status':r['status']})
  except Exception:pass
 finally:
  if own_connection:c.close()
 seen=set();uniq=[]
 for x in out:
  k=(x['kind'],x.get('id'))
  if k not in seen:seen.add(k);uniq.append(x)
 return uniq

def is_available(start_time,end_time,**kwargs):return not conflicts(start_time,end_time,**kwargs)
def assert_available(start_time,end_time,**kwargs):
 hits=conflicts(start_time,end_time,**kwargs)
 if hits:raise ValueError('slot_unavailable')
 return True
