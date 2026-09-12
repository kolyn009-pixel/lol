"""Temporary public-trial onboarding."""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib,re,secrets
import database
from core import event_center
MAX_NAME=80;MAX_TELEGRAM=80;MAX_PHONE=40;MAX_NOTE=600;MAX_SUBJECT=80;RETENTION_DAYS=7;CODE_TTL_DAYS=7
def _now():return datetime.now()
def _iso(value):return value.isoformat(timespec='seconds')
def ensure_schema():
 c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS public_trial_requests (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,contact TEXT,subject TEXT,study_goal TEXT,preferred_time TEXT,note TEXT,status TEXT NOT NULL DEFAULT 'NEW',source TEXT NOT NULL DEFAULT 'WEB',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,reviewed_at TEXT,reviewer_id INTEGER);CREATE INDEX IF NOT EXISTS idx_public_trial_status_created ON public_trial_requests(status,created_at DESC);""")
 cols={r['name'] for r in c.execute('PRAGMA table_info(public_trial_requests)').fetchall()};additions={'telegram':'TEXT','phone':'TEXT','grade':'TEXT','board_url':'TEXT','meeting_url':'TEXT','trial_start':'TEXT','trial_end':'TEXT','trial_finished_at':'TEXT','continuation_code_hash':'TEXT','continuation_code_expires_at':'TEXT','continuation_code_used_at':'TEXT','expires_at':'TEXT','converted_user_id':'INTEGER','purged_at':'TEXT','timezone':'TEXT','region':'TEXT','selected_slot_start':'TEXT','selected_slot_end':'TEXT'}
 for name,kind in additions.items():
  if name not in cols:c.execute(f'ALTER TABLE public_trial_requests ADD COLUMN {name} {kind}')
 c.execute('CREATE INDEX IF NOT EXISTS idx_public_trial_expires ON public_trial_requests(expires_at,status)');c.execute('CREATE INDEX IF NOT EXISTS idx_public_trial_code_hash ON public_trial_requests(continuation_code_hash)');c.execute('CREATE INDEX IF NOT EXISTS idx_public_trial_selected_slot ON public_trial_requests(selected_slot_start,status)');c.commit();c.close()
def _clean(value,limit):return re.sub(r'\s+',' ',str(value or '').strip())[:limit]
def _code_hash(code):return hashlib.sha256(str(code).strip().upper().encode()).hexdigest()
def _new_code():
 alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';return ''.join(secrets.choice(alphabet) for _ in range(8))
def create(name,telegram=None,phone=None,subject=None,study_goal=None,preferred_time=None,note=None,grade=None,source='WEB',contact=None,timezone=None,region=None,selected_slot_start=None,selected_slot_end=None):
 ensure_schema();name=_clean(name,MAX_NAME);telegram=_clean(telegram,MAX_TELEGRAM) or None;phone=_clean(phone,MAX_PHONE) or None;legacy=_clean(contact,160) or None
 if not telegram and not phone and legacy:telegram=legacy
 subject=_clean(subject,MAX_SUBJECT) or None;study_goal=_clean(study_goal,MAX_SUBJECT) or None;preferred_time=_clean(preferred_time,80) or None;note=_clean(note,MAX_NOTE) or None;grade=_clean(grade,30) or None;timezone=_clean(timezone,80) or None;region=_clean(region,100) or None;selected_slot_start=_clean(selected_slot_start,40) or None;selected_slot_end=_clean(selected_slot_end,40) or None
 if len(name)<2:raise ValueError('name_required')
 if not telegram and not phone:raise ValueError('telegram_or_phone_required')
 if selected_slot_start:
  if not selected_slot_end:raise ValueError('trial_slot_required')
  start=datetime.fromisoformat(selected_slot_start);end=datetime.fromisoformat(selected_slot_end)
  if end<=start:raise ValueError('invalid_trial_time')
 now=_now();expires=now+timedelta(days=RETENTION_DAYS);c=database.connect()
 try:
  # Serialize the availability check and insert. Two simultaneous public requests can no longer both reserve the same/overlapping slot.
  c.execute('BEGIN IMMEDIATE')
  if selected_slot_start:
   from web_backend import availability_guard
   hits=availability_guard.conflicts(start,end)
   if hits:raise ValueError('trial_slot_taken')
  cur=c.execute("""INSERT INTO public_trial_requests(name,contact,telegram,phone,grade,subject,study_goal,preferred_time,note,status,source,created_at,updated_at,expires_at,timezone,region,selected_slot_start,selected_slot_end) VALUES(?,?,?,?,?,?,?,?,?,'NEW',?,?,?,?,?,?,?,?)""",(name,legacy,telegram,phone,grade,subject,study_goal,preferred_time,note,str(source or 'WEB')[:20],_iso(now),_iso(now),_iso(expires),timezone,region,selected_slot_start,selected_slot_end));rid=cur.lastrowid;c.commit()
 except Exception:
  c.rollback();raise
 finally:c.close()
 try:
  parts=[x for x in [f'Telegram: {telegram}' if telegram else None,f'Телефон: {phone}' if phone else None,f'Класс: {grade}' if grade else None,f'Предмет: {subject}' if subject else None,f'Цель: {study_goal}' if study_goal else None,f'Время: {selected_slot_start}' if selected_slot_start else (f'Желаемое время: {preferred_time}' if preferred_time else None),f'Регион: {region}' if region else None] if x];event_center.push('PUBLIC_TRIAL_REQUEST',f'Пробное занятие: {name}',' · '.join(parts),'ACTION','public_trial',int(rid),f'public_trial:{int(rid)}')
 except Exception:pass
 return {'status':'ok','request_id':int(rid),'expires_at':_iso(expires)}
def get(request_id):
 ensure_schema();c=database.connect();r=c.execute('SELECT * FROM public_trial_requests WHERE id=?',(int(request_id),)).fetchone();c.close();return dict(r) if r else None
def list_for_teacher(status=None,limit=100):
 ensure_schema();cleanup_expired();c=database.connect();sql='SELECT * FROM public_trial_requests';p=[]
 if status:sql+=' WHERE status=?';p.append(str(status).upper())
 sql+=' ORDER BY created_at DESC LIMIT ?';p.append(max(1,min(int(limit),200)));rows=c.execute(sql,p).fetchall();c.close();return [dict(r) for r in rows]
def approve(request_id,reviewer_id,trial_start=None,trial_end=None,meeting_url=None,board_url=None):
 ensure_schema();row=get(request_id)
 if not row:raise ValueError('request_not_found')
 if row['status'] not in {'NEW','CONTACTED','ACCEPTED'}:raise ValueError('request_not_actionable')
 start=str(trial_start or row.get('selected_slot_start') or '').strip();end=str(trial_end or row.get('selected_slot_end') or '').strip()
 if not start or not end:raise ValueError('trial_time_required')
 if datetime.fromisoformat(end)<=datetime.fromisoformat(start):raise ValueError('invalid_trial_time')
 now=_now();expires=datetime.fromisoformat(end)+timedelta(days=RETENTION_DAYS);c=database.connect();c.execute("UPDATE public_trial_requests SET status='ACCEPTED',trial_start=?,trial_end=?,meeting_url=?,board_url=?,reviewed_at=?,reviewer_id=?,updated_at=?,expires_at=? WHERE id=?",(start,end,_clean(meeting_url,1200) or None,_clean(board_url,1200) or None,_iso(now),int(reviewer_id),_iso(now),_iso(expires),int(request_id)));c.commit();c.close();return teacher_share_payload(request_id)
def teacher_share_payload(request_id):
 row=get(request_id)
 if not row:raise ValueError('request_not_found')
 return {'request_id':int(row['id']),'name':row['name'],'telegram':row.get('telegram'),'phone':row.get('phone'),'trial_start':row.get('trial_start'),'trial_end':row.get('trial_end'),'meeting_url':row.get('meeting_url'),'board_url':row.get('board_url'),'status':row['status'],'timezone':row.get('timezone'),'region':row.get('region'),'ready_to_send':bool(row.get('meeting_url') and row.get('board_url'))}
def finish_trial(request_id,finished_at=None):
 ensure_schema();row=get(request_id)
 if not row:raise ValueError('request_not_found')
 if row['status'] not in {'ACCEPTED','TRIAL_COMPLETED'}:raise ValueError('trial_not_accepted')
 finished=datetime.fromisoformat(finished_at) if finished_at else _now();code=_new_code();code_exp=finished+timedelta(days=CODE_TTL_DAYS);c=database.connect();c.execute("UPDATE public_trial_requests SET status='TRIAL_COMPLETED',trial_finished_at=?,continuation_code_hash=?,continuation_code_expires_at=?,continuation_code_used_at=NULL,updated_at=?,expires_at=? WHERE id=?",(_iso(finished),_code_hash(code),_iso(code_exp),_iso(finished),_iso(code_exp),int(request_id)));c.commit();c.close()
 try:event_center.push('TRIAL_CONTINUATION_CODE',f'Код после пробного: {row["name"]}',f'Код действует до {_iso(code_exp)}','ACTION','public_trial',int(request_id),f'trial_code:{int(request_id)}')
 except Exception:pass
 return {'status':'ok','request_id':int(request_id),'continuation_code':code,'expires_at':_iso(code_exp)}
def validate_continuation_code(code):
 ensure_schema();h=_code_hash(code);now=_iso(_now());c=database.connect();r=c.execute("SELECT * FROM public_trial_requests WHERE continuation_code_hash=? AND continuation_code_used_at IS NULL AND continuation_code_expires_at>? AND status='TRIAL_COMPLETED' LIMIT 1",(h,now)).fetchone();c.close()
 if not r:raise ValueError('invalid_or_expired_code')
 d=dict(r);return {'request_id':int(d['id']),'name':d['name'],'telegram':d.get('telegram'),'phone':d.get('phone'),'grade':d.get('grade'),'subject':d.get('subject'),'study_goal':d.get('study_goal'),'board_url':d.get('board_url'),'meeting_url':d.get('meeting_url'),'trial_finished_at':d.get('trial_finished_at')}
def mark_converted(code,user_id):
 ensure_schema();h=_code_hash(code);now=_iso(_now());c=database.connect();r=c.execute("SELECT id FROM public_trial_requests WHERE continuation_code_hash=? AND continuation_code_used_at IS NULL AND continuation_code_expires_at>? AND status='TRIAL_COMPLETED' LIMIT 1",(h,now)).fetchone()
 if not r:c.close();raise ValueError('invalid_or_expired_code')
 c.execute("UPDATE public_trial_requests SET status='CONVERTED',continuation_code_used_at=?,converted_user_id=?,updated_at=?,expires_at=? WHERE id=?",(now,int(user_id),now,now,int(r['id'])));c.commit();c.close();return {'status':'ok','request_id':int(r['id']),'user_id':int(user_id)}
def set_status(request_id,status,reviewer_id=None):
 ensure_schema();status=str(status or '').upper()
 if status not in {'NEW','CONTACTED','ACCEPTED','DECLINED','CLOSED'}:raise ValueError('invalid_status')
 now=_now();expires=now+timedelta(days=RETENTION_DAYS);c=database.connect();cur=c.execute("UPDATE public_trial_requests SET status=?,updated_at=?,reviewed_at=?,reviewer_id=?,expires_at=? WHERE id=?",(status,_iso(now),_iso(now),int(reviewer_id) if reviewer_id else None,_iso(expires),int(request_id)));c.commit();c.close()
 if cur.rowcount!=1:raise ValueError('request_not_found')
 return {'status':'ok','request_id':int(request_id),'request_status':status}
def cleanup_expired(now=None):
 ensure_schema();now=now or _now();stamp=_iso(now);c=database.connect();rows=c.execute("SELECT id FROM public_trial_requests WHERE purged_at IS NULL AND converted_user_id IS NULL AND expires_at IS NOT NULL AND expires_at<=?",(stamp,)).fetchall();ids=[int(r['id']) for r in rows]
 if ids:
  marks=','.join('?' for _ in ids);c.execute(f"UPDATE public_trial_requests SET name='Удалено',contact=NULL,telegram=NULL,phone=NULL,grade=NULL,subject=NULL,study_goal=NULL,preferred_time=NULL,note=NULL,meeting_url=NULL,board_url=NULL,continuation_code_hash=NULL,status='EXPIRED',purged_at=?,updated_at=? WHERE id IN ({marks})",(stamp,stamp,*ids))
 c.commit();c.close();return {'status':'ok','purged_count':len(ids),'purged_ids':ids}
