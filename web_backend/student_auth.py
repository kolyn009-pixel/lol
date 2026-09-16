"""Student web authentication for Adelia."""
import base64,hashlib,hmac,re,secrets
from datetime import datetime,timedelta
from database import connect,now_iso
from web_backend.web_sessions import revoke_identity_sessions
from web_backend import otp_secret

CODE_TTL_MINUTES=10;PBKDF2_ITERATIONS=600_000
_LOGIN_RE=re.compile(r"^[a-z0-9._-]{4,32}$");_DUMMY_SALT=b"adelia-auth-dummy"

def ensure_student_web_login_table():
 conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS student_web_login_codes(id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,code TEXT UNIQUE NOT NULL,expires_at TEXT NOT NULL,used_at TEXT,created_at TEXT NOT NULL,FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE);CREATE INDEX IF NOT EXISTS idx_student_web_login_code ON student_web_login_codes(code);CREATE TABLE IF NOT EXISTS student_web_credentials(student_id INTEGER PRIMARY KEY,login TEXT NOT NULL COLLATE NOCASE UNIQUE,password_hash TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT,FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE);CREATE UNIQUE INDEX IF NOT EXISTS idx_student_web_credentials_login ON student_web_credentials(login COLLATE NOCASE);""");conn.commit();conn.close()
def _new_code():return f"{secrets.randbelow(1_000_000):06d}"
def _code_digest(code):return otp_secret.digest(code)
def _code_candidates(code):return otp_secret.candidates(code)
def _normalize_login(login):
 v=str(login or '').strip().lower()
 if not _LOGIN_RE.fullmatch(v):raise ValueError('invalid_login')
 return v
def _validate_password(password):
 v=str(password or '')
 if len(v)<8:raise ValueError('password_too_short')
 if len(v)>128:raise ValueError('password_too_long')
 return v
def _password_hash(password):
 password=_validate_password(password);salt=secrets.token_bytes(16);d=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,PBKDF2_ITERATIONS);return 'pbkdf2_sha256${}${}${}'.format(PBKDF2_ITERATIONS,base64.urlsafe_b64encode(salt).decode(),base64.urlsafe_b64encode(d).decode())
def _password_matches(password,encoded):
 try:
  scheme,it,salt_text,digest_text=str(encoded).split('$',3)
  if scheme!='pbkdf2_sha256':return False
  salt=base64.urlsafe_b64decode(salt_text.encode());expected=base64.urlsafe_b64decode(digest_text.encode());actual=hashlib.pbkdf2_hmac('sha256',str(password or '').encode(),salt,int(it));return hmac.compare_digest(actual,expected)
 except Exception:return False
def _dummy_password_work(password):hashlib.pbkdf2_hmac('sha256',str(password or '').encode(),_DUMMY_SALT,PBKDF2_ITERATIONS)
def has_student_credentials(student_id):
 ensure_student_web_login_table();conn=connect();row=conn.execute('SELECT 1 FROM student_web_credentials WHERE student_id=? LIMIT 1',(int(student_id),)).fetchone();conn.close();return bool(row)
def _validate_credential_change(student_id,login,password):
 ensure_student_web_login_table();student_id=int(student_id);login=_normalize_login(login);password=_validate_password(password);conn=connect();student=conn.execute('SELECT id FROM users WHERE id=? LIMIT 1',(student_id,)).fetchone()
 if not student:conn.close();raise ValueError('student_not_found')
 owner=conn.execute('SELECT student_id FROM student_web_credentials WHERE login=? COLLATE NOCASE LIMIT 1',(login,)).fetchone();conn.close()
 if owner and int(owner['student_id'])!=student_id:raise ValueError('login_taken')
 return login,password
def _ensure_social_profile(student_id):
 from web_backend import student_social_profile
 student_social_profile.ensure_schema();student_social_profile.public_profile(int(student_id),viewer_id=int(student_id))
def set_student_credentials(student_id,login,password,revoke_existing=True):
 ensure_student_web_login_table();student_id=int(student_id);login,password=_validate_credential_change(student_id,login,password);ph=_password_hash(password);conn=connect();existing=conn.execute('SELECT student_id FROM student_web_credentials WHERE student_id=?',(student_id,)).fetchone()
 if existing:conn.execute('UPDATE student_web_credentials SET login=?,password_hash=?,updated_at=? WHERE student_id=?',(login,ph,now_iso(),student_id))
 else:conn.execute('INSERT INTO student_web_credentials(student_id,login,password_hash,created_at) VALUES(?,?,?,?)',(student_id,login,ph,now_iso()))
 conn.commit();conn.close();_ensure_social_profile(student_id)
 if revoke_existing:revoke_identity_sessions('student',student_id)
 return {'status':'ok','login':login,'profile_created':True}
def authenticate_student(login,password):
 ensure_student_web_login_table()
 try:login=_normalize_login(login)
 except ValueError:_dummy_password_work(password);return {'status':'invalid','student':None}
 conn=connect();row=conn.execute('SELECT u.id,u.name,u.grade,c.password_hash FROM student_web_credentials c JOIN users u ON u.id=c.student_id WHERE c.login=? COLLATE NOCASE AND u.active=1 LIMIT 1',(login,)).fetchone()
 if not row:conn.close();_dummy_password_work(password);return {'status':'invalid','student':None}
 if not _password_matches(password,row['password_hash']):conn.close();return {'status':'invalid','student':None}
 student={'id':int(row['id']),'name':row['name'],'grade':row['grade']};conn.close();_ensure_social_profile(student['id']);return {'status':'ok','student':student}
def issue_student_login_code(student_id,ttl_minutes=CODE_TTL_MINUTES):
 ensure_student_web_login_table();student_id=int(student_id);ttl_minutes=max(1,min(int(ttl_minutes),30));expires=(datetime.now()+timedelta(minutes=ttl_minutes)).isoformat(timespec='seconds');conn=connect();student=conn.execute('SELECT id FROM users WHERE id=? AND active=1',(student_id,)).fetchone()
 if not student:conn.close();raise ValueError('student_not_found')
 conn.execute('UPDATE student_web_login_codes SET used_at=? WHERE student_id=? AND used_at IS NULL',(now_iso(),student_id))
 while True:
  code=_new_code();digest=_code_digest(code);exists=conn.execute('SELECT 1 FROM student_web_login_codes WHERE code=?',(digest,)).fetchone()
  if not exists:break
 conn.execute('INSERT INTO student_web_login_codes(student_id,code,expires_at,created_at) VALUES(?,?,?,?)',(student_id,digest,expires,now_iso()));conn.commit();conn.close();return code
def _peek_plain_code(code):
 code=''.join(ch for ch in str(code or '') if ch.isdigit())
 if len(code)!=6:return {'status':'invalid','student':None}
 values=_code_candidates(code);marks=','.join('?' for _ in values);conn=connect();row=conn.execute(f'SELECT c.id AS code_id,c.expires_at,c.used_at,u.id,u.name,u.grade FROM student_web_login_codes c JOIN users u ON u.id=c.student_id WHERE c.code IN ({marks}) AND u.active=1 ORDER BY c.id DESC LIMIT 1',values).fetchone();conn.close()
 if not row or row['used_at']:return {'status':'invalid','student':None}
 if datetime.fromisoformat(row['expires_at'])<datetime.now():return {'status':'expired','student':None}
 return {'status':'ok','code_id':int(row['code_id']),'student':{'id':int(row['id']),'name':row['name'],'grade':row['grade']}}
def peek_student_login_code(code):
 """Validate a one-time code without consuming it; used by two-step onboarding."""
 result=_peek_plain_code(code)
 if result.get('status')!='ok':return {'status':result.get('status','invalid'),'student':None}
 return {'status':'ok','student':result['student']}
def _consume_plain_code(code):
 result=_peek_plain_code(code)
 if result.get('status')!='ok':return result
 conn=connect();cur=conn.execute('UPDATE student_web_login_codes SET used_at=? WHERE id=? AND used_at IS NULL',(now_iso(),int(result['code_id'])));conn.commit();conn.close()
 if not cur.rowcount:return {'status':'invalid','student':None}
 _ensure_social_profile(result['student']['id']);return {'status':'ok','student':result['student']}
def consume_student_login_code(payload):
 ensure_student_web_login_table();raw=str(payload or '')
 if raw.startswith('login:'):
  parts=raw.split(':',2);return authenticate_student(parts[1],parts[2]) if len(parts)==3 else {'status':'invalid','student':None}
 if raw.startswith('setup:'):
  parts=raw.split(':',3)
  if len(parts)!=4:return {'status':'invalid','student':None}
  preview=_peek_plain_code(parts[1])
  if preview.get('status')!='ok':return preview
  try:_validate_credential_change(preview['student']['id'],parts[2],parts[3])
  except ValueError as exc:return {'status':str(exc),'student':None}
  result=_consume_plain_code(parts[1])
  if result.get('status')!='ok':return result
  try:set_student_credentials(result['student']['id'],parts[2],parts[3],True)
  except ValueError as exc:return {'status':str(exc),'student':None}
  return result
 return _consume_plain_code(raw)
