"""Secure Telegram/VK identity links for a public trial request.

Telegram and VK are independent links. Browser operations require the request
manage token. Raw messenger link tokens are returned once and only SHA-256
hashes are stored.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets

import database
from web_backend import public_trial, public_trial_access

TOKEN_TTL_MINUTES = 60
TG_BOT_URL = 'https://t.me/AdeliaTutorBot'
VK_MESSAGES_URL = 'https://vk.me/club241263797'
CHANNELS = {'TELEGRAM', 'VK'}
TERMINAL_STATUSES = {'DECLINED', 'CLOSED', 'EXPIRED', 'CONVERTED'}


def _now():return datetime.now()
def _iso(v=None):return (v or _now()).isoformat(timespec='seconds')
def _token(prefix='TRIAL'):
    alphabet='ABCDEFGHJKLMNPQRSTUVWXYZ23456789';return prefix+'-'+''.join(secrets.choice(alphabet) for _ in range(12))
def _hash(token):return hashlib.sha256(str(token or '').strip().upper().encode()).hexdigest()
def _channel(value):
    ch=str(value or '').strip().upper()
    if ch not in CHANNELS:raise ValueError('invalid_channel')
    return ch

def ensure_schema():
    public_trial.ensure_schema();c=database.connect();c.executescript("""
    CREATE TABLE IF NOT EXISTS public_trial_channel_links (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      request_id INTEGER NOT NULL,
      channel TEXT NOT NULL,
      token_hash TEXT,
      token_expires_at TEXT,
      external_id TEXT,
      username TEXT,
      display_name TEXT,
      verified_at TEXT,
      revoked_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(request_id, channel),
      FOREIGN KEY(request_id) REFERENCES public_trial_requests(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_trial_channel_token_hash
      ON public_trial_channel_links(token_hash) WHERE token_hash IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_trial_channel_external
      ON public_trial_channel_links(channel, external_id, verified_at);
    """);cols={r['name'] for r in c.execute('PRAGMA table_info(public_trial_channel_links)').fetchall()}
    if 'revoked_at' not in cols:c.execute('ALTER TABLE public_trial_channel_links ADD COLUMN revoked_at TEXT')
    c.commit();c.close()

def begin(request_id,channel,manage_token):
    ensure_schema();rid=int(request_id);public_trial_access.require(rid,manage_token);row=public_trial.get(rid)
    if not row:raise ValueError('request_not_found')
    if row['status'] in TERMINAL_STATUSES:raise ValueError('request_not_actionable')
    ch=_channel(channel);raw=_token();expires=_now()+timedelta(minutes=TOKEN_TTL_MINUTES);now=_iso();c=database.connect();existing=c.execute('SELECT external_id,verified_at FROM public_trial_channel_links WHERE request_id=? AND channel=?',(rid,ch)).fetchone()
    if existing and existing['external_id'] and existing['verified_at']:c.close();raise ValueError('trial_channel_already_linked')
    c.execute("""INSERT INTO public_trial_channel_links(request_id,channel,token_hash,token_expires_at,revoked_at,created_at,updated_at) VALUES(?,?,?,?,NULL,?,?) ON CONFLICT(request_id,channel) DO UPDATE SET token_hash=excluded.token_hash,token_expires_at=excluded.token_expires_at,revoked_at=NULL,updated_at=excluded.updated_at""",(rid,ch,_hash(raw),_iso(expires),now,now));c.commit();c.close();return {'status':'ok','request_id':rid,'channel':ch,'token':raw,'telegram_url':f'{TG_BOT_URL}?start=trial_{raw}' if ch=='TELEGRAM' else None,'vk_url':VK_MESSAGES_URL if ch=='VK' else None,'vk_code':raw if ch=='VK' else None,'expires_at':_iso(expires)}
def _by_token(token):
    ensure_schema();c=database.connect();r=c.execute("""SELECT l.*,r.status AS request_status FROM public_trial_channel_links l JOIN public_trial_requests r ON r.id=l.request_id WHERE l.token_hash=? AND l.revoked_at IS NULL LIMIT 1""",(_hash(token),)).fetchone();c.close();return dict(r) if r else None
def confirm(token,channel,external_id,username=None,display_name=None):
    row=_by_token(token)
    if not row:raise ValueError('trial_link_not_found')
    ch=_channel(channel);eid=str(external_id or '').strip()
    if not eid:raise ValueError('external_id_required')
    if ch!=str(row.get('channel') or '').upper():raise ValueError('wrong_channel')
    if row.get('token_expires_at') and datetime.fromisoformat(row['token_expires_at'])<=_now():raise ValueError('trial_link_expired')
    if row.get('request_status') in TERMINAL_STATUSES:raise ValueError('request_not_actionable')
    existing=str(row.get('external_id') or '').strip()
    if existing and existing!=eid:raise ValueError('trial_identity_locked')
    now=_iso();c=database.connect();collision=c.execute("""SELECT request_id FROM public_trial_channel_links WHERE channel=? AND external_id=? AND verified_at IS NOT NULL AND request_id<>? LIMIT 1""",(ch,eid,int(row['request_id']))).fetchone()
    if collision:c.close();raise ValueError('trial_identity_in_use')
    cur=c.execute("""UPDATE public_trial_channel_links SET external_id=?,username=?,display_name=?,verified_at=COALESCE(verified_at,?),token_hash=NULL,token_expires_at=NULL,revoked_at=NULL,updated_at=? WHERE id=? AND token_hash=? AND revoked_at IS NULL""",(eid,str(username or '').strip()[:100] or None,str(display_name or '').strip()[:160] or None,now,now,int(row['id']),_hash(token)))
    if cur.rowcount!=1:c.rollback();c.close();raise ValueError('trial_link_not_found')
    c.commit();c.close();public_trial.activate_linked_request(int(row['request_id']),ch,username,display_name);return _status_payload(int(row['request_id']))
def _status_payload(request_id):
    ensure_schema();row=public_trial.get(int(request_id))
    if not row:raise ValueError('request_not_found')
    c=database.connect();links=c.execute("""SELECT channel,external_id,username,display_name,verified_at FROM public_trial_channel_links WHERE request_id=? ORDER BY channel""",(int(request_id),)).fetchall();c.close();found={str(r['channel']).upper():r for r in links};channels={}
    for ch in ('TELEGRAM','VK'):
        r=found.get(ch);linked=bool(r and r['verified_at'] and r['external_id']);channels[ch.lower()]={'linked':linked,'verified':linked,'external_username':r['username'] if r else None,'display_name':r['display_name'] if r else None}
    return {'request_id':int(row['id']),'request_status':row['status'],'verified':any(x['linked'] for x in channels.values()),'telegram':channels['telegram'],'vk':channels['vk'],'channels':channels,'trial_start':row.get('trial_start') or row.get('selected_slot_start'),'trial_end':row.get('trial_end') or row.get('selected_slot_end'),'meeting_url':row.get('meeting_url'),'board_url':row.get('board_url')}
def status(request_id,manage_token):
    rid=int(request_id);public_trial_access.require(rid,manage_token);return _status_payload(rid)
def pending_by_external(channel,external_id):
    ensure_schema();ch=_channel(channel);c=database.connect();r=c.execute("""SELECT p.* FROM public_trial_channel_links l JOIN public_trial_requests p ON p.id=l.request_id WHERE l.channel=? AND l.external_id=? AND l.verified_at IS NOT NULL AND l.revoked_at IS NULL AND p.status NOT IN ('CONVERTED','CLOSED','DECLINED','EXPIRED') ORDER BY l.id DESC LIMIT 1""",(ch,str(external_id))).fetchone();c.close();return dict(r) if r else None
def channels_for_request(request_id):
    """Internal helper for trusted server-side callers; never expose by request id."""
    return _status_payload(int(request_id)).get('channels',{})
def identity_for_request(request_id,channel):
    """Return a verified messenger identity for trusted server-side continuation only."""
    ensure_schema();ch=_channel(channel);c=database.connect();r=c.execute("""SELECT request_id,channel,external_id,username,display_name,verified_at FROM public_trial_channel_links WHERE request_id=? AND channel=? AND verified_at IS NOT NULL AND revoked_at IS NULL AND external_id IS NOT NULL LIMIT 1""",(int(request_id),ch)).fetchone();c.close()
    if not r:raise ValueError('trial_channel_not_linked')
    return dict(r)
