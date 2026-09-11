"""Temporary Telegram/VK identity links for a public trial request.

Links are stored in a dedicated table so Telegram and VK can coexist for the same
trial. Raw one-time codes are never persisted; only SHA-256 hashes are stored.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets
import string

import database
from web_backend import public_trial

TOKEN_TTL_MINUTES = 60
TG_BOT_URL = 'https://t.me/AdeliaTutorBot'
VK_MESSAGES_URL = 'https://vk.me/club241263797'
CHANNELS = {'TELEGRAM', 'VK'}


def _now():
    return datetime.now()


def _iso(v=None):
    return (v or _now()).isoformat(timespec='seconds')


def _token(prefix='TRIAL'):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return prefix + '-' + ''.join(secrets.choice(alphabet) for _ in range(12))


def _hash(token):
    return hashlib.sha256(str(token or '').strip().upper().encode()).hexdigest()


def ensure_schema():
    public_trial.ensure_schema()
    c = database.connect()
    c.executescript("""
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
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(request_id, channel),
      FOREIGN KEY(request_id) REFERENCES public_trial_requests(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_trial_channel_token_hash
      ON public_trial_channel_links(token_hash) WHERE token_hash IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_trial_channel_external
      ON public_trial_channel_links(channel, external_id, verified_at);
    """)
    c.commit()
    c.close()


def begin(request_id, channel):
    ensure_schema()
    row = public_trial.get(int(request_id))
    if not row:
        raise ValueError('request_not_found')
    if row['status'] in {'DECLINED', 'CLOSED', 'EXPIRED', 'CONVERTED'}:
        raise ValueError('request_not_actionable')
    ch = str(channel or '').strip().upper()
    if ch not in CHANNELS:
        raise ValueError('invalid_channel')

    raw = _token()
    expires = _now() + timedelta(minutes=TOKEN_TTL_MINUTES)
    now = _iso()
    c = database.connect()
    c.execute(
        """INSERT INTO public_trial_channel_links(
             request_id,channel,token_hash,token_expires_at,created_at,updated_at
           ) VALUES(?,?,?,?,?,?)
           ON CONFLICT(request_id,channel) DO UPDATE SET
             token_hash=excluded.token_hash,
             token_expires_at=excluded.token_expires_at,
             updated_at=excluded.updated_at""",
        (int(request_id), ch, _hash(raw), _iso(expires), now, now),
    )
    c.commit()
    c.close()
    return {
        'status': 'ok',
        'request_id': int(request_id),
        'channel': ch,
        'token': raw,
        'telegram_url': f'{TG_BOT_URL}?start=trial_{raw}' if ch == 'TELEGRAM' else None,
        'vk_url': VK_MESSAGES_URL if ch == 'VK' else None,
        'vk_code': raw if ch == 'VK' else None,
        'expires_at': _iso(expires),
    }


def _by_token(token):
    ensure_schema()
    c = database.connect()
    r = c.execute(
        """SELECT l.*,r.status AS request_status
           FROM public_trial_channel_links l
           JOIN public_trial_requests r ON r.id=l.request_id
           WHERE l.token_hash=? LIMIT 1""",
        (_hash(token),),
    ).fetchone()
    c.close()
    return dict(r) if r else None


def confirm(token, channel, external_id, username=None, display_name=None):
    row = _by_token(token)
    if not row:
        raise ValueError('trial_link_not_found')
    ch = str(channel or '').strip().upper()
    eid = str(external_id or '').strip()
    if ch != str(row.get('channel') or '').upper():
        raise ValueError('wrong_channel')
    if row.get('token_expires_at') and datetime.fromisoformat(row['token_expires_at']) < _now():
        raise ValueError('trial_link_expired')
    if row.get('request_status') in {'DECLINED','CLOSED','EXPIRED','CONVERTED'}:
        raise ValueError('request_not_actionable')
    existing = str(row.get('external_id') or '').strip()
    if existing and existing != eid:
        raise ValueError('trial_identity_locked')

    c = database.connect()
    c.execute(
        """UPDATE public_trial_channel_links
           SET external_id=?,username=?,display_name=?,verified_at=COALESCE(verified_at,?),
               token_hash=NULL,token_expires_at=NULL,updated_at=?
           WHERE id=?""",
        (
            eid,
            str(username or '').strip()[:100] or None,
            str(display_name or '').strip()[:160] or None,
            _iso(),
            _iso(),
            int(row['id']),
        ),
    )
    c.commit()
    c.close()
    return status(int(row['request_id']))


def status(request_id):
    ensure_schema()
    row = public_trial.get(int(request_id))
    if not row:
        raise ValueError('request_not_found')
    c = database.connect()
    links = c.execute(
        """SELECT channel,external_id,username,display_name,verified_at
           FROM public_trial_channel_links WHERE request_id=? ORDER BY channel""",
        (int(request_id),),
    ).fetchall()
    c.close()
    channels = {
        r['channel']: {
            'verified': bool(r['verified_at'] and r['external_id']),
            'external_username': r['username'],
            'display_name': r['display_name'],
        }
        for r in links
    }
    return {
        'request_id': int(row['id']),
        'request_status': row['status'],
        'verified': any(x['verified'] for x in channels.values()),
        'channels': channels,
        'trial_start': row.get('trial_start') or row.get('selected_slot_start'),
        'trial_end': row.get('trial_end') or row.get('selected_slot_end'),
        'meeting_url': row.get('meeting_url'),
        'board_url': row.get('board_url'),
    }


def pending_by_external(channel, external_id):
    ensure_schema()
    ch = str(channel or '').strip().upper()
    c = database.connect()
    r = c.execute(
        """SELECT p.*
           FROM public_trial_channel_links l
           JOIN public_trial_requests p ON p.id=l.request_id
           WHERE l.channel=? AND l.external_id=? AND l.verified_at IS NOT NULL
             AND p.status NOT IN ('CONVERTED','CLOSED','DECLINED','EXPIRED')
           ORDER BY l.id DESC LIMIT 1""",
        (ch, str(external_id)),
    ).fetchone()
    c.close()
    return dict(r) if r else None


def channels_for_request(request_id):
    return status(request_id).get('channels', {})
