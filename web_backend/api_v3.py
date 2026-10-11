"""Adelia web API v3: Stage 12 privacy/security hardening on top of api_v2."""
from __future__ import annotations
import ipaddress,json,time
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from core import admin_roles
from web_backend import api as v1,api_v2,otp_secret
from web_backend.lesson_join import student_join
from web_backend.student_portal import set_student_timezone
from web_backend.teacher_display_timezone import preference as teacher_timezone, set_preference as set_teacher_timezone, dashboard_with_instants
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_self_service import (
 regular_schedules as student_regular_schedules,
 pause_schedule as student_pause_schedule,
 resume_schedule as student_resume_schedule,
 vacation as student_vacation,
 resume_all as student_resume_all,
 sickness as student_sickness,
 cancel_lesson as student_cancel_lesson,
 request_reschedule as student_request_reschedule,
 lesson_actions as student_lesson_actions,
)
_AUTH_LIMITS={};_AUTH_WINDOW=300;_AUTH_MAX=8;MAX_JSON_BODY=256*1024
_OWNER_ONLY_POST={'/api/teacher/finance/price','/api/teacher/finance/override','/api/teacher/finance/override/delete','/api/teacher/finance/package'}
_LOOPBACKS={'127.0.0.1','::1'}
def _valid_ip(value):
 try:return str(ipaddress.ip_address(str(value or '').strip()))
 except ValueError:return None
def _auth_allowed(ip,route):
 now=time.time();key=(str(ip or ''),str(route or ''));start,count=_AUTH_LIMITS.get(key,(now,0))
 if now-start>_AUTH_WINDOW:start,count=now,0
 count+=1;_AUTH_LIMITS[key]=(start,count)
 if len(_AUTH_LIMITS)>5000:
  for k,v in list(_AUTH_LIMITS.items()):
   if now-v[0]>_AUTH_WINDOW:_AUTH_LIMITS.pop(k,None)
 return count<=_AUTH_MAX
class Handler(api_v2.Handler):
 server_version='AdeliaWeb/3.8'
 def _client_ip(self):
  peer=_valid_ip(self.client_address[0]) or str(self.client_address[0])
  if peer not in _LOOPBACKS:return peer
  real=_valid_ip(self.headers.get('X-Real-IP'))
  if real:return real
  forwarded=str(self.headers.get('X-Forwarded-For') or '')
  if forwarded:
   first=_valid_ip(forwarded.split(',',1)[0])
   if first:return first
  return peer
 def _body(self):
  try:total=int(self.headers.get('Content-Length','0') or 0)
  except Exception:return None
  if total<0:return None
  if total>MAX_JSON_BODY:self._body_too_large=True;return None
  self._body_too_large=False
  try:return json.loads(self.rfile.read(total) or b'{}')
  except Exception:return None
 def log_message(self,fmt,*args):
  try:path=urlparse(self.path).path
  except Exception:path='?'
  print('[web-api]',self._client_ip(),self.command,path,flush=True)
 def end_headers(self):
  self.send_header('X-Frame-Options','DENY');self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()');self.send_header('Cross-Origin-Opener-Policy','same-origin');self.send_header('Cross-Origin-Resource-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; font-src 'self' data: https://cdn.jsdelivr.net; img-src 'self' data: blob:; connect-src 'self'");super().end_headers()
 def _same_origin_write(self):
  origin=str(self.headers.get('Origin') or '').strip()
  if not origin:return True
  host=str(self.headers.get('Host') or '').strip().lower()
  if not host:return False
  try:parsed=urlparse(origin)
  except Exception:return False
  return parsed.scheme in {'https','http'} and bool(parsed.netloc) and parsed.netloc.lower()==host
 def _owner(self):
  auth=self._teacher()
  if not auth:return None
  try:return auth if admin_roles.role_for(int(auth['id']))=='OWNER' else None
  except Exception:return None
 def _student_self_service_error(self,exc):
  if isinstance(exc,PermissionError):return self._json(404,{'error':str(exc) or 'not_found'})
  if isinstance(exc,(TypeError,ValueError)):return self._json(409,{'error':str(exc) or 'invalid_request'})
  print('[web-api] student self-service error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
 def do_GET(self):
  u=urlparse(self.path);path=u.path;q=parse_qs(u.query)
  if path=='/api/auth/me':
   auth=self._auth()
   if not auth:return self._json(200,{'authenticated':False,'session':None})
   return self._json(200,{'authenticated':True,'role':auth.get('role'),'session':{'role':auth.get('role')}})
  if path in {'/api/teacher/display-timezone','/api/teacher/dashboard'}:
   auth=self._teacher()
   if not auth:return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,teacher_timezone(int(auth['id'])) if path.endswith('/display-timezone') else dashboard_with_instants(int(auth['id'])))
   except Exception as exc:print('[web-api] teacher time display error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path in {'/api/student/self-service/regular-schedules','/api/student/self-service/lesson-actions'}:
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   try:
    uid=int(auth['id'])
    if path.endswith('/regular-schedules'):return self._json(200,{'items':student_regular_schedules(uid)})
    return self._json(200,student_lesson_actions(uid,int(q.get('lesson_id',['0'])[0])))
   except Exception as exc:return self._student_self_service_error(exc)
  return super().do_GET()
 def do_POST(self):
  path=urlparse(self.path).path
  if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
  try:declared=int(self.headers.get('Content-Length','0') or 0)
  except Exception:declared=0
  if declared>MAX_JSON_BODY and path!='/api/teacher/pdf-import/upload':return self._json(413,{'error':'request_too_large'})
  if path in _OWNER_ONLY_POST and not self._owner():return self._json(403,{'error':'owner_required'})
  if path in {'/api/auth/student/code','/api/auth/teacher/code','/api/auth/parent/code'} and not _auth_allowed(self._client_ip(),path):return self._json(429,{'error':'too_many_attempts'})
  if path=='/api/teacher/display-timezone':
   auth=self._teacher()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(413 if getattr(self,'_body_too_large',False) else 400,{'error':'request_too_large' if getattr(self,'_body_too_large',False) else 'invalid_json'})
   if not isinstance(body,dict):return self._json(400,{'error':'invalid_json'})
   try:return self._json(200,set_teacher_timezone(int(auth['id']),body.get('zone')))
   except ValueError:return self._json(400,{'error':'invalid_timezone'})
   except Exception as exc:print('[web-api] teacher display timezone error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/student/timezone':
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(413 if getattr(self,'_body_too_large',False) else 400,{'error':'request_too_large' if getattr(self,'_body_too_large',False) else 'invalid_json'})
   if not isinstance(body,dict):return self._json(400,{'error':'invalid_json'})
   try:return self._json(200,set_student_timezone(int(auth['id']),body.get('zone')))
   except ValueError:return self._json(400,{'error':'invalid_timezone'})
   except PermissionError:return self._json(404,{'error':'student_not_found'})
   except Exception as exc:print('[web-api] student timezone error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path.startswith('/api/student/self-service/'):
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(413 if getattr(self,'_body_too_large',False) else 400,{'error':'request_too_large' if getattr(self,'_body_too_large',False) else 'invalid_json'})
   try:
    uid=int(auth['id'])
    if path.endswith('/vacation'):result=student_vacation(uid,body.get('pause_until'))
    elif path.endswith('/resume-all'):result=student_resume_all(uid)
    elif path.endswith('/pause'):result=student_pause_schedule(uid,int(body.get('schedule_id')),body.get('pause_until'))
    elif path.endswith('/resume'):result=student_resume_schedule(uid,int(body.get('schedule_id')))
    elif path.endswith('/sickness'):result=student_sickness(uid,int(body.get('lesson_id')),body.get('comment'))
    elif path.endswith('/cancel'):result=student_cancel_lesson(uid,int(body.get('lesson_id')))
    elif path.endswith('/reschedule'):result=student_request_reschedule(uid,int(body.get('lesson_id')),body.get('reason'))
    else:return self._json(404,{'error':'not_found'})
    return self._json(200,result)
   except Exception as exc:return self._student_self_service_error(exc)
  if path=='/api/student/lesson/join':
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(413 if getattr(self,'_body_too_large',False) else 400,{'error':'request_too_large' if getattr(self,'_body_too_large',False) else 'invalid_json'})
   try:result=student_join(int(body.get('lesson_id')),int(auth['id']))
   except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
   except Exception as exc:print('[web-api] student lesson join error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
   status=result.get('status')
   if status=='ok':return self._json(200,result)
   if status=='not_found':return self._json(404,{'error':status})
   if status in {'entry_closed','invalid_status','payment_required'}:return self._json(409,{'error':status,**{k:v for k,v in result.items() if k!='status'}})
   return self._json(400,{'error':status or 'join_failed'})
  return super().do_POST()
def main():
 if not otp_secret.configured():raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
 ensure_indexes();print(f'Adelia web API v3.8 listening on http://{v1.HOST}:{v1.PORT}');ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()
