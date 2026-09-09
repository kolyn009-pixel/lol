"""HTTP API for adeliatutor.ru. Separate process, shared TutorBot database."""
import cgi
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from web_backend.parent_linking import find_student_by_username, link_parent_to_student_by_username
from web_backend.public_catalog import get_public_price_catalog
from web_backend.public_reviews import list_public_reviews
from web_backend.student_auth import consume_student_login_code
from web_backend.teacher_auth import consume_teacher_login_code
from web_backend.teacher_portal import dashboard as teacher_dashboard, students as teacher_students, student_card, review_submission
from web_backend.homework_authoring import create_assignment
from web_backend.homework_center import list_homework as teacher_homework_list, stats as teacher_homework_stats, detail as teacher_homework_detail
from web_backend.library import list_materials, grant_student, link_to_homework, list_collections, list_tasks, create_material, create_collection, add_material_to_collection, add_task
from web_backend.unified_messages import inbox as message_inbox, conversation, queue_teacher_reply
from web_backend.lesson_workspace import workspace as lesson_workspace, start_lesson, finish_lesson
from web_backend.post_lesson_flow import state as post_lesson_state, save_marks as post_lesson_save_marks, complete_review as post_lesson_complete_review, skip_homework as post_lesson_skip_homework, link_created_homework
from web_backend.external_homework import teacher_completion_feed
from web_backend.student_homework import list_homework as student_homework_list, detail as student_homework_detail, submit_answers, open_external, external_status
from web_backend.pdf_workflow import upload_collection as pdf_upload_collection, get_review as pdf_get_review, edit_review_item as pdf_edit_item, set_review_item as pdf_set_item, publish_review as pdf_publish_review
from web_backend.pdf_storage import MAX_PDF_BYTES
from web_backend.web_sessions import SESSION_TTL, create_session, read_session, revoke_session

HOST=os.getenv('ADELIA_WEB_HOST','127.0.0.1');PORT=int(os.getenv('ADELIA_WEB_PORT','8765'))
_attempts={}
def _session(role,entity_id):return create_session(role,entity_id,SESSION_TTL)
def _clean():
 now=time.time()
 for k in [k for k,v in _attempts.items() if now-v[0]>60]:_attempts.pop(k,None)
def _allowed(ip):
 _clean();now=time.time();start,count=_attempts.get(ip,(now,0))
 if now-start>60:start,count=now,0
 count+=1;_attempts[ip]=(start,count);return count<=12

class Handler(BaseHTTPRequestHandler):
 server_version='AdeliaWeb/1.0'
 def log_message(self,fmt,*args):print('[web-api]',self.address_string(),fmt%args)
 def _json(self,status,payload,cookie=None,clear_cookie=False):
  data=json.dumps(payload,ensure_ascii=False,default=str).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','same-origin')
  if cookie:self.send_header('Set-Cookie',f'adelia_session={cookie}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_TTL}')
  elif clear_cookie:self.send_header('Set-Cookie','adelia_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0')
  self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def _body(self):
  try:return json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),65536)) or b'{}')
  except:return None
 def _multipart(self):
  total=int(self.headers.get('Content-Length','0') or 0)
  if total<=0:return None
  if total>MAX_PDF_BYTES+1024*1024:raise ValueError('file_too_large')
  ctype=self.headers.get('Content-Type','')
  if not ctype.lower().startswith('multipart/form-data'):raise ValueError('multipart_required')
  env={'REQUEST_METHOD':'POST','CONTENT_TYPE':ctype,'CONTENT_LENGTH':str(total)}
  return cgi.FieldStorage(fp=self.rfile,headers=self.headers,environ=env,keep_blank_values=True)
 def _token(self):
  raw=self.headers.get('Cookie','');return next((p.split('=',1)[1] for p in raw.split('; ') if p.startswith('adelia_session=')),None)
 def _auth(self):return read_session(self._token())
 def _teacher(self):
  a=self._auth();return a if a and a['role']=='teacher' else None
 def _student(self):
  a=self._auth();return a if a and a['role']=='student' else None
 def do_GET(self):
  u=urlparse(self.path);path=u.path;q=parse_qs(u.query)
  try:
   if path=='/api/health':return self._json(200,{'ok':True,'service':'adelia-web'})
   if path=='/api/public/prices':return self._json(200,{'items':get_public_price_catalog()})
   if path=='/api/public/reviews':return self._json(200,{'items':list_public_reviews(12)})
   if path=='/api/auth/me':
    a=self._auth();return self._json(200,{'authenticated':bool(a),'session':a if a else None})
   if path.startswith('/api/student/'):
    a=self._student()
    if not a:return self._json(401,{'error':'unauthorized'})
    if path=='/api/student/homework':return self._json(200,{'items':student_homework_list(a['id'])})
    if path=='/api/student/homework/detail':
     item=student_homework_detail(int(q.get('id',['0'])[0]),a['id']);return self._json(200,item) if item else self._json(404,{'error':'homework_not_found'})
   if path.startswith('/api/teacher/'):
    if not self._teacher():return self._json(401,{'error':'unauthorized'})
    if path=='/api/teacher/dashboard':return self._json(200,teacher_dashboard())
    if path=='/api/teacher/students':return self._json(200,teacher_students())
    if path=='/api/teacher/student':
     item=student_card(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
    if path=='/api/teacher/homework-center':return self._json(200,{'stats':teacher_homework_stats(),'items':teacher_homework_list(status=q.get('status',[None])[0],user_id=q.get('user_id',[None])[0],mode=q.get('mode',[None])[0],search=q.get('q',[None])[0])})
    if path=='/api/teacher/homework-center/detail':
     item=teacher_homework_detail(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'homework_not_found'})
    if path=='/api/teacher/library':return self._json(200,{'items':list_materials(subject=q.get('subject',[None])[0],search=q.get('q',[None])[0])})
    if path=='/api/teacher/library/collections':return self._json(200,{'items':list_collections(subject=q.get('subject',[None])[0])})
    if path=='/api/teacher/library/tasks':return self._json(200,{'items':list_tasks(subject=q.get('subject',[None])[0],grade=q.get('grade',[None])[0],topic=q.get('topic',[None])[0],search=q.get('q',[None])[0],collection_id=q.get('collection_id',[None])[0])})
    if path=='/api/teacher/pdf-import':
     item=pdf_get_review(int(q.get('id',['0'])[0]));return self._json(200,item) if item and item.get('job') else self._json(404,{'error':'import_not_found'})
    if path=='/api/teacher/external-homework/feed':return self._json(200,{'items':teacher_completion_feed()})
    if path=='/api/teacher/messages':
     uid=int(q.get('user_id',['0'])[0]);return self._json(200,{'items':conversation(uid) if uid else message_inbox()})
    if path=='/api/teacher/lesson':
     item=lesson_workspace(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
    if path=='/api/teacher/post-lesson':
     item=post_lesson_state(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'lesson_not_found'})
   return self._json(404,{'error':'not_found'})
  except Exception:return self._json(500,{'error':'server_error'})
 def do_POST(self):
  path=urlparse(self.path).path
  try:
   if path=='/api/auth/logout':
    revoke_session(self._token());return self._json(200,{'ok':True},clear_cookie=True)
   if path=='/api/teacher/pdf-import/upload':
    if not self._teacher():return self._json(401,{'error':'unauthorized'})
    form=self._multipart();file_item=form['file'] if form is not None and 'file' in form else None
    if file_item is None or not getattr(file_item,'filename',None):return self._json(400,{'error':'file_required'})
    data=file_item.file.read(MAX_PDF_BYTES+1)
    def fv(name,default=None):
     try:
      v=form.getfirst(name,default);return v if v not in ('',None) else default
     except:return default
    r=pdf_upload_collection(data,file_item.filename,title=fv('title'),subject=fv('subject'),grade=int(fv('grade')) if fv('grade') else None,study_goal=fv('study_goal'),section=fv('section'),topic=fv('topic'),collection_id=int(fv('collection_id')) if fv('collection_id') else None)
    return self._json(200,r)
   body=self._body()
   if body is None:return self._json(400,{'error':'invalid_json'})
   if path in ('/api/auth/student/code','/api/auth/teacher/code'):
    if not _allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
    result=(consume_student_login_code if path.endswith('student/code') else consume_teacher_login_code)(body.get('code'))
    if result['status']!='ok':return self._json(401,{'error':result['status']})
    if path.endswith('student/code'):
     entity=result['student'];token=_session('student',entity['id']);return self._json(200,{'ok':True,'student':entity},token)
    token=_session('teacher',result['admin_telegram_id']);return self._json(200,{'ok':True,'role':'teacher'},token)
   if path.startswith('/api/student/'):
    a=self._student()
    if not a:return self._json(401,{'error':'unauthorized'})
    if path=='/api/student/homework/submit':return self._json(200,submit_answers(int(body.get('homework_id')),a['id'],body.get('responses') or {},int(body.get('attempt_number') or 1)))
    if path=='/api/student/homework/external/open':return self._json(200,open_external(int(body.get('homework_id')),a['id'],body.get('reminder_due_at')))
    if path=='/api/student/homework/external/status':return self._json(200,external_status(int(body.get('homework_id')),a['id'],body.get('status')))
   if path.startswith('/api/teacher/'):
    if not self._teacher():return self._json(401,{'error':'unauthorized'})
    if path=='/api/teacher/homework':
     r=create_assignment(body.get('user_id'),body.get('title'),body.get('description'),body.get('deadline'),body.get('lesson_id'),body.get('mode','MANUAL'),body.get('task_ids'),body.get('material_ids'),body.get('external_url'),body.get('external_title'),body.get('task_settings'))
     if r['status']!='ok':return self._json(400,{'error':r['status']})
     if body.get('lesson_id'):link_created_homework(int(body['lesson_id']),int(r['homework_id']))
     return self._json(200,r)
    if path=='/api/teacher/pdf-import/item':
     pdf_edit_item(int(body.get('item_id')),body.get('fields') or {});return self._json(200,{'status':'ok'})
    if path=='/api/teacher/pdf-import/item/status':return self._json(200,pdf_set_item(int(body.get('item_id')),bool(body.get('approved'))))
    if path=='/api/teacher/pdf-import/commit':
     r=pdf_publish_review(int(body.get('job_id')));return self._json(200,r) if r.get('status')=='ok' else self._json(400,{'error':r.get('status','import_failed')})
    if path=='/api/teacher/review':
     r=review_submission(body.get('submission_id'),body.get('result'),body.get('comment'),body.get('total_tasks'),body.get('correct_tasks'));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/message':
     text=str(body.get('text') or '').strip()
     if not text:return self._json(400,{'error':'text_required'})
     mid=queue_teacher_reply(int(body.get('user_id')),text);return self._json(200,{'status':'ok','message_id':mid,'delivery':'queued'})
    if path=='/api/teacher/lesson/start':
     r=start_lesson(int(body.get('lesson_id')));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/lesson/finish':
     r=finish_lesson(int(body.get('lesson_id')),body.get('attendance_status','PRESENT'),body.get('tutor_comment'),body.get('mode','NOW'));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/post-lesson/marks':
     r=post_lesson_save_marks(int(body.get('lesson_id')),body.get('marks') or []);return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/post-lesson/review':
     r=post_lesson_complete_review(int(body.get('lesson_id')),body.get('marks') or []);return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/post-lesson/homework/skip':
     r=post_lesson_skip_homework(int(body.get('lesson_id')));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/library/material':
     mid=create_material(body.get('title'),body.get('description'),body.get('subject'),body.get('grade_min'),body.get('grade_max'),body.get('material_type','LINK'),external_url=body.get('external_url'),tags=body.get('tags') or []);return self._json(200,{'status':'ok','material_id':mid})
    if path=='/api/teacher/library/collection':
     cid=create_collection(body.get('title'),body.get('description'),body.get('subject'),body.get('grade'),body.get('collection_type','BOOK'));return self._json(200,{'status':'ok','collection_id':cid})
    if path=='/api/teacher/library/collection/material':
     add_material_to_collection(int(body.get('collection_id')),int(body.get('material_id')),int(body.get('sort_order') or 100));return self._json(200,{'status':'ok'})
    if path=='/api/teacher/library/task':
     tid=add_task(body.get('subject'),body.get('statement'),body.get('grade'),body.get('study_goal'),body.get('section'),body.get('topic'),body.get('collection_id'),body.get('source_label'),body.get('task_number'),body.get('title'),body.get('answer'),body.get('solution'),body.get('difficulty',2),body.get('tags') or []);return self._json(200,{'status':'ok','task_id':tid})
    if path=='/api/teacher/material/grant':
     grant_student(int(body.get('material_id')),int(body.get('user_id')));return self._json(200,{'status':'ok'})
    if path=='/api/teacher/material/link-homework':
     link_to_homework(int(body.get('material_id')),int(body.get('homework_id')),body.get('note'));return self._json(200,{'status':'ok'})
   if path=='/api/parent/student/find':
    a=self._auth()
    if not a or a['role']!='parent':return self._json(401,{'error':'unauthorized'})
    s=find_student_by_username(body.get('username'));return self._json(200,{'found':bool(s),'student':s})
   if path=='/api/parent/student/link':
    a=self._auth()
    if not a or a['role']!='parent':return self._json(401,{'error':'unauthorized'})
    return self._json(200,link_parent_to_student_by_username(a['id'],body.get('username')))
   return self._json(404,{'error':'not_found'})
  except ValueError as e:return self._json(400,{'error':str(e)})
  except Exception:return self._json(500,{'error':'server_error'})
def main():
 print(f'Adelia web API listening on http://{HOST}:{PORT}');ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
if __name__=='__main__':main()