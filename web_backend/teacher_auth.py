"""One-time login codes for the teacher web cabinet."""
import secrets
from datetime import datetime,timedelta
from database import connect,now_iso
from core import admin_roles
from web_backend import otp_secret
TTL_MINUTES=10;TEACHER_WEB_ROLES={'OWNER','ADMIN'}
def _digest(code):return otp_secret.digest(code)
def _can_use_teacher_web(telegram_id):
 if telegram_id is None:return False
 try:return admin_roles.role_for(int(telegram_id)) in TEACHER_WEB_ROLES
 except (TypeError,ValueError):return False
def ensure_table():
 conn=connect();conn.execute('CREATE TABLE IF NOT EXISTS teacher_web_login_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,admin_telegram_id INTEGER NOT NULL,code TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,used_at TEXT,created_at TEXT NOT NULL)');conn.execute('CREATE INDEX IF NOT EXISTS idx_teacher_web_code ON teacher_web_login_codes(code)');conn.commit();conn.close()
def issue_teacher_login_code(admin_telegram_id,ttl_minutes=TTL_MINUTES):
 admin_telegram_id=int(admin_telegram_id)
 if not _can_use_teacher_web(admin_telegram_id):raise PermissionError('teacher_web_access_denied')
 ensure_table();expires=(datetime.now()+timedelta(minutes=max(1,min(int(ttl_minutes),30)))).isoformat(timespec='seconds');conn=connect();conn.execute('UPDATE teacher_web_login_codes SET used_at=? WHERE admin_telegram_id=? AND used_at IS NULL',(now_iso(),admin_telegram_id))
 while True:
  code=f'{secrets.randbelow(1_000_000):06d}';d=_digest(code)
  if not conn.execute('SELECT 1 FROM teacher_web_login_codes WHERE code=?',(d,)).fetchone():break
 conn.execute('INSERT INTO teacher_web_login_codes(admin_telegram_id,code,expires_at,created_at) VALUES(?,?,?,?)',(admin_telegram_id,d,expires,now_iso()));conn.commit();conn.close();return code
def consume_teacher_login_code(code):
 ensure_table();code=''.join(ch for ch in str(code or '') if ch.isdigit())
 if len(code)!=6:return {'status':'invalid'}
 values=otp_secret.candidates(code);marks=','.join('?' for _ in values);conn=connect();row=conn.execute(f'SELECT * FROM teacher_web_login_codes WHERE code IN ({marks}) ORDER BY id DESC LIMIT 1',values).fetchone()
 if not row or row['used_at']:conn.close();return {'status':'invalid'}
 if datetime.fromisoformat(row['expires_at'])<datetime.now():conn.close();return {'status':'expired'}
 tid=int(row['admin_telegram_id'])
 if not _can_use_teacher_web(tid):conn.close();return {'status':'invalid'}
 cur=conn.execute('UPDATE teacher_web_login_codes SET used_at=? WHERE id=? AND used_at IS NULL',(now_iso(),int(row['id'])));conn.commit();conn.close()
 return {'status':'ok','admin_telegram_id':tid} if cur.rowcount else {'status':'invalid'}
