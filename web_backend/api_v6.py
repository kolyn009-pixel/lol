"""Adelia web API v6: auth verification, trial slots, onboarding and request center."""
from __future__ import annotations
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from web_backend import api as v1
from web_backend import api_v5,otp_secret,open_event_admin,event_campaign,student_social_profile,group_portal,public_trial_access,public_trial_slots,public_trial_channel,student_onboarding,teacher_request_center,onboarding_schedule_options,payment_hub,teacher_schedule_settings,server_health,student_regular_booking,trial_approval_atomic
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_auth import peek_student_login_code
class Handler(api_v5.Handler):
 server_version='AdeliaWeb/6.12'
 def do_GET(self):
  u=urlparse(self.path);path=u.path;q=parse_qs(u.query)
  if path=='/api/public/trial/slots':
   try:return self._json(200,public_trial_slots.feed(q.get('timezone',['Europe/Moscow'])[0],q.get('days',['14'])[0],q.get('duration_minutes',['60'])[0]))
   except ValueError as exc:return self._json(400,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] public trial slots error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/public/trial/channel/status':return self._json(405,{'error':'method_not_allowed'})
  if path=='/api/student/payment-hub':
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,payment_hub.student_hub(int(auth['id'])))
   except PermissionError as exc:return self._json(404,{'error':str(exc) or 'not_found'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] payment hub error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/onboarding/status':
   try:return self._json(200,student_onboarding.status_payload(q.get('token',[''])[0]))
   except ValueError as exc:return self._json(404 if str(exc)=='onboarding_not_found' else 409,{'error':str(exc)})
   except Exception as exc:print('[web-api] onboarding status error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/onboarding/schedule-options':
   try:return self._json(200,onboarding_schedule_options.feed(q.get('token',[''])[0]))
   except ValueError as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] onboarding schedule options error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/requests':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,teacher_request_center.list_all(q.get('limit',['100'])[0]))
   except Exception as exc:print('[web-api] teacher requests error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/working-hours':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,teacher_schedule_settings.snapshot())
   except Exception as exc:print('[web-api] teacher working hours error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/server-health':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,server_health.snapshot())
   except Exception as exc:print('[web-api] teacher server health error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  return super().do_GET()
 def do_POST(self):
  path=urlparse(self.path).path
  if path=='/api/student/booking/regular':
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:return self._json(200,student_regular_booking.create_group(int(auth['id']),int(body.get('program_id')),body.get('selections') or []))
   except PermissionError as exc:return self._json(404,{'error':str(exc) or 'not_found'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] recurring booking error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/trial/approve':
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   teacher=self._teacher()
   if not teacher:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:return self._json(200,trial_approval_atomic.approve(int(body.get('request_id')),int(teacher['admin_telegram_id']),body.get('trial_start'),body.get('trial_end'),body.get('meeting_url'),body.get('board_url')))
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] trial approval error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path in {'/api/public/trial/channel/start','/api/public/trial/channel/status'}:
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   if not v1._allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    if path.endswith('/start'):result=public_trial_channel.begin(body.get('request_id'),body.get('channel'),body.get('manage_token'))
    else:result=public_trial_channel.status(body.get('request_id'),body.get('manage_token'))
    return self._json(200,result)
   except PermissionError:return self._json(403,{'error':'invalid_manage_token'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] public trial channel error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/auth/student/code/verify':
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   if not v1._allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   result=peek_student_login_code(body.get('code'))
   if result.get('status')!='ok':return self._json(401,{'error':result.get('status','invalid')})
   student=result.get('student') or {};return self._json(200,{'ok':True,'student':{'id':student.get('id'),'name':student.get('name'),'grade':student.get('grade')}})
  if path.startswith('/api/onboarding/'):
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   if not v1._allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    if path=='/api/onboarding/start':return self._json(200,student_onboarding.start_returning(body.get('preferred_channel'),body.get('profile_url'),body.get('name'),body.get('grade'),body.get('subject'),body.get('study_goal'),body.get('phone'),body.get('legacy_note')))
    if path=='/api/onboarding/trial/start':return self._json(200,student_onboarding.start_trial_continuation(body.get('continuation_code')))
    if path=='/api/onboarding/region':return self._json(200,student_onboarding.save_region(body.get('token'),body.get('region'),body.get('timezone')))
    if path=='/api/onboarding/schedule':return self._json(200,student_onboarding.save_schedule(body.get('token'),body.get('selections') or []))
    if path=='/api/onboarding/complete':
     result=student_onboarding.complete(body.get('token'),body.get('login'),body.get('password'),body.get('continuation_code'));return self._json(200,{'status':'ok','user_id':result['user_id'],'login':result['login'],'redirect':result['redirect'],'schedule_request_ids':result.get('schedule_request_ids',[])},cookie=result['session_token'])
    return self._json(404,{'error':'not_found'})
   except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
   except ValueError as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] onboarding POST error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/working-hours':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:return self._json(200,teacher_schedule_settings.replace(body))
   except ValueError as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] teacher working hours save error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  actions={'/api/teacher/request/lesson/approve':('lesson','approve'),'/api/teacher/request/lesson/reject':('lesson','reject'),'/api/teacher/request/schedule/approve':('schedule','approve'),'/api/teacher/request/schedule/reject':('schedule','reject')}
  if path in actions:
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    kind,action=actions[path]
    if kind=='lesson':result=teacher_request_center.approve_lesson(body.get('lesson_id')) if action=='approve' else teacher_request_center.reject_lesson(body.get('lesson_id'),body.get('reason'))
    else:result=teacher_request_center.approve_schedule(body.get('schedule_id')) if action=='approve' else teacher_request_center.reject_schedule(body.get('schedule_id'),body.get('reason'))
    return self._json(200,result)
   except ValueError as exc:return self._json(409,{'error':str(exc)})
   except Exception as exc:print('[web-api] teacher request action error:',type(exc).__name__,repr(exc),flush=True);return self._json(500,{'error':'server_error'})
  return super().do_POST()
def main():
 if not otp_secret.configured():raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
 ensure_indexes();open_event_admin.choices();event_campaign.ensure_schema();student_social_profile.ensure_schema();group_portal.ensure_schema();student_onboarding.ensure_schema();public_trial_access.ensure_schema();public_trial_channel.ensure_schema();student_regular_booking.ensure_schema();print(f'Adelia web API v6.12 listening on http://{v1.HOST}:{v1.PORT}');ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()
