"""Fast, read-only Stage 12 privacy/security checks.
Run on the server with the web-service environment:
    python -m web_backend.stage12_security_selftest
"""
from database import connect
from web_backend import api_v3,student_auth,teacher_auth,parent_auth,otp_secret
from web_backend.web_sessions import SESSION_TTL,LAST_SEEN_WRITE_INTERVAL

def _columns(conn,table):return {str(r['name']) for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
def _indexes(conn,table):return {str(r['name']) for r in conn.execute(f'PRAGMA index_list({table})').fetchall()}
def run():
 checks=[]
 def check(name,ok):checks.append((name,bool(ok)))
 student_auth.ensure_student_web_login_table();teacher_auth.ensure_table();parent_auth.ensure_tables();conn=connect()
 check('student OTP table exists',bool(_columns(conn,'student_web_login_codes')))
 check('teacher OTP table exists',bool(_columns(conn,'teacher_web_login_codes')))
 check('parent OTP hash column','code_hash' in _columns(conn,'parent_web_login_codes'))
 check('session token index','idx_web_sessions_token' in _indexes(conn,'web_sessions'))
 check('student credential login index','idx_student_web_credentials_login' in _indexes(conn,'student_web_credentials'))
 conn.close()
 check('OTP server secret configured',otp_secret.configured())
 check('session cookie lifetime bounded',300<=int(SESSION_TTL)<=60*60*24*180)
 check('last_seen writes throttled',int(LAST_SEEN_WRITE_INTERVAL)>=60)
 check('auth limiter enabled',api_v3._AUTH_MAX<=10 and api_v3._AUTH_WINDOW>=60)
 check('JSON body bounded',32*1024<=int(api_v3.MAX_JSON_BODY)<=1024*1024)
 check('owner-only finance routes','/api/teacher/finance/price' in api_v3._OWNER_ONLY_POST and '/api/teacher/finance/package' in api_v3._OWNER_ONLY_POST)
 check('student password cost',student_auth.PBKDF2_ITERATIONS>=300_000)
 if otp_secret.configured():
  a=student_auth._code_digest('123456');b=teacher_auth._digest('123456');c=parent_auth._hash('123456')
  check('OTP keyed digest format',a.startswith(otp_secret.PREFIX) and b.startswith(otp_secret.PREFIX) and c.startswith(otp_secret.PREFIX) and len(a)>64)
  check('OTP digest not plaintext',all(x!='123456' for x in (a,b,c)))
 else:
  check('OTP keyed digest format',False);check('OTP digest not plaintext',False)
 failed=[name for name,ok in checks if not ok]
 for name,ok in checks:print(('OK  ' if ok else 'FAIL')+name)
 if failed:raise SystemExit('Stage 12 security selftest failed: '+', '.join(failed))
 print(f'Stage 12 security selftest passed: {len(checks)} checks')
if __name__=='__main__':run()
