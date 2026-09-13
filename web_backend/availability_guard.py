"""Unified collision guard for public trials, one-off lessons and recurring schedules."""
from __future__ import annotations
from datetime import datetime,timedelta
import database
from web_backend import public_trial

# Keep lesson collision semantics compatible with database.is_slot_reserved().
# Historical terminal lessons must not reserve future/public slots, while a
# lesson that is currently running must always block its interval.
BLOCKING_LESSON_STATUSES={'PENDING','CONFIRMED','IN_PROGRESS'}
BLOCKING_REGULAR_STATUSES={'PENDING','APPROVED'}
BLOCKING_TRIAL_STATUSES={'LINKING','NEW','CONTACTED','ACCEPTED'}

def _dt(v):return v if isinstance(v,datetime) else datetime.fromisoformat(str(v))
def overlaps(a_start,a_end,b_start,b_end):return _dt(a_start)<_dt(b_end) and _dt(b_start)<_dt(a_end)
def _clock_minutes(v):
 h,m=[int(x) for x in str(v)[:5].split(':')];return h*60+m

def availability_snapshot(range_start,range_end,include_pending_regular=True,conn=None):
 """Load all blocking rows for a time window once.

 Public slot feeds can then test hundreds of candidate windows in memory instead
 of issuing several SQL queries per 30-minute candidate.
 """
 start=_dt(range_start);end=_dt(range_end)
 if end<=start:raise ValueError('invalid_interval')
 c=conn or database.connect();own_connection=conn is None
 try:
  lessons=[];trials=[];regular=[]
  try:
   marks=','.join('?' for _ in BLOCKING_LESSON_STATUSES)
   rows=c.execute(
    f"SELECT id,start_time,end_time,lesson_status FROM lessons "
    f"WHERE start_time < ? AND end_time > ? AND lesson_status IN ({marks})",
    (end.isoformat(),start.isoformat(),*sorted(BLOCKING_LESSON_STATUSES))
   ).fetchall()
   lessons=[dict(r) for r in rows]
  except Exception:pass
  try:
   if own_connection:public_trial.ensure_schema()
   marks=','.join('?' for _ in BLOCKING_TRIAL_STATUSES)
   rows=c.execute(
    f"SELECT id,selected_slot_start,selected_slot_end,status FROM public_trial_requests "
    f"WHERE selected_slot_start IS NOT NULL AND status IN ({marks}) "
    f"AND (expires_at IS NULL OR expires_at>?)",
    (*sorted(BLOCKING_TRIAL_STATUSES),datetime.now().isoformat(timespec='seconds'))
   ).fetchall()
   trials=[dict(r) for r in rows]
  except Exception:pass
  try:
   statuses=('PENDING','APPROVED') if include_pending_regular else ('APPROVED',)
   marks=','.join('?' for _ in statuses)
   rows=c.execute(
    f"SELECT id,weekday,start_time,duration_minutes,status,start_date,end_date,pause_until "
    f"FROM regular_schedules WHERE status IN ({marks}) AND COALESCE(active,1)=1",
    statuses
   ).fetchall()
   regular=[dict(r) for r in rows]
  except Exception:pass
  return {'lessons':lessons,'trials':trials,'regular':regular}
 finally:
  if own_connection:c.close()

def conflicts_from_snapshot(start_time,end_time,snapshot,ignore_lesson_id=None,ignore_regular_id=None,ignore_trial_id=None):
 start=_dt(start_time);end=_dt(end_time)
 if end<=start:raise ValueError('invalid_interval')
 out=[]
 for r in snapshot.get('lessons',[]):
  if ignore_lesson_id and int(r['id'])==int(ignore_lesson_id):continue
  if overlaps(start,end,r['start_time'],r['end_time']):out.append({'kind':'lesson','id':int(r['id']),'status':r.get('lesson_status')})
 for r in snapshot.get('trials',[]):
  if ignore_trial_id and int(r['id'])==int(ignore_trial_id):continue
  s=r['selected_slot_start'];e=r.get('selected_slot_end') or (_dt(s)+timedelta(minutes=60)).isoformat()
  if overlaps(start,end,s,e):out.append({'kind':'public_trial','id':int(r['id']),'status':r.get('status')})
 weekday=start.weekday();day=start.date();sm=start.hour*60+start.minute;em=end.hour*60+end.minute
 for r in snapshot.get('regular',[]):
  if ignore_regular_id and int(r['id'])==int(ignore_regular_id):continue
  if int(r['weekday'])!=weekday:continue
  # A recurring reservation only exists inside its configured date range.
  # Older databases may have NULL bounds, which intentionally means unbounded.
  try:
   if r.get('start_date') and day<datetime.fromisoformat(str(r['start_date'])).date():continue
   if r.get('end_date') and day>datetime.fromisoformat(str(r['end_date'])).date():continue
  except Exception:
   pass
  # Defensive support for temporarily paused rows if legacy data happens to
  # retain APPROVED while pause_until is populated.
  try:
   if r.get('pause_until') and day<=datetime.fromisoformat(str(r['pause_until'])).date():continue
  except Exception:
   pass
  rs=_clock_minutes(r['start_time']);re=rs+int(r.get('duration_minutes') or 60)
  if sm<re and rs<em:out.append({'kind':'regular_schedule','id':int(r['id']),'status':r.get('status')})
 return out

def conflicts(start_time,end_time,ignore_lesson_id=None,ignore_regular_id=None,ignore_trial_id=None,include_pending_regular=True,conn=None):
 start=_dt(start_time);end=_dt(end_time)
 if end<=start:raise ValueError('invalid_interval')
 snap=availability_snapshot(start,end,include_pending_regular=include_pending_regular,conn=conn)
 return conflicts_from_snapshot(start,end,snap,ignore_lesson_id=ignore_lesson_id,ignore_regular_id=ignore_regular_id,ignore_trial_id=ignore_trial_id)

def is_available(start_time,end_time,**kwargs):return not conflicts(start_time,end_time,**kwargs)
def is_available_from_snapshot(start_time,end_time,snapshot,**kwargs):return not conflicts_from_snapshot(start_time,end_time,snapshot,**kwargs)
def assert_available(start_time,end_time,**kwargs):
 hits=conflicts(start_time,end_time,**kwargs)
 if hits:raise ValueError('slot_unavailable')
 return True
