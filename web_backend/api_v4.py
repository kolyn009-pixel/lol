"""Adelia web API v4: student self-service, finance, feedback and teacher schedule review."""
from __future__ import annotations
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from web_backend import api as v1, api_v3, otp_secret
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_booking import programs as booking_programs, free_slots as booking_free_slots, request_one_off, request_trial, trial_status, cancel_pending
from web_backend.student_reschedule import free_slots_for_lesson, create_request as create_slot_change, outgoing as outgoing_slot_changes, incoming as incoming_exchanges, respond_to_exchange, cancel_request as cancel_slot_change
from web_backend.student_finance import overview as finance_overview, quote as finance_quote, create_package_payment, create_lesson_payment, history as finance_history, attach_receipt
from web_backend.finance_receipts import web_receipt_file
from web_backend.post_lesson import get_feedback, submit_feedback, pending_for_student
from web_backend.teacher_cascade import list_requests as cascade_requests, analyze_request as analyze_cascade, approve_plan as approve_cascade
from web_backend import public_trial, public_trial_access, trial_conversion, teacher_board
from final_features import regular_schedule_change, cascade_consents, cascade_shift

class Handler(api_v3.Handler):
 server_version='AdeliaWeb/4.11'
 def _send_receipt_file(self,receipt_id):
  if not self._teacher():return self._json(401,{'error':'unauthorized'})
  try:path,mime=web_receipt_file(int(receipt_id));data=path.read_bytes()
  except (TypeError,ValueError) as exc:return self._json(404,{'error':str(exc) or 'receipt_not_found'})
  except Exception as exc:print('[web-api] receipt file error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  self.send_response(200);self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(data)));self.send_header('Content-Disposition',f'inline; filename="receipt-{int(receipt_id)}{path.suffix.lower()}"');self.send_header('Cache-Control','private, no-store, max-age=0');self.send_header('Pragma','no-cache');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  u=urlparse(self.path);path,q=u.path,parse_qs(u.query)
  if path=='/api/teacher/finance/receipt/file':return self._send_receipt_file(q.get('receipt_id',['0'])[0])
  if path=='/api/teacher/cascade/requests':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,{'items':cascade_requests(int(q.get('limit',['50'])[0]))})
   except Exception as exc:print('[web-api] cascade GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/cascade/consents':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,cascade_consents.summary(int(q.get('plan_id',['0'])[0])))
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
  if path=='/api/teacher/regular-change/request':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:
    item=regular_schedule_change.get_request(int(q.get('request_id',['0'])[0]));return self._json(200,{'item':item}) if item else self._json(404,{'error':'request_not_found'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
  if path=='/api/teacher/trials':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,{'items':public_trial.list_for_teacher(q.get('status',[None])[0],int(q.get('limit',['100'])[0]))})
   except Exception as exc:print('[web-api] trial GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  if path=='/api/teacher/trial/share':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,public_trial.teacher_share_payload(int(q.get('request_id',['0'])[0])))
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
  if path=='/api/teacher/student/board':
   if not self._teacher():return self._json(401,{'error':'unauthorized'})
   try:return self._json(200,teacher_board.get_board(int(q.get('user_id',['0'])[0])))
   except (TypeError,ValueError) as exc:return self._json(404,{'error':str(exc) or 'student_not_found'})
  booking={'/api/student/booking/programs','/api/student/booking/free-slots','/api/student/booking/trial-status'};changes={'/api/student/reschedule/free-slots','/api/student/reschedule/outgoing','/api/student/exchanges/incoming'};finance={'/api/student/finance/overview','/api/student/finance/history','/api/student/finance/quote'};regular={'/api/student/regular-schedules','/api/student/regular-change/requests'}
  if path in booking|changes|finance|regular|{'/api/student/post-lesson','/api/student/post-lesson/pending','/api/student/cascade/incoming'}:
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   try:
    uid=int(auth['id'])
    if path.endswith('/booking/programs'):result={'items':booking_programs(uid)}
    elif path.endswith('/booking/free-slots'):result={'items':booking_free_slots(uid,int(q.get('program_id',['0'])[0]),int(q.get('days',['14'])[0]),int(q.get('duration_minutes',['60'])[0]))}
    elif path.endswith('/booking/trial-status'):result=trial_status(uid)
    elif path.endswith('/reschedule/free-slots'):result={'items':free_slots_for_lesson(uid,int(q.get('lesson_id',['0'])[0]),int(q.get('days',['14'])[0]))}
    elif path.endswith('/reschedule/outgoing'):result={'items':outgoing_slot_changes(uid)}
    elif path.endswith('/exchanges/incoming'):result={'items':incoming_exchanges(uid)}
    elif path.endswith('/cascade/incoming'):result={'items':cascade_consents.incoming(uid)}
    elif path.endswith('/post-lesson/pending'):result={'items':pending_for_student(uid)}
    elif path.endswith('/finance/overview'):result=finance_overview(uid)
    elif path.endswith('/finance/history'):result={'items':finance_history(uid,int(q.get('limit',['30'])[0]))}
    elif path.endswith('/finance/quote'):result=finance_quote(uid,int(q.get('selection_key',['0'])[0]),int(q.get('lessons_count',['1'])[0]),q.get('promo_code',[None])[0])
    elif path.endswith('/regular-schedules'):result={'items':regular_schedule_change.schedules_for_student(uid)}
    elif path.endswith('/regular-change/requests'):result={'items':regular_schedule_change.requests_for_student(uid)}
    else:result=get_feedback(uid,int(q.get('lesson_id',['0'])[0]))
    return self._json(200,result)
   except PermissionError as exc:return self._json(404,{'error':str(exc) or 'not_found'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] student GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  return super().do_GET()
 def do_POST(self):
  path=urlparse(self.path).path
  if path=='/api/public/trial':
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    result=public_trial.create(body.get('name'),body.get('telegram'),body.get('phone'),body.get('subject'),body.get('study_goal'),body.get('preferred_time'),body.get('note'),body.get('grade'),source='WEB',timezone=body.get('timezone'),region=body.get('region'),selected_slot_start=body.get('selected_slot_start'),selected_slot_end=body.get('selected_slot_end'))
    result['manage_token']=public_trial_access.issue(result['request_id'])
    return self._json(200,result)
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
  if path in {'/api/teacher/cascade/analyze','/api/teacher/cascade/approve','/api/teacher/cascade/request-consents','/api/teacher/cascade/apply','/api/teacher/regular-change/approve','/api/teacher/regular-change/apply','/api/teacher/regular-change/reject','/api/teacher/trial/approve','/api/teacher/trial/finish','/api/teacher/trial/status','/api/teacher/student/board'}:
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   teacher=self._teacher()
   if not teacher:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    tid=int(teacher['admin_telegram_id'])
    if path.endswith('/cascade/analyze'):result=analyze_cascade(int(body.get('request_id')))
    elif path.endswith('/cascade/approve'):result=approve_cascade(int(body.get('plan_id')),tid)
    elif path.endswith('/cascade/request-consents'):result=cascade_consents.create_for_approved_plan(int(body.get('plan_id')))
    elif path.endswith('/cascade/apply'):
     plan_id=int(body.get('plan_id'))
     if not cascade_consents.ready_for_final_apply(plan_id):raise ValueError('student_consents_pending')
     result=cascade_shift.apply_approved(plan_id,tid)
    elif path.endswith('/regular-change/approve'):result=regular_schedule_change.approve(int(body.get('request_id')),tid)
    elif path.endswith('/regular-change/apply'):result=regular_schedule_change.apply_approved(int(body.get('request_id')),tid)
    elif path.endswith('/regular-change/reject'):result=regular_schedule_change.reject(int(body.get('request_id')),tid)
    elif path.endswith('/trial/approve'):result=public_trial.approve(int(body.get('request_id')),tid,body.get('trial_start'),body.get('trial_end'),body.get('meeting_url'),body.get('board_url'))
    elif path.endswith('/trial/finish'):result=public_trial.finish_trial(int(body.get('request_id')),body.get('finished_at'))
    elif path.endswith('/trial/status'):result=public_trial.set_status(int(body.get('request_id')),body.get('status'),tid)
    else:result=teacher_board.set_board(int(body.get('user_id')),body.get('board_url'))
    return self._json(200,result)
   except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] teacher schedule POST error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  routes={'/api/student/booking/request','/api/student/booking/trial','/api/student/booking/cancel','/api/student/reschedule/request','/api/student/reschedule/cancel','/api/student/exchanges/respond','/api/student/cascade/respond','/api/student/finance/package','/api/student/finance/lesson','/api/student/finance/receipt','/api/student/post-lesson','/api/student/regular-change/request','/api/student/trial/claim'}
  if path in routes:
   if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
   auth=self._student()
   if not auth:return self._json(401,{'error':'unauthorized'})
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   try:
    uid=int(auth['id'])
    if path.endswith('/booking/request'):result=request_one_off(uid,int(body.get('program_id')),body.get('start_time'),int(body.get('duration_minutes') or 60))
    elif path.endswith('/booking/trial'):result=request_trial(uid,int(body.get('program_id')),body.get('start_time'),int(body.get('duration_minutes') or 60))
    elif path.endswith('/booking/cancel'):result=cancel_pending(uid,int(body.get('lesson_id')))
    elif path.endswith('/reschedule/request'):result=create_slot_change(uid,int(body.get('lesson_id')),body.get('desired_start'),body.get('note'))
    elif path.endswith('/reschedule/cancel'):result=cancel_slot_change(uid,int(body.get('request_id')))
    elif path.endswith('/exchanges/respond'):
     if not isinstance(body.get('accepted'),bool):raise ValueError('invalid_accepted')
     result=respond_to_exchange(uid,int(body.get('request_id')),body['accepted'])
    elif path.endswith('/cascade/respond'):
     if not isinstance(body.get('accepted'),bool):raise ValueError('invalid_accepted')
     result=cascade_consents.respond(uid,int(body.get('consent_id')),body['accepted'])
    elif path.endswith('/finance/package'):result=create_package_payment(uid,int(body.get('selection_key')),int(body.get('lessons_count')),body.get('promo_code'))
    elif path.endswith('/finance/lesson'):result=create_lesson_payment(uid,int(body.get('lesson_id')),body.get('promo_code'))
    elif path.endswith('/finance/receipt'):result=attach_receipt(uid,int(body.get('payment_id')),body.get('filename'),body.get('mime_type'),body.get('content_b64'))
    elif path.endswith('/regular-change/request'):result=regular_schedule_change.create_request(uid,int(body.get('regular_schedule_id')),int(body.get('weekday')),body.get('start_time'),int(body.get('duration_minutes')),source='WEB',note=body.get('note'))
    elif path.endswith('/trial/claim'):result=trial_conversion.claim_continuation_code(uid,body.get('code'))
    else:result=submit_feedback(uid,int(body.get('lesson_id')),int(body.get('rating')),body.get('next_topic'),body.get('comment'),'WEB')
    return self._json(200,result)
   except PermissionError as exc:return self._json(404,{'error':str(exc) or 'not_found'})
   except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
   except Exception as exc:print('[web-api] student POST error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
  return super().do_POST()
def main():
 if not otp_secret.configured():raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
 ensure_indexes();public_trial.ensure_schema();public_trial_access.ensure_schema();trial_conversion.ensure_schema();print(f'Adelia web API v4.11 listening on http://{v1.HOST}:{v1.PORT}');ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()
