"""Permanent-student onboarding for returning TutorBot students.

A returning student may predate TutorBot and therefore have no canonical profile.
Messenger ownership is verified first. If no matching profile exists, a provisional
canonical student is created from the onboarding form and stays inactive until the
web registration is completed.
"""
from __future__ import annotations
from datetime import datetime,timedelta
import json,secrets,string
import database
from web_backend import student_auth,web_sessions

SESSION_TTL_MINUTES=60
TG_BOT_URL='https://t.me/AdeliaTutorBot'
VK_MESSAGES_URL='https://vk.me/club241263797'

def _now():return datetime.now()
def _iso(dt=None):return (dt or _now()).isoformat(timespec='seconds')
def _token(prefix='JOIN'):
 alphabet=string.ascii_uppercase+string.digits;return prefix+'-'+''.join(secrets.choice(alphabet) for _ in range(10))
def _clean(v,n=120):return str(v or '').strip()[:n]
def _goal(v):
 x=_clean(v,80).upper();m={'ПОДГОТОВКА К ОГЭ':'OGE','ОГЭ':'OGE','ПОДГОТОВКА К ЕГЭ':'EGE','ЕГЭ':'EGE','ОЛИМПИАДНАЯ ФИЗИКА':'OLYMPIAD','ОЛИМПИАДНАЯ ПОДГОТОВКА':'OLYMPIAD','ШКОЛЬНАЯ ПРОГРАММА':'SCHOOL','ПОВЫСИТЬ УСПЕВАЕМОСТЬ':'SCHOOL','ПОВЫШЕНИЕ УСПЕВАЕМОСТИ':'SCHOOL'};return m.get(x,x if x in {'OGE','EGE','OLYMPIAD','SCHOOL'} else 'SCHOOL')
def _subject(v):
 x=_clean(v,80).upper();return 'CHEMISTRY' if x in {'ХИМИЯ','CHEMISTRY'} else 'PHYSICS'

def ensure_schema():
 c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS student_onboarding_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,token TEXT NOT NULL UNIQUE,mode TEXT NOT NULL DEFAULT 'RETURNING',preferred_channel TEXT,claimed_profile_url TEXT,status TEXT NOT NULL DEFAULT 'WAIT_CHANNEL',external_id TEXT,external_username TEXT,external_display_name TEXT,linked_user_id INTEGER,region TEXT,timezone TEXT,schedule_json TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,expires_at TEXT NOT NULL,completed_at TEXT,FOREIGN KEY(linked_user_id) REFERENCES users(id) ON DELETE SET NULL);CREATE INDEX IF NOT EXISTS idx_student_onboarding_token ON student_onboarding_sessions(token);CREATE INDEX IF NOT EXISTS idx_student_onboarding_status ON student_onboarding_sessions(status,expires_at);""")
 cols={r['name'] for r in c.execute('PRAGMA table_info(student_onboarding_sessions)').fetchall()}
 for name,kind in {'name':'TEXT','grade':'INTEGER','subject':'TEXT','study_goal':'TEXT','phone':'TEXT','legacy_note':'TEXT','provisional_user_created':'INTEGER DEFAULT 0'}.items():
  if name not in cols:c.execute(f'ALTER TABLE student_onboarding_sessions ADD COLUMN {name} {kind}')
 c.commit();c.close()
def _row(token):
 ensure_schema();c=database.connect();r=c.execute('SELECT * FROM student_onboarding_sessions WHERE token=? LIMIT 1',(_clean(token,80).upper(),)).fetchone();c.close();return dict(r) if r else None
def _active(row):
 if not row:raise ValueError('onboarding_not_found')
 if datetime.fromisoformat(row['expires_at'])<_now():raise ValueError('onboarding_expired')
 return row
def _find_existing_user(channel,external_id):
 channel=_clean(channel,20).upper();external_id=_clean(external_id,100);c=database.connect()
 try:
  if channel=='TELEGRAM':
   try:r=c.execute('SELECT id FROM users WHERE telegram_id=? LIMIT 1',(int(external_id),)).fetchone()
   except ValueError:r=None
   if r:return int(r['id'])
  try:r=c.execute('SELECT user_id FROM channel_identities WHERE channel=? AND external_id=? AND enabled=1 LIMIT 1',(channel,external_id)).fetchone()
  except Exception:r=None
  return int(r['user_id']) if r else None
 finally:c.close()
def _bind_identity(uid,channel,external_id,username=None,display_name=None):
 channel=_clean(channel,20).upper();external_id=_clean(external_id,100);now=_iso();c=database.connect()
 try:
  if channel=='TELEGRAM':
   c.execute('UPDATE users SET telegram_id=?,telegram_username=COALESCE(?,telegram_username),updated_at=? WHERE id=?',(int(external_id),_clean(username,100) or None,now,int(uid)))
  try:
   c.execute("""INSERT INTO channel_identities(user_id,channel,external_id,username,display_name,enabled,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?) ON CONFLICT(user_id,channel) DO UPDATE SET external_id=excluded.external_id,username=excluded.username,display_name=excluded.display_name,enabled=1,blocked_at=NULL,updated_at=excluded.updated_at""",(int(uid),channel,external_id,_clean(username,100) or None,_clean(display_name,160) or None,now,now))
  except Exception:pass
  c.commit()
 finally:c.close()
def _create_provisional(row,channel,external_id,username=None,display_name=None):
 name=_clean(row.get('name'),80);grade=int(row.get('grade') or 0);subject=_subject(row.get('subject'));goal=_goal(row.get('study_goal'))
 if len(name)<2 or grade<1:raise ValueError('student_identity_incomplete')
 now=_iso();c=database.connect()
 try:
  c.execute('BEGIN IMMEDIATE')
  tg=int(external_id) if channel=='TELEGRAM' else None
  cur=c.execute("""INSERT INTO users(telegram_id,telegram_username,name,grade,phone,study_goal,main_subject,trial_used,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,0,0,?,?)""",(tg,_clean(username,100) or None if tg else None,name,grade,_clean(row.get('phone'),40) or None,goal,subject,now,now));uid=int(cur.lastrowid)
  c.execute("""INSERT OR IGNORE INTO student_programs(user_id,study_goal,subject,is_primary,active,approval_status,trial_used,created_by,created_at) VALUES(?,?,?,1,1,'APPROVED',0,'RETURNING_ONBOARDING',?)""",(uid,goal,subject,now))
  c.commit()
 finally:c.close()
 _bind_identity(uid,channel,external_id,username,display_name);return uid

def start_returning(preferred_channel,profile_url=None,name=None,grade=None,subject=None,study_goal=None,phone=None,legacy_note=None):
 ensure_schema();channel=_clean(preferred_channel,20).upper()
 if channel not in {'TELEGRAM','VK'}:raise ValueError('invalid_channel')
 name=_clean(name,80)
 if len(name)<2:raise ValueError('name_required')
 try:grade=int(grade)
 except Exception:raise ValueError('grade_required')
 if grade<1 or grade>14:raise ValueError('invalid_grade')
 token=_token();now=_now();expires=now+timedelta(minutes=SESSION_TTL_MINUTES);c=database.connect();c.execute("""INSERT INTO student_onboarding_sessions(token,mode,preferred_channel,claimed_profile_url,status,name,grade,subject,study_goal,phone,legacy_note,created_at,updated_at,expires_at) VALUES(?,'RETURNING',?,?, 'WAIT_CHANNEL',?,?,?,?,?,?,?, ?,?)""",(token,channel,_clean(profile_url,500) or None,name,grade,_subject(subject),_goal(study_goal),_clean(phone,40) or None,_clean(legacy_note,600) or None,_iso(now),_iso(now),_iso(expires)));c.commit();c.close();return {'token':token,'preferred_channel':channel,'telegram_url':f'{TG_BOT_URL}?start=join_{token}','vk_url':VK_MESSAGES_URL,'vk_code':token,'expires_at':_iso(expires)}
def confirm_channel(token,channel,external_id,username=None,display_name=None):
 row=_active(_row(token));channel=_clean(channel,20).upper()
 if channel!=_clean(row.get('preferred_channel'),20).upper():raise ValueError('wrong_channel')
 uid=_find_existing_user(channel,external_id);created=0
 if not uid:uid=_create_provisional(row,channel,str(external_id),username,display_name);created=1
 else:_bind_identity(uid,channel,str(external_id),username,display_name)
 c=database.connect();c.execute("UPDATE student_onboarding_sessions SET status='CHANNEL_VERIFIED',external_id=?,external_username=?,external_display_name=?,linked_user_id=?,provisional_user_created=?,updated_at=? WHERE id=?",(_clean(external_id,100),_clean(username,100) or None,_clean(display_name,160) or None,int(uid),created,_iso(),int(row['id'])));c.commit();c.close();return status_payload(token)
def save_region(token,region,timezone):
 row=_active(_row(token))
 if row['status'] not in {'CHANNEL_VERIFIED','REGION_SET','SCHEDULE_SET'}:raise ValueError('channel_not_verified')
 from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
 region=_clean(region,100);timezone=_clean(timezone,80)
 if not region or not timezone:raise ValueError('region_required')
 try:ZoneInfo(timezone)
 except ZoneInfoNotFoundError:raise ValueError('invalid_timezone')
 c=database.connect();c.execute("UPDATE student_onboarding_sessions SET region=?,timezone=?,status='REGION_SET',updated_at=? WHERE id=?",(region,timezone,_iso(),int(row['id'])));c.commit();c.close();return status_payload(token)
def save_schedule(token,selections):
 row=_active(_row(token))
 if row['status'] not in {'REGION_SET','SCHEDULE_SET'}:raise ValueError('region_not_set')
 values=selections if isinstance(selections,list) else [];clean=[]
 for x in values[:4]:
  if not isinstance(x,dict):continue
  day=_clean(x.get('weekday'),20);time=_clean(x.get('time'),8);duration=int(x.get('duration_minutes') or 60)
  if day and time and 30<=duration<=180:clean.append({'weekday':day,'time':time,'duration_minutes':duration})
 if not clean:raise ValueError('schedule_required')
 c=database.connect();c.execute("UPDATE student_onboarding_sessions SET schedule_json=?,status='SCHEDULE_SET',updated_at=? WHERE id=?",(json.dumps(clean,ensure_ascii=False),_iso(),int(row['id'])));c.commit();c.close();return status_payload(token)
def complete(token,login,password):
 row=_active(_row(token))
 if row['status']!='SCHEDULE_SET' or not row.get('linked_user_id'):raise ValueError('onboarding_incomplete')
 uid=int(row['linked_user_id']);now=_iso();c=database.connect();c.execute('UPDATE users SET active=1,updated_at=? WHERE id=?',(now,uid));c.commit();c.close();result=student_auth.set_student_credentials(uid,login,password,revoke_existing=True);session=web_sessions.create_session('student',uid);c=database.connect();c.execute("UPDATE student_onboarding_sessions SET status='COMPLETED',completed_at=?,updated_at=? WHERE id=?",(now,now,int(row['id'])));c.commit();c.close();return {'status':'ok','user_id':uid,'login':result['login'],'session_token':session,'redirect':'/app/'}
def status_payload(token):
 row=_active(_row(token));user=None
 if row.get('linked_user_id'):
  u=database.get_user(int(row['linked_user_id']));user={'id':int(u['id']),'name':u['name'],'grade':u['grade'],'main_subject':u['main_subject'],'study_goal':u['study_goal']} if u else None
 try:schedule=json.loads(row.get('schedule_json') or '[]')
 except Exception:schedule=[]
 return {'token':row['token'],'mode':row['mode'],'preferred_channel':row['preferred_channel'],'status':row['status'],'name':row.get('name'),'grade':row.get('grade'),'subject':row.get('subject'),'study_goal':row.get('study_goal'),'region':row.get('region'),'timezone':row.get('timezone'),'schedule':schedule,'user':user,'provisional_user_created':bool(row.get('provisional_user_created')),'external_username':row.get('external_username'),'external_display_name':row.get('external_display_name'),'expires_at':row['expires_at']}
