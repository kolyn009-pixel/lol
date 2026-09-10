"""Adelia web API v5: paid events, attendance, campaigns and self-registration."""
from __future__ import annotations
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from web_backend import api as v1,api_v4,otp_secret,open_event_admin,event_campaign
from web_backend.stage12_indexes import ensure_indexes

class Handler(api_v4.Handler):
    server_version='AdeliaWeb/5.1'
    def do_GET(self):
        u=urlparse(self.path);path,q=u.path,parse_qs(u.query)
        if path in {'/api/teacher/events','/api/teacher/events/choices','/api/teacher/event','/api/teacher/group/attendance'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                if path.endswith('/events'):r={'items':open_event_admin.list_events(int(q.get('limit',['100'])[0]))}
                elif path.endswith('/events/choices'):r=open_event_admin.choices()
                elif path.endswith('/event'):
                    r=open_event_admin.detail(int(q.get('id',['0'])[0]));r=r if r else {'error':'event_not_found'}
                    if not r.get('error'):r['audience_rules']=event_campaign.audience_rules(int(q.get('id',['0'])[0]))
                else:r={'items':open_event_admin.group_roster(int(q.get('lesson_id',['0'])[0]))}
                return self._json(404 if r.get('error') else 200,r)
            except (TypeError,ValueError,PermissionError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] event GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/events':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            try:return self._json(200,{'items':event_campaign.feed(int(auth['id']))})
            except Exception as exc:print('[web-api] student event GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        teacher_routes={'/api/teacher/event/create','/api/teacher/event/payment','/api/teacher/event/attendance','/api/teacher/event/result','/api/teacher/event/start','/api/teacher/event/finish','/api/teacher/group/attendance','/api/teacher/event/publish','/api/teacher/event/invite','/api/teacher/event/audience'}
        if path in teacher_routes:
            if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
            teacher=self._teacher()
            if not teacher:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                tid=int(teacher['admin_telegram_id'])
                if path.endswith('/event/create'):
                    r=open_event_admin.create(body,tid);event_campaign.set_audience(r['event_id'],body.get('audience_rules') or [])
                    if body.get('publish_now',True):r['publication']=event_campaign.publish_event(r['event_id'],tid)
                elif path.endswith('/event/payment'):r=open_event_admin.set_payment(int(body.get('event_id')),int(body.get('user_id')),body.get('status'))
                elif path.endswith('/event/attendance'):r=open_event_admin.attendance(int(body.get('event_id')),int(body.get('user_id')),body.get('event_type'),tid,body.get('happened_at'))
                elif path.endswith('/event/result'):r=open_event_admin.save_result(int(body.get('event_id')),int(body.get('user_id')),body.get('score'),body.get('max_score'),body.get('note'))
                elif path.endswith('/event/start'):r=open_event_admin.start(int(body.get('event_id')))
                elif path.endswith('/event/finish'):r=open_event_admin.finish(int(body.get('event_id')))
                elif path.endswith('/event/publish'):r=event_campaign.publish_event(int(body.get('event_id')),tid)
                elif path.endswith('/event/invite'):r=event_campaign.invite_student(int(body.get('event_id')),int(body.get('user_id')),tid,body.get('reason'),int(body.get('hold_hours') or 24))
                elif path.endswith('/event/audience'):r={'rules':event_campaign.set_audience(int(body.get('event_id')),body.get('rules') or [])}
                else:r=open_event_admin.group_attendance(int(body.get('lesson_id')),int(body.get('user_id')),body.get('event_type'),tid,body.get('happened_at'))
                return self._json(200,r)
            except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
            except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] event POST error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/student/event/register','/api/student/event/invite/respond'}:
            if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                uid=int(auth['id']);eid=int(body.get('event_id'))
                if path.endswith('/register'):r=event_campaign.register(eid,uid)
                else:
                    if not isinstance(body.get('accepted'),bool):raise ValueError('invalid_accepted')
                    r=event_campaign.respond_invite(eid,uid,body['accepted'])
                return self._json(200,r)
            except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
            except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
        return super().do_POST()

def main():
    if not otp_secret.configured():raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
    ensure_indexes();open_event_admin.choices();event_campaign.ensure_schema();print(f'Adelia web API v5.1 listening on http://{v1.HOST}:{v1.PORT}');ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()
