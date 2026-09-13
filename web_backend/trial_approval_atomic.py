from __future__ import annotations
from datetime import datetime,timedelta
import database
from web_backend import availability_guard,public_trial

def approve(request_id,reviewer_id,trial_start=None,trial_end=None,meeting_url=None,board_url=None):
 rid=int(request_id);ensure=public_trial.ensure_schema;ensure();c=database.connect()
 try:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute('SELECT * FROM public_trial_requests WHERE id=?',(rid,)).fetchone()
  if not row:raise ValueError('request_not_found')
  row=dict(row)
  if row['status'] not in {'NEW','CONTACTED','ACCEPTED'}:raise ValueError('request_not_actionable')
  start=str(trial_start or row.get('selected_slot_start') or '').strip();end=str(trial_end or row.get('selected_slot_end') or '').strip()
  if not start or not end:raise ValueError('trial_time_required')
  start_dt=datetime.fromisoformat(start);end_dt=datetime.fromisoformat(end)
  if end_dt<=start_dt:raise ValueError('invalid_trial_time')
  if availability_guard.conflicts(start_dt,end_dt,ignore_trial_id=rid,conn=c):raise ValueError('trial_slot_taken')
  now=datetime.now();expires=end_dt+timedelta(days=public_trial.RETENTION_DAYS)
  c.execute("UPDATE public_trial_requests SET status='ACCEPTED',selected_slot_start=?,selected_slot_end=?,trial_start=?,trial_end=?,meeting_url=?,board_url=?,reviewed_at=?,reviewer_id=?,updated_at=?,expires_at=? WHERE id=?",(start_dt.isoformat(timespec='seconds'),end_dt.isoformat(timespec='seconds'),start_dt.isoformat(timespec='seconds'),end_dt.isoformat(timespec='seconds'),public_trial._clean(meeting_url,1200) or None,public_trial._clean(board_url,1200) or None,now.isoformat(timespec='seconds'),int(reviewer_id),now.isoformat(timespec='seconds'),expires.isoformat(timespec='seconds'),rid))
  c.commit()
 except Exception:
  c.rollback();raise
 finally:c.close()
 return public_trial.teacher_share_payload(rid)
