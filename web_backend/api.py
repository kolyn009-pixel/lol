"""HTTP API for adeliatutor.ru. Separate process, shared TutorBot database."""
import json, os, secrets, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from web_backend.parent_linking import find_student_by_username, link_parent_to_student_by_username
from web_backend.public_catalog import get_public_price_catalog
from web_backend.public_reviews import list_public_reviews
from web_backend.student_auth import consume_student_login_code
from web_backend.teacher_auth import consume_teacher_login_code
from web_backend.teacher_portal import dashboard as teacher_dashboard, students as teacher_students, student_card, create_simple_homework, review_submission
HOST=os.getenv('ADELIA_WEB_HOST','127.0.0.1');PORT=int(os.getenv('ADELIA_WEB_PORT','8765'));SESSION_TTL=60*60*24*30
_sessions={};_attempts={}
def _session(role,entity_id):
 token=secrets.token_urlsafe(32);_sessions[token]={'role':role,'id':int(entity_id),'expires':time.time()+SESSION_TTL};return token
def _clean():
 now=time.time()
 for k in [k for k,v in _sessions.items() if v['expires']<now]:_sessions.pop(k,None)
 for k in [k for k,v in _attempts.items() if now-v[0]>60]:_attempts.pop(k,None)
def _allowed(ip):
 _clean();now=time.time();start,count=_attempts.get(ip,(now,0))
 if now-start>60:start,count=now,0
 count+=1;_attempts[ip]=(start,count);return count<=12
class Handler(BaseHTTPRequestHandler):
 server_version='AdeliaWeb/0.2'
 def log_message(self,fmt,*args):print('[web-api]',self.address_string(),fmt%args)
 def _json(self,status,payload,cookie=None):
  data=json.dumps(payload,ensure_ascii=False,default=str).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  if cookie:self.send_header('Set-Cookie',f'adelia_session={cookie}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_TTL}')
  self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def _body(self):
  try:return json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),65536)) or b'{}')
  except:return None
 def _auth(self):
  raw=self.headers.get('Cookie','');token=next((p.split('=',1)[1] for p in raw.split('; ') if p.startswith('adelia_session=')),None);item=_sessions.get(token)
  return item if item and item['expires']>=time.time() else None
 def _teacher(self):
  a=self._auth();return a if a and a['role']=='teacher' else None
 def do_GET(self):
  u=urlparse(self.path);path=u.path
  try:
   if path=='/api/health':return self._json(200,{'ok':True,'service':'adelia-web'})
   if path=='/api/public/prices':return self._json(200,{'items':get_public_price_catalog()})
   if path=='/api/public/reviews':return self._json(200,{'items':list_public_reviews(12)})
   if path=='/api/auth/me':
    a=self._auth();return self._json(200,{'authenticated':bool(a),'session':a if a else None})
   if path.startswith('/api/teacher/'):
    if not self._teacher():return self._json(401,{'error':'unauthorized'})
    if path=='/api/teacher/dashboard':return self._json(200,teacher_dashboard())
    if path=='/api/teacher/students':return self._json(200,teacher_students())
    if path=='/api/teacher/student':
     q=parse_qs(u.query);item=student_card(int(q.get('id',['0'])[0]));return self._json(200,item) if item else self._json(404,{'error':'student_not_found'})
   return self._json(404,{'error':'not_found'})
  except Exception as e:return self._json(500,{'error':'server_error','detail':str(e)[:180]})
 def do_POST(self):
  path=urlparse(self.path).path;body=self._body()
  if body is None:return self._json(400,{'error':'invalid_json'})
  try:
   if path in ('/api/auth/student/code','/api/auth/teacher/code'):
    if not _allowed(self.client_address[0]):return self._json(429,{'error':'too_many_attempts'})
    result=(consume_student_login_code if path.endswith('student/code') else consume_teacher_login_code)(body.get('code'))
    if result['status']!='ok':return self._json(401,{'error':result['status']})
    if path.endswith('student/code'):
     entity=result['student'];token=_session('student',entity['id']);return self._json(200,{'ok':True,'student':entity},token)
    token=_session('teacher',result['admin_telegram_id']);return self._json(200,{'ok':True,'role':'teacher'},token)
   if path.startswith('/api/teacher/'):
    if not self._teacher():return self._json(401,{'error':'unauthorized'})
    if path=='/api/teacher/homework':
     r=create_simple_homework(body.get('user_id'),body.get('title'),body.get('description'),body.get('deadline'),body.get('lesson_id'));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
    if path=='/api/teacher/review':
     r=review_submission(body.get('submission_id'),body.get('result'),body.get('comment'),body.get('total_tasks'),body.get('correct_tasks'));return self._json(200,r) if r['status']=='ok' else self._json(400,{'error':r['status']})
   if path=='/api/parent/student/find':
    a=self._auth()
    if not a or a['role']!='parent':return self._json(401,{'error':'unauthorized'})
    s=find_student_by_username(body.get('username'));return self._json(200,{'found':bool(s),'student':s})
   if path=='/api/parent/student/link':
    a=self._auth()
    if not a or a['role']!='parent':return self._json(401,{'error':'unauthorized'})
    return self._json(200,link_parent_to_student_by_username(a['id'],body.get('username')))
   return self._json(404,{'error':'not_found'})
  except Exception as e:return self._json(500,{'error':'server_error','detail':str(e)[:180]})
def main():
 print(f'Adelia web API listening on http://{HOST}:{PORT}');ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
if __name__=='__main__':main()
