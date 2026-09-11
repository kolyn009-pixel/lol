"""Private browser manage tokens for public trial requests.

The browser receives the raw token once; only its SHA-256 hash is stored.
"""
from __future__ import annotations
import hashlib,secrets,string
import database
from web_backend import public_trial

ALPHABET='ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

def _new():return 'MANAGE-'+''.join(secrets.choice(ALPHABET) for _ in range(24))
def _hash(v):return hashlib.sha256(str(v or '').strip().upper().encode()).hexdigest()

def ensure_schema():
 public_trial.ensure_schema();c=database.connect();cols={r['name'] for r in c.execute('PRAGMA table_info(public_trial_requests)').fetchall()}
 if 'manage_token_hash' not in cols:c.execute('ALTER TABLE public_trial_requests ADD COLUMN manage_token_hash TEXT')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_public_trial_manage_hash ON public_trial_requests(manage_token_hash) WHERE manage_token_hash IS NOT NULL');c.commit();c.close()

def issue(request_id):
 ensure_schema();rid=int(request_id);row=public_trial.get(rid)
 if not row:raise ValueError('request_not_found')
 raw=_new();c=database.connect();c.execute('UPDATE public_trial_requests SET manage_token_hash=? WHERE id=?',(_hash(raw),rid));c.commit();c.close();return raw

def require(request_id,token):
 ensure_schema();rid=int(request_id);h=_hash(token);c=database.connect();r=c.execute('SELECT id,status FROM public_trial_requests WHERE id=? AND manage_token_hash=? LIMIT 1',(rid,h)).fetchone();c.close()
 if not r:raise PermissionError('invalid_manage_token')
 return {'request_id':rid,'status':r['status']}
