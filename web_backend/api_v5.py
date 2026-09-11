"""Adelia web API v5: events, attendance, campaigns, live entry, social profile and group space."""
from __future__ import annotations
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from web_backend import api as v1,api_v4,otp_secret,open_event_admin,event_campaign,student_live_entry,student_social_profile,student_portal,group_portal,public_opportunities
from web_backend.stage12_indexes import ensure_indexes

def _student_profile(uid):
    """Backward-compatible profile payload: tutoring data + app social fields."""
    legacy=student_portal.profile(int(uid)) or {}
    social=student_social_profile.public_profile(int(uid),viewer_id=int(uid))
    return {**legacy,**social}

class Handler(api_v4.Handler):
    server_version='AdeliaWeb/5.7'
    def do_GET(self):
        u=urlparse(self.path);path,q=u.path,parse_qs(u.query)
        if path=='/api/public/opportunities':
            try:return self._json(200,public_opportunities.feed())
            except Exception as exc:print('[web-api] public opportunities error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        if path in {'/api/teacher/events','/api/teacher/events/choices','/api/teacher/event','/api/teacher/group/attendance','/api/teacher/group-lessons','/api/teacher/group-lesson'}:
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                if path.endswith('/events'):r={'items':open_event_admin.list_events(int(q.get('limit',['100'])[0]))}
                elif path.endswith('/events/choices'):r=open_event_admin.choices()
                elif path.endswith('/event'):
                    r=open_event_admin.detail(int(q.get('id',['0'])[0]));r=r if r else {'error':'event_not_found'}
                    if not r.get('error'):r['audience_rules']=event_campaign.audience_rules(int(q.get('id',['0'])[0]))
                elif path.endswith('/group-lessons'):r={'items':open_event_admin.list_group_lessons(int(q.get('limit',['120'])[0]))}
                elif path.endswith('/group-lesson'):r=open_event_admin.group_lesson_detail(int(q.get('id',['0'])[0])) or {'error':'group_lesson_not_found'}
                else:r={'items':open_event_admin.group_roster(int(q.get('lesson_id',['0'])[0]))}
                return self._json(404 if r.get('error') else 200,r)
            except (TypeError,ValueError,PermissionError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] event GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
        student_get={'/api/student/events','/api/student/profile','/api/student/group/members','/api/student/groups','/api/student/group/summary','/api/student/group/chat'}
        if path in student_get:
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            try:
                uid=int(auth['id'])
                if path.endswith('/events'):r={'items':event_campaign.feed(uid)}
                elif path.endswith('/profile'):r=_student_profile(uid)
                elif path.endswith('/group/members'):r={'items':student_social_profile.group_members(int(q.get('group_id',['0'])[0]),uid)}
                elif path.endswith('/groups'):r={'items':group_portal.student_groups(uid)}
                elif path.endswith('/group/summary'):r=group_portal.student_group_summary(uid,int(q.get('group_id',['0'])[0]))
                else:r={'items':group_portal.group_chat(int(q.get('group_id',['0'])[0]),uid,int(q.get('limit',['100'])[0]))}
                return self._json(200,r)
            except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
            except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
            except Exception as exc:print('[web-api] student group GET error:',type(exc).__name__,flush=True);return self._json(500,{'error':'server_error'})
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
        student_routes={'/api/student/event/register','/api/student/event/invite/respond','/api/student/group-lesson/enter','/api/student/group-lesson/leave','/api/student/event/enter','/api/student/event/leave','/api/student/profile','/api/student/presence','/api/student/group/chat'}
        if path in student_routes:
            if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                uid=int(auth['id'])
                if path.endswith('/register'):r=event_campaign.register(int(body.get('event_id')),uid)
                elif path.endswith('/invite/respond'):
                    if not isinstance(body.get('accepted'),bool):raise ValueError('invalid_accepted')
                    r=event_campaign.respond_invite(int(body.get('event_id')),uid,body['accepted'])
                elif path.endswith('/group-lesson/enter'):r=student_live_entry.group_entry(int(body.get('lesson_id')),uid,'APP')
                elif path.endswith('/group-lesson/leave'):r=student_live_entry.leave_group(int(body.get('lesson_id')),uid,'APP')
                elif path.endswith('/event/enter'):r=student_live_entry.event_entry(int(body.get('event_id')),uid,'APP')
                elif path.endswith('/event/leave'):r=student_live_entry.leave_event(int(body.get('event_id')),uid,'APP')
                elif path.endswith('/presence'):r=student_social_profile.touch_presence(uid,int(body.get('active_seconds') or 120))
                elif path.endswith('/group/chat'):r=group_portal.post_group_message(int(body.get('group_id')),uid,'STUDENT',body.get('body'))
                else:
                    student_social_profile.update(uid,display_name=body.get('display_name'),avatar_kind=body.get('avatar_kind'),avatar_value=body.get('avatar_value'),manual_status=body.get('manual_status'),study_status_text=body.get('study_status_text'),show_online=body.get('show_online'),allow_group_messages=body.get('allow_group_messages'));r=_student_profile(uid)
                return self._json(200,r)
            except PermissionError as exc:return self._json(403,{'error':str(exc) or 'forbidden'})
            except (TypeError,ValueError) as exc:return self._json(409,{'error':str(exc) or 'invalid_request'})
        return super().do_POST()

def main():
    if not otp_secret.configured():raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
    ensure_indexes();open_event_admin.choices();event_campaign.ensure_schema();student_social_profile.ensure_schema();group_portal.ensure_schema();print(f'Adelia web API v5.7 listening on http://{v1.HOST}:{v1.PORT}');ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()
