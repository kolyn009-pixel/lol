"""Adelia web API v2: real student cabinet and coordinated lesson entry."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from web_backend import api as v1
from web_backend.student_portal import dashboard as student_dashboard, schedule as student_schedule, payments as student_payments, profile as student_profile, conversation_for_student
from web_backend.unified_messages import add_message
from web_backend.lesson_join import student_workspace, student_join, teacher_open_entry, join_events
from web_backend.lesson_context import context as lesson_context, add_note as lesson_add_note, send_teacher_message


class Handler(v1.Handler):
    server_version = "AdeliaWeb/1.2"

    def do_GET(self):
        u=urlparse(self.path); path=u.path; q=parse_qs(u.query)
        if path.startswith('/api/student/'):
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            uid=int(auth['id'])
            try:
                if path=='/api/student/dashboard':
                    item=student_dashboard(uid);return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
                if path=='/api/student/schedule':return self._json(200,{'items':student_schedule(uid,q.get('limit',[40])[0])})
                if path=='/api/student/payments':
                    item=student_payments(uid,q.get('limit',[50])[0]);return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
                if path=='/api/student/profile':
                    item=student_profile(uid);return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
                if path=='/api/student/messages':return self._json(200,{'items':conversation_for_student(uid,q.get('limit',[100])[0])})
                if path=='/api/student/lesson':
                    item=student_workspace(int(q.get('id',['0'])[0]),uid);return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
            except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
            except Exception as exc:
                print('[web-api] student GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/lesson/join-events':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:return self._json(200,{'items':join_events(int(q.get('id',['0'])[0]))})
            except Exception:return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/lesson/context':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                item=lesson_context(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
            except Exception as exc:
                print('[web-api] lesson context error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return super().do_GET()

    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/student/message':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            text=str(body.get('text') or '').strip()
            if not text:return self._json(400,{'error':'text_required'})
            if len(text)>4000:return self._json(400,{'error':'text_too_long'})
            try:
                mid=add_message(int(auth['id']),'IN','STUDENT','WEB',text=text);return self._json(200,{'status':'ok','message_id':mid})
            except Exception as exc:
                print('[web-api] student message error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/lesson/join':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=student_join(int(body.get('lesson_id')),int(auth['id']))
                return self._json(200,r) if r.get('status')=='ok' else self._json(409 if r.get('status')=='entry_closed' else 400,{'error':r.get('status')})
            except Exception as exc:
                print('[web-api] student join error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/lesson/open-entry':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=teacher_open_entry(int(body.get('lesson_id')));return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:
                print('[web-api] teacher open entry error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/lesson/note':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=lesson_add_note(int(body.get('lesson_id')),body.get('text'))
                return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:
                print('[web-api] lesson note error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/lesson/message':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=send_teacher_message(int(body.get('lesson_id')),body.get('text'))
                return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:
                print('[web-api] lesson message error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return super().do_POST()


def main():
    print(f"Adelia web API v2 listening on http://{v1.HOST}:{v1.PORT}")
    ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()

if __name__=='__main__':main()
