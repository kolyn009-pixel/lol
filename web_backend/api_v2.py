"""Adelia web API v2: real student, teacher and parent cabinets."""
from __future__ import annotations
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from web_backend import api as v1
from web_backend.student_portal import dashboard as student_dashboard, schedule as student_schedule, payments as student_payments, profile as student_profile, conversation_for_student
from web_backend.student_homework import submit_answers
from web_backend.manual_homework import submit as submit_manual_homework
from web_backend.unified_messages import add_message
from web_backend.lesson_join import student_workspace, student_join, teacher_open_entry, join_events
from web_backend.lesson_context import context as lesson_context, add_note as lesson_add_note, send_teacher_message
from web_backend.post_lesson_flow import state as post_state, save_marks, complete_review, skip_homework
from web_backend.post_lesson_complete import state as completion_state, complete as complete_post_lesson
from web_backend.homework_center import update_homework
from web_backend.assessment import save_task_feedback, student_feedback
from web_backend.homework_review_flow import finalize as finalize_homework_review
from web_backend.teacher_crm import schedule as teacher_crm_schedule, students as teacher_crm_students, student as teacher_crm_student, update_student as teacher_crm_update_student
from web_backend.stage6_api import Stage6Mixin
from web_backend.stage7_api import Stage7Mixin
from web_backend.stage8_api import Stage8Mixin
from web_backend.stage9_api import Stage9Mixin

class Handler(Stage9Mixin,Stage8Mixin,Stage7Mixin,Stage6Mixin,v1.Handler):
    server_version="AdeliaWeb/2.4"
    def do_GET(self):
        u=urlparse(self.path);path=u.path;q=parse_qs(u.query)
        handled=self.stage9_get(path,q)
        if handled is not False:return handled
        handled=self.stage8_get(path,q)
        if handled is not False:return handled
        handled=self.stage7_get(path,q)
        if handled is not False:return handled
        handled=self.stage6_get(path,q)
        if handled is not False:return handled
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
                if path=='/api/student/homework/feedback':return self._json(200,student_feedback(int(q.get('id',['0'])[0]),uid))
            except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
            except Exception as exc:print('[web-api] student GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path.startswith('/api/teacher/crm/'):
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                if path=='/api/teacher/crm/schedule':return self._json(200,teacher_crm_schedule(q.get('start',[None])[0],q.get('end',[None])[0],q.get('limit',[300])[0]))
                if path=='/api/teacher/crm/students':return self._json(200,teacher_crm_students(q.get('q',[None])[0],q.get('status',[None])[0],q.get('limit',[200])[0]))
                if path=='/api/teacher/crm/student':
                    item=teacher_crm_student(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
            except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
            except Exception as exc:print('[web-api] teacher CRM GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path.startswith('/api/teacher/lesson/'):
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            try:
                lid=int(q.get('id',['0'])[0])
                if path=='/api/teacher/lesson/join-events':return self._json(200,{'items':join_events(lid)})
                if path=='/api/teacher/lesson/context':
                    item=lesson_context(lid);return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
                if path=='/api/teacher/lesson/post-state':
                    item=post_state(lid);return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
                if path=='/api/teacher/lesson/completion-state':
                    item=completion_state(lid);return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
            except Exception as exc:print('[web-api] teacher lesson GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path
        handled=self.stage9_post(path)
        if handled is not False:return handled
        handled=self.stage8_post(path)
        if handled is not False:return handled
        handled=self.stage7_post(path)
        if handled is not False:return handled
        handled=self.stage6_post(path)
        if handled is not False:return handled
        if path=='/api/student/message':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            text=str(body.get('text') or '').strip()
            if not text:return self._json(400,{'error':'text_required'})
            if len(text)>4000:return self._json(400,{'error':'text_too_long'})
            try:return self._json(200,{'status':'ok','message_id':add_message(int(auth['id']),'IN','STUDENT','WEB',text=text)})
            except Exception as exc:print('[web-api] student message error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/homework/submit':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                attempt=body.get('attempt_number');r=submit_answers(int(body.get('homework_id')),int(auth['id']),body.get('responses') or {},attempt if attempt not in ('',None) else None);return self._json(200,r)
            except PermissionError:return self._json(404,{'error':'homework_not_found'})
            except ValueError as exc:return self._json(409,{'error':str(exc)})
            except Exception as exc:print('[web-api] student homework submit error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/student/homework/manual-submit':
            auth=self._student()
            if not auth:return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=submit_manual_homework(int(body.get('homework_id')),int(auth['id']),body.get('comment'))
                return self._json(200,r) if r.get('status')=='ok' else self._json(409,{'error':r.get('status')})
            except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
            except Exception as exc:print('[web-api] manual homework submit error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/crm/student/update':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=teacher_crm_update_student(int(body.get('user_id')),body.get('fields') or {});return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status'),'field':r.get('field')})
            except (TypeError,ValueError):return self._json(400,{'error':'invalid_request'})
            except Exception as exc:print('[web-api] teacher CRM update error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/homework-center/update':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=update_homework(int(body.get('homework_id')),title=body.get('title'),description=body.get('description'),deadline=body.get('deadline'),status=body.get('status'));return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:print('[web-api] homework update error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/homework-center/task-feedback':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=save_task_feedback(body.get('homework_id'),body.get('task_id'),body.get('user_id'),body.get('attempt_number'),body.get('comment'),body.get('is_correct'),body.get('points_awarded'));return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:print('[web-api] task feedback error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path=='/api/teacher/homework-center/finalize':
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                r=finalize_homework_review(body.get('homework_id'),body.get('user_id'),body.get('result'),body.get('comment'),body.get('attempt_number'));return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status')})
            except Exception as exc:print('[web-api] homework finalize error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        if path.startswith('/api/teacher/lesson/'):
            if not self._teacher():return self._json(401,{'error':'unauthorized'})
            body=self._body()
            if body is None:return self._json(400,{'error':'invalid_json'})
            try:
                lid=int(body.get('lesson_id'))
                if path=='/api/teacher/lesson/open-entry':r=teacher_open_entry(lid)
                elif path=='/api/teacher/lesson/note':r=lesson_add_note(lid,body.get('text'))
                elif path=='/api/teacher/lesson/message':r=send_teacher_message(lid,body.get('text'))
                elif path=='/api/teacher/lesson/review/save':r=save_marks(lid,body.get('marks') or [])
                elif path=='/api/teacher/lesson/review/complete':r=complete_review(lid,body.get('marks') or [])
                elif path=='/api/teacher/lesson/homework/skip':r=skip_homework(lid)
                elif path=='/api/teacher/lesson/complete':r=complete_post_lesson(lid)
                else:return super().do_POST()
                status=r.get('status');return self._json(200,r) if status=='ok' else self._json(409,{'error':status})
            except Exception as exc:print('[web-api] teacher lesson POST error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return super().do_POST()
def main():
    print(f"Adelia web API v2 listening on http://{v1.HOST}:{v1.PORT}");ThreadingHTTPServer((v1.HOST,v1.PORT),Handler).serve_forever()
if __name__=='__main__':main()