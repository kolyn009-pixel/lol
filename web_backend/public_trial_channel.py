"""Temporary Telegram/VK identity link for a public trial request.

This does not create a permanent student account. It only associates a verified
messenger identity with the temporary trial request so links and updates can be
delivered before conversion to a full student.
"""
from __future__ import annotations
from datetime import datetime,timedelta
import secrets,string
import database
from web_backend import public_trial

TOKEN_TTL_MINUTES=60
TG_BOT_URL='https://t.me/AdeliaTutorBot'
VK_MESSAGES_URL='https://vk.me/club241263797'

def _now():return datetime.now()
def _iso(v=None):return (v or _now()).isoformat(timespec='seconds')
def _token(prefix='TRIAL'):
 alphabet=string.ascii_uppercase+string.digits
 return prefix+'-'+''.join(secrets.choice(alphabet) for _ in range(10))
def ensure_schema():
 public_trial.ensure_schema();c=database.connect();cols={r['name'] for r in c.execute('PRAGMA table_info(public_trial_requests)').fetchall()}
 for name,kind in {'trial_channel':'TEXT','trial_channel_external_id':'TEXT','trial_channel_username':'TEXT','trial_channel_display_name':'TEXT','trial_link_token':'TEXT','trial_link_expires_at':'TEXT','trial_channel_verified_at':'TEXT'}.items():
  if name not in cols:c.execute(f'ALTER TABLE public_trial_requests ADD COLUMN {name} {kind}')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_public_trial_link_token ON public_trial_requests(trial_link_token) WHERE trial_link_token IS NOT NULL');c.commit();c.close()
def begin(request_id,channel):
 ensure_schema();row=public_trial.get(int(request_id))
 if not row:raise ValueError('request_not_found')
 if row['status'] in {'DECLINED','CLOSED','EXPIRED'}:raise ValueError('request_not_actionable')
 ch=str(channel or '').strip().upper()
 if ch not in {'TELEGRAM','VK'}:raise ValueError('invalid_channel')
 token=_token();exp=_now()+timedelta(minutes=TOKEN_TTL_MINUTES);c=database.connect();c.execute("UPDATE public_trial_requests SET trial_channel=?,trial_link_token=?,trial_link_expires_at=?,updated_at=? WHERE id=?",(ch,token,_iso(exp),_iso(),int(request_id)));c.commit();c.close()
 return {'status':'ok','request_id':int(request_id),'channel':ch,'token':token,'telegram_url':f'{TG_BOT_URL}?start=trial_{token}','vk_url':VK_MESSAGES_URL,'vk_code':token,'expires_at':_iso(exp)}
def _by_token(token):
 ensure_schema();c=database.connect();r=c.execute('SELECT * FROM public_trial_requests WHERE trial_link_token=? LIMIT 1',(str(token or '').strip().upper(),)).fetchone();c.close();return dict(r) if r else None
def confirm(token,channel,external_id,username=None,display_name=None):
 row=_by_token(token)
 if not row:raise ValueError('trial_link_not_found')
 if row.get('trial_link_expires_at') and datetime.fromisoformat(row['trial_link_expires_at'])<_now():raise ValueError('trial_link_expired')
 ch=str(channel or '').strip().upper();eid=str(external_id or '').strip()
 if ch!=str(row.get('trial_channel') or '').upper():raise ValueError('wrong_channel')
 existing=str(row.get('trial_channel_external_id') or '').strip()
 if existing and existing!=eid:raise ValueError('trial_identity_locked')
 c=database.connect();c.execute("UPDATE public_trial_requests SET trial_channel_external_id=?,trial_channel_username=?,trial_channel_display_name=?,trial_channel_verified_at=?,updated_at=? WHERE id=?",(eid,str(username or '').strip()[:100] or None,str(display_name or '').strip()[:160] or None,_iso(),_iso(),int(row['id'])));c.commit();c.close();return status(int(row['id']))
def status(request_id):
 ensure_schema();row=public_trial.get(int(request_id))
 if not row:raise ValueError('request_not_found')
 return {'request_id':int(row['id']),'request_status':row['status'],'channel':row.get('trial_channel'),'verified':bool(row.get('trial_channel_verified_at') and row.get('trial_channel_external_id')),'external_username':row.get('trial_channel_username'),'trial_start':row.get('trial_start') or row.get('selected_slot_start'),'trial_end':row.get('trial_end') or row.get('selected_slot_end'),'meeting_url':row.get('meeting_url'),'board_url':row.get('board_url')}
def pending_by_external(channel,external_id):
 ensure_schema();c=database.connect();r=c.execute("SELECT * FROM public_trial_requests WHERE trial_channel=? AND trial_channel_external_id=? AND trial_channel_verified_at IS NOT NULL AND status NOT IN ('CONVERTED','CLOSED','DECLINED','EXPIRED') ORDER BY id DESC LIMIT 1",(str(channel).upper(),str(external_id))).fetchone();c.close();return dict(r) if r else None
