"""Real formula SQLite/seed checks plus scoped help and canonical booking tests."""
from pathlib import Path
import sys,types,tempfile,sqlite3,unittest,json
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
tmp=tempfile.TemporaryDirectory();path=Path(tmp.name)/'db.sqlite'
def connect():
 c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row;return c
db=types.ModuleType('database');db.connect=connect;db.now_iso=lambda:datetime.now().isoformat();db.get_setting=lambda key,default=None:'Europe/Moscow' if key=='schedule_timezone' else default;sys.modules['database']=db
from web_backend import formula_book,formula_catalog_seed,learning_tools
integration=types.ModuleType('integrations.lesson_sync');integration.sync_lesson=lambda lid:{};sys.modules['integrations']=types.ModuleType('integrations');sys.modules['integrations.lesson_sync']=integration
push=types.ModuleType('web_backend.push_events');push.student_and_parents=lambda *a,**kw:{};push.teachers=lambda *a,**kw:{};sys.modules['web_backend.push_events']=push
from web_backend import teacher_manual_booking as booking
class Tests(unittest.TestCase):
 def setUp(self):
  if path.exists():path.unlink()
  c=connect();c.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,study_goal TEXT,main_subject TEXT);INSERT INTO users VALUES(1,'Ученик','SCHOOL','PHYSICS'),(2,'Другой','SCHOOL','CHEMISTRY');CREATE TABLE lessons(id INTEGER PRIMARY KEY,user_id INTEGER,start_time TEXT,duration_minutes INTEGER,study_goal TEXT,subject TEXT,lesson_status TEXT,program_id INTEGER);");c.commit();c.close()
  db.get_user=lambda uid:dict(id=uid,name='Ученик',study_goal='SCHOOL',main_subject='PHYSICS')
  db.get_student_programs=lambda uid,**kw:[{'id':3,'study_goal':'EGE','subject':'PHYSICS'}] if uid==1 else []
  db.get_program_rate_info=lambda pid:{'effective_rate':2100}
  db.get_student_rate=lambda *args:1000
  db.calculate_lesson_price=lambda rate,duration:round(rate*duration/60)
  db.get_lesson=lambda lid:{'id':lid}
  def create(uid,goal,subject,start,end,duration,rate,price,**kw):
   self.created=(uid,goal,subject,start,end,duration,rate,price,kw)
   c=connect();cur=c.execute("INSERT INTO lessons(user_id,start_time,duration_minutes,study_goal,subject,lesson_status) VALUES(?,?,?,?,?,'CONFIRMED')",(uid,start,duration,goal,subject));c.commit();c.close();return cur.lastrowid
  db.create_admin_lesson=create;booking.sync_lesson=lambda lid:{};booking.push_events.student_and_parents=lambda *a,**kw:{}
 def test_seed_idempotent_and_preserves_teacher_edit(self):
  result=formula_catalog_seed.seed();self.assertGreater(result['created'],200)
  c=connect();fid=c.execute('SELECT id FROM formula_book LIMIT 1').fetchone()[0];c.execute("UPDATE formula_book SET title='МОЯ ПРАВКА' WHERE id=?",(fid,));c.commit();c.close()
  self.assertEqual(formula_catalog_seed.seed()['created'],0);self.assertEqual(formula_book.formula_detail(fid)['title'],'МОЯ ПРАВКА')
 def test_cyrillic_search_and_topics(self):
  formula_catalog_seed.seed();rows=formula_book.list_formulas(search='НЬЮТОНА');self.assertGreaterEqual(len(rows),2)
  self.assertGreaterEqual(len(formula_book.facets()['topics']),20)
 def test_seed_reuses_existing_formula_and_favorite(self):
  formula_book.ensure_tables();fid=formula_book.create_formula({'subject':'PHYSICS','title':'Мой закон Ома','formula_latex':r'I=\frac{U}{R}'})['id'];formula_book.set_favorite(fid,1)
  result=formula_catalog_seed.seed();self.assertGreaterEqual(result['linked_existing'],1);self.assertEqual(formula_book.formula_detail(fid,1)['favorite'],1)
 def test_help_scope_and_duplicate_retry(self):
  source=types.ModuleType('web_backend.student_homework');source.detail=lambda hid,uid:{'homework':{'id':hid}} if (hid,uid)==(9,1) else None
  sys.modules['web_backend.student_homework']=source
  import web_backend
  web_backend.student_homework=source
  data={'homework_id':9,'question':'Не понимаю, как выбрать ось','topic':'Динамика'}
  first=learning_tools.request_help(1,data);self.assertEqual(first['id'],learning_tools.request_help(1,data)['id'])
  with self.assertRaises(PermissionError):learning_tools.request_help(2,data)
  self.assertEqual(learning_tools.list_help(2),[])
  learning_tools.close_help(first['id']);self.assertEqual(learning_tools.list_help(),[])
 def test_booking_program_tariff_timezone_and_retry(self):
  formula_catalog_seed.seed();fid=formula_book.list_formulas(subject='PHYSICS')[0]['id'];start=(datetime.now()+timedelta(days=2)).replace(hour=15,minute=0,second=0,microsecond=0).isoformat()+'+04:00'
  data=booking.create(1,start,90,'AWAITING_PAYMENT',3,'Динамика',fid)
  self.assertEqual(data['price'],3150);self.assertEqual(self.created[1],'EGE');self.assertIn('T14:00:00',self.created[3]);self.assertEqual(booking.create(1,start,90,'AWAITING_PAYMENT',3)['already_created'],True)
  c=connect();self.assertEqual(c.execute('SELECT topic FROM learning_lesson_topics').fetchone()[0],'Динамика');c.close()
 def test_wrong_program_or_subject_is_rejected(self):
  future=(datetime.now()+timedelta(days=2)).isoformat()
  with self.assertRaises(ValueError):booking.create(1,future,60,'FREE',99)
  fid=formula_book.create_formula({'subject':'CHEMISTRY','title':'Моль','formula_latex':'n=m/M'})['id']
  with self.assertRaises(ValueError):booking.create(1,future,60,'FREE',3,formula_id=fid)
if __name__=='__main__':unittest.main()
