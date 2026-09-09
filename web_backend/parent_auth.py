"""One-time parent login codes for the Stage 9 web cabinet."""
from __future__ import annotations
import secrets,sqlite3
from datetime import datetime,timedelta
from database import connect,now_iso
from web_backend import otp_secret
TTL_MINUTES=10
def ensure_tables():
 conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS parent_web_login_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER NOT NULL,code_hash TEXT NOT NULL UNIQUE,expires_at TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,consumed_at TEXT,created_at TEXT NOT NULL,FOREIGN KEY(parent_id) REFERENCES parent_accounts(id) ON DELETE CASCADE);CREATE INDEX IF NOT EXISTS idx_parent_web_login_active ON parent_web_login_codes(code_hash,expires_at,consumed_at);""");conn.commit();conn.close()
def _hash(code):return otp_secret.digest(code)
def create_parent_login_code(parent_id,ttl_minutes=TTL_MINUTES):
 ensure_tables();pid=int(parent_id);conn=connect();p=conn.execute('SELECT id FROM parent_accounts WHERE id=? AND active=1',(pid,)).fetchone()
 if not p:conn.close();raise ValueError('parent_not_found')
 now=datetime.now();expires=now+timedelta(minutes=max(2,min(int(ttl_minutes or TTL_MINUTES),30)));conn.execute('DELETE FROM parent_web_login_codes WHERE parent_id=? AND consumed_at IS NULL',(pid,))
 for _ in range(20):
  code=f'{secrets.randbelow(1_000_000):06d}'
  try:
   conn.execute('INSERT INTO parent_web_login_codes(parent_id,code_hash,expires_at,created_at) VALUES(?,?,?,?)',(pid,_hash(code),expires.isoformat(timespec='seconds'),now.isoformat(timespec='seconds')));conn.commit();conn.close();return {'status':'ok','code':code,'expires_at':expires.isoformat(timespec='seconds')}
  except sqlite3.IntegrityError:continue
 conn.rollback();conn.close();raise RuntimeError('parent_code_generation_failed')
def consume_parent_login_code(code):
 ensure_tables();raw=str(code or '').strip()
 if len(raw)!=6 or not raw.isdigit():return {'status':'invalid_code'}
 values=otp_secret.candidates(raw);marks=','.join('?' for _ in values);now=datetime.now();conn=connect();row=conn.execute(f'SELECT * FROM parent_web_login_codes WHERE code_hash IN ({marks}) ORDER BY id DESC LIMIT 1',values).fetchone()
 if not row:conn.close();return {'status':'invalid_code'}
 if row['consumed_at'] is not None:conn.close();return {'status':'used_code'}
 try:expires=datetime.fromisoformat(str(row['expires_at']))
 except Exception:expires=now-timedelta(seconds=1)
 if expires<now:conn.execute('UPDATE parent_web_login_codes SET consumed_at=? WHERE id=?',(now_iso(),int(row['id'])));conn.commit();conn.close();return {'status':'expired_code'}
 parent=conn.execute('SELECT id,name FROM parent_accounts WHERE id=? AND active=1',(int(row['parent_id']),)).fetchone()
 if not parent:conn.execute('UPDATE parent_web_login_codes SET consumed_at=? WHERE id=?',(now_iso(),int(row['id'])));conn.commit();conn.close();return {'status':'parent_not_found'}
 cur=conn.execute('UPDATE parent_web_login_codes SET consumed_at=? WHERE id=? AND consumed_at IS NULL',(now_iso(),int(row['id'])));conn.commit();conn.close();return {'status':'ok','parent':dict(parent)} if cur.rowcount else {'status':'used_code'}
