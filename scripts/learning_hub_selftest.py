"""Learning records, scope and waiting-list behavior against a disposable SQLite DB."""
from pathlib import Path
import sys,sqlite3,tempfile,unittest
from types import ModuleType
from datetime import datetime,timedelta,timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
folder=tempfile.TemporaryDirectory();db_path=Path(folder.name)/'test.db'
def connect():
    c=sqlite3.connect(db_path);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
db=ModuleType('database');db.connect=connect;db.get_setting=lambda *args:'Europe/Samara';db.now_iso=lambda:datetime.now(timezone.utc).isoformat();sys.modules['database']=db
guard=ModuleType('web_backend.availability_guard');guard.blocked=False
def available(start,end,conn=None):
    if guard.blocked:raise ValueError('slot_unavailable')
guard.assert_available=available;sys.modules['web_backend.availability_guard']=guard
from web_backend import learning_hub as hub
from web_backend.learning_hub_api import LearningHubMixin
from web_backend import library
parent=ModuleType('web_backend.parent_portal')
def linked(pid,uid):
    if pid!=7 or uid!=1:raise PermissionError('student_not_linked')
    return uid
parent._assert_link=linked;sys.modules['web_backend.parent_portal']=parent

class Handler(LearningHubMixin):
    def __init__(self,role='student',body=None):self.role=role;self.body=body;self.origin=True
    def _student(self):return {'id':1} if self.role=='student' else None
    def _teacher(self):return {'id':9} if self.role=='teacher' else None
    def _auth(self):return {'role':self.role,'id':7} if self.role else None
    def _same_origin_write(self):return self.origin
    def _body(self):return self.body
    def _json(self,status,payload):return status,payload

class Tests(unittest.TestCase):
    def setUp(self):
        guard.blocked=False
        c=connect();tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")];c.close()
        c=sqlite3.connect(db_path)
        for t in tables:c.execute('DROP TABLE '+t)
        c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT); INSERT INTO users VALUES(1,'Кирилл'),(2,'Другой ученик');CREATE TABLE lessons(id INTEGER PRIMARY KEY,user_id INTEGER,start_time TEXT,lesson_status TEXT);INSERT INTO lessons VALUES(10,1,'2026-10-11T10:00:00','COMPLETED'),(20,2,'2026-10-11T12:00:00','COMPLETED');CREATE TABLE homework(id INTEGER PRIMARY KEY);");c.commit();c.close()
    def test_summary_is_private_until_published_and_lesson_scoped(self):
        payload={'lesson_id':10,'topics':'Динамика','achievement':'Второй закон Ньютона'}
        hub.save_summary(1,payload);self.assertEqual(hub.overview(1)['summaries'],[])
        self.assertEqual(len(hub.overview(1,True)['summaries']),1)
        hub.save_summary(1,{**payload,'published':True});self.assertEqual(len(hub.overview(1)['summaries']),1)
        with self.assertRaises(PermissionError):hub.save_summary(2,payload)
    def test_error_is_scoped_and_can_be_resolved(self):
        payload={'subject':'PHYSICS','topic':'Единицы','description':'Не переводит сантиметры в метры'}
        hub.save_error(1,payload);item=hub.overview(1)['errors'][0]
        self.assertEqual(hub.overview(2)['errors'],[])
        with self.assertRaises(PermissionError):hub.save_error(2,{**payload,'id':item['id']})
        hub.save_error(1,{**payload,'id':item['id'],'status':'RESOLVED'});self.assertEqual(hub.overview(1)['errors'][0]['status'],'RESOLVED')
    def test_plan_progress_and_invalid_update_preserves_plan(self):
        data={'subject':'PHYSICS','target':'ЕГЭ 80 баллов','steps':[{'title':'Механика','status':'DONE'},{'title':'Оптика'}]}
        hub.save_plan(1,data);self.assertEqual(hub.overview(1)['plans'][0]['progress_percent'],50)
        with self.assertRaises(ValueError):hub.save_plan(1,{**data,'steps':[{'title':'Оптика','status':'BAD'}]})
        self.assertEqual(hub.overview(1)['plans'][0]['progress_percent'],50)
    def wait(self):
        day=(datetime.now(timezone.utc)+timedelta(days=2)).date().isoformat()
        data={'subject':'PHYSICS','preferred_date':day,'preferred_from':'16:00','preferred_to':'18:00','timezone':'Europe/Samara'}
        return hub.add_wait(1,data)['id'],data,day+'T12:00:00+00:00'
    def test_timezone_matching_and_duration_window(self):
        rid,data,start=self.wait();self.assertEqual(hub.add_wait(1,data)['id'],rid)
        self.assertEqual(len(hub.candidates(start,60,'PHYSICS')),1)
        self.assertEqual(len(hub.candidates(start,180,'PHYSICS')),0)
        self.assertEqual(hub.candidates(start,60,'CHEMISTRY'),[])
        with self.assertRaises(ValueError):hub.candidates(start[:19],60,'PHYSICS')
    def test_offer_scope_acceptance_and_withdrawal(self):
        rid,data,start=self.wait();hub.offer(rid,start,60);hub.offer(rid,start,60)
        offers=hub.overview(1)['offers'];self.assertEqual(len(offers),1)
        with self.assertRaises(PermissionError):hub.respond_offer(2,offers[0]['id'],'ACCEPTED')
        rid2=hub.add_wait(2,data)['id'];hub.offer(rid2,start,60)
        other=hub.overview(2)['offers'][0]['id']
        self.assertEqual(hub.respond_offer(1,offers[0]['id'],'ACCEPTED')['booking'],'teacher_confirmation_required')
        with self.assertRaises(ValueError):hub.respond_offer(2,other,'ACCEPTED')
        hub.close_wait(2,rid2)
        self.assertEqual(hub.overview(2)['offers'][0]['status'],'WITHDRAWN')
    def test_russian_material_search_and_access(self):
        mid=library.create_material('ЗАКОН НЬЮТОНА','Конспект',subject='PHYSICS',file_path='/private/file.pdf')
        library.grant_student(mid,1);rows=hub.material_search(1,'закон')
        self.assertEqual(len(rows),1);self.assertNotIn('file_path',rows[0]);self.assertEqual(hub.material_search(2,'закон'),[])
    def test_occupied_slot_cannot_be_offered_or_accepted(self):
        rid,data,start=self.wait();guard.blocked=True
        with self.assertRaises(ValueError):hub.offer(rid,start,60)
        guard.blocked=False;hub.offer(rid,start,60);oid=hub.overview(1)['offers'][0]['id'];guard.blocked=True
        with self.assertRaises(ValueError):hub.respond_offer(1,oid,'ACCEPTED')
        self.assertEqual(hub.overview(1)['offers'][0]['status'],'OFFERED')
    def test_http_identity_is_not_overridden_by_user_input(self):
        h=Handler('student');code,data=h.learning_get('/api/student/learning',{'user_id':['2']});self.assertEqual(code,200);self.assertEqual(data['student']['id'],1)
        h=Handler('parent');self.assertEqual(h.learning_get('/api/parent/learning',{'user_id':['2']})[0],404)
        self.assertEqual(h.learning_get('/api/parent/learning',{'user_id':['1']})[0],200)
        h=Handler(None);self.assertEqual(h.learning_get('/api/teacher/learning',{'user_id':['1']})[0],401)
        h=Handler('student',{});h.origin=False;self.assertEqual(h.learning_post('/api/student/learning/wait')[0],403)
        self.assertEqual(Handler('student',{}).learning_post('/api/teacher/learning/plan')[0],401)

if __name__=='__main__':unittest.main()
