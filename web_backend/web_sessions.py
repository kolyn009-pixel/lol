"""Persistent web sessions for Adelia.

Raw bearer tokens are returned only to the browser cookie. SQLite stores only a
SHA-256 digest. Schema setup is process-cached so authenticated requests do not
open an extra SQLite connection just to run CREATE IF NOT EXISTS statements.
"""
from __future__ import annotations
import hashlib,secrets,time,threading
from datetime import datetime,timedelta
from database import connect,now_iso

SESSION_TTL=60*60*24*180
LAST_SEEN_WRITE_INTERVAL=300
_ALLOWED_ROLES={"student","parent","teacher"}
_TABLE_READY=False
_TABLE_LOCK=threading.Lock()

def _digest(token):return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()
def ensure_table():
 global _TABLE_READY
 if _TABLE_READY:return
 with _TABLE_LOCK:
  if _TABLE_READY:return
  conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS web_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,token_hash TEXT UNIQUE NOT NULL,role TEXT NOT NULL,entity_id INTEGER NOT NULL,expires_at INTEGER NOT NULL,created_at TEXT NOT NULL,last_seen_at TEXT,revoked_at TEXT);CREATE INDEX IF NOT EXISTS idx_web_sessions_token ON web_sessions(token_hash);CREATE INDEX IF NOT EXISTS idx_web_sessions_expiry ON web_sessions(expires_at);CREATE INDEX IF NOT EXISTS idx_web_sessions_identity ON web_sessions(role,entity_id,revoked_at,expires_at);""");conn.commit();conn.close();_TABLE_READY=True
def _identity_active(conn,role,entity_id):
 role=str(role or '').lower();entity_id=int(entity_id)
 if role=='student':return bool(conn.execute('SELECT 1 FROM users WHERE id=? AND active=1 LIMIT 1',(entity_id,)).fetchone())
 if role=='parent':return bool(conn.execute('SELECT 1 FROM parent_accounts WHERE id=? AND active=1 LIMIT 1',(entity_id,)).fetchone())
 if role=='teacher':
  row=conn.execute('SELECT role FROM admin_accounts WHERE telegram_id=? AND active=1 LIMIT 1',(entity_id,)).fetchone()
  return bool(row and str(row['role']).upper() in {'OWNER','ADMIN'})
 return False
def create_session(role,entity_id,ttl_seconds=SESSION_TTL):
 ensure_table();role=str(role or '').strip().lower()
 if role not in _ALLOWED_ROLES:raise ValueError('invalid_session_role')
 entity_id=int(entity_id);ttl_seconds=max(300,min(int(ttl_seconds),SESSION_TTL));token=secrets.token_urlsafe(32);expires=int(time.time())+ttl_seconds;conn=connect()
 if not _identity_active(conn,role,entity_id):conn.close();raise PermissionError('session_identity_inactive')
 stamp=now_iso();conn.execute('INSERT INTO web_sessions(token_hash,role,entity_id,expires_at,created_at,last_seen_at) VALUES(?,?,?,?,?,?)',(_digest(token),role,entity_id,expires,stamp,stamp));conn.execute('DELETE FROM web_sessions WHERE expires_at < ? OR revoked_at IS NOT NULL',(int(time.time())-86400,));conn.commit();conn.close();return token
def _last_seen_due(value):
 if not value:return True
 try:seen=datetime.fromisoformat(str(value))
 except Exception:return True
 return datetime.now()-seen>=timedelta(seconds=LAST_SEEN_WRITE_INTERVAL)
def read_session(token):
 if not token:return None
 ensure_table();now=int(time.time());conn=connect();row=conn.execute('SELECT id,role,entity_id,expires_at,last_seen_at FROM web_sessions WHERE token_hash=? AND revoked_at IS NULL AND expires_at>=? LIMIT 1',(_digest(token),now)).fetchone()
 if not row:conn.close();return None
 if row['role'] not in _ALLOWED_ROLES or not _identity_active(conn,row['role'],row['entity_id']):
  conn.execute('UPDATE web_sessions SET revoked_at=? WHERE id=?',(now_iso(),int(row['id'])));conn.commit();conn.close();return None
 if _last_seen_due(row['last_seen_at']):conn.execute('UPDATE web_sessions SET last_seen_at=? WHERE id=?',(now_iso(),int(row['id'])));conn.commit()
 role=str(row['role']);entity_id=int(row['entity_id']);item={'role':role,'id':entity_id,'expires':int(row['expires_at'])}
 if role=='teacher':item['admin_telegram_id']=entity_id
 conn.close();return item
def revoke_session(token):
 if not token:return False
 ensure_table();conn=connect();cur=conn.execute('UPDATE web_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL',(now_iso(),_digest(token)));conn.commit();changed=bool(cur.rowcount);conn.close();return changed
def revoke_identity_sessions(role,entity_id):
 role=str(role or '').strip().lower()
 if role not in _ALLOWED_ROLES:return 0
 ensure_table();conn=connect();cur=conn.execute('UPDATE web_sessions SET revoked_at=? WHERE role=? AND entity_id=? AND revoked_at IS NULL',(now_iso(),role,int(entity_id)));conn.commit();count=int(cur.rowcount or 0);conn.close();return count
