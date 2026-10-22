from urllib.parse import urlparse,parse_qs
import database
from web_backend import day_off_planner as planner


class DayOffMixin:
 def _dayoff_auth(self,path):
  if '/teacher/' in path:return self._teacher(),'teacher'
  if '/parent/' in path:return self._parent(),'parent'
  return self._student(),'student'

 def _dayoff_uid(self,role,auth,iid):
  if role=='teacher':return None
  if role=='student':return int(auth['id'])
  c=database.connect()
  try:
   r=c.execute("SELECT l.user_id FROM day_off_invitations d JOIN lessons l ON l.id=d.lesson_id JOIN parent_student_links p ON p.student_id=l.user_id WHERE d.id=? AND d.kind='LESSON' AND p.parent_id=?",(int(iid),int(auth['id']))).fetchone()
   if not r:raise PermissionError('Предложение переноса не найдено.')
   return int(r['user_id'])
  finally:c.close()

 def do_GET(self):
  u=urlparse(self.path);q=parse_qs(u.query)
  if u.path not in {'/api/'+r+'/day-off/'+a for r in ('teacher','student','parent') for a in ('invitations','slots')}:return super().do_GET()
  auth,role=self._dayoff_auth(u.path)
  if not auth:return self._json(401,{'error':'unauthorized'})
  try:
   if u.path.endswith('/slots'):
    iid=q.get('invitation_id',['0'])[0];result=planner.slots(iid,self._dayoff_uid(role,auth,iid),role=='teacher')
   elif role=='parent':
    c=database.connect()
    try:uids=[r['student_id'] for r in c.execute('SELECT student_id FROM parent_student_links WHERE parent_id=?',(int(auth['id']),))]
    finally:c.close()
    items={r['id']:r for uid in uids for r in planner.invitations(uid)['items']};result={'items':list(items.values()),'timezone':str(planner.lesson_timezone())}
   else:result=planner.invitations(int(auth['id']) if role=='student' else None,role=='teacher')
   return self._json(200,result)
  except PermissionError as e:return self._json(404,{'error':str(e)})
  except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})
  except Exception as e:
   print('[day-off] get:',type(e).__name__,flush=True);return self._json(500,{'error':'server_error'})

 def do_POST(self):
  path=urlparse(self.path).path
  if path not in {'/api/teacher/day-off/preview','/api/teacher/day-off/save','/api/teacher/day-off/deliver','/api/teacher/day-off/reschedule','/api/student/day-off/reschedule','/api/parent/day-off/reschedule'}:return super().do_POST()
  if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
  auth,role=self._dayoff_auth(path)
  if not auth:return self._json(401,{'error':'unauthorized'})
  body=self._body()
  if not isinstance(body,dict):return self._json(400,{'error':'invalid_json'})
  try:
   if path.endswith('/preview'):result=planner.preview(body)
   elif path.endswith('/save'):result=planner.save(body)
   elif path.endswith('/deliver'):
    planner.start_worker();result={'status':'ok','deliveries':planner.delivery_summary()}
   else:
    iid=body.get('invitation_id');result=planner.move(iid,body.get('start_time'),self._dayoff_uid(role,auth,iid),role=='teacher')
   return self._json(200,result)
  except PermissionError as e:return self._json(404,{'error':str(e)})
  except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})
  except Exception as e:
   print('[day-off] post:',type(e).__name__,flush=True);return self._json(500,{'error':'server_error'})
