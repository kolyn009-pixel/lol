import ast,concurrent.futures,importlib.util,sqlite3,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'test.db';self.old={k:sys.modules.get(k) for k in ('database','web_backend','web_backend.group_finance')}
  def connect():
   c=sqlite3.connect(self.db,timeout=15);c.row_factory=sqlite3.Row;return c
  db=types.ModuleType('database');db.connect=connect;db.now_iso=lambda:'2026-10-31T12:00:00';sys.modules['database']=db
  c=connect();c.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);INSERT INTO users VALUES(1,'Иван'),(2,'Мария');CREATE TABLE study_groups(id INTEGER PRIMARY KEY,name TEXT,price_per_lesson INTEGER,active INTEGER);INSERT INTO study_groups VALUES(1,'Физика',900,1),(2,'Другая',500,1);CREATE TABLE group_members(group_id INTEGER,user_id INTEGER,status TEXT);INSERT INTO group_members VALUES(1,1,'ACTIVE'),(1,2,'ACTIVE');CREATE TABLE group_lessons(id INTEGER PRIMARY KEY,group_id INTEGER,start_time TEXT,end_time TEXT,status TEXT);INSERT INTO group_lessons VALUES(10,1,'2026-11-01T16:00:00','2026-11-01T17:00:00','SCHEDULED'),(11,1,'2026-11-03T16:00:00','2026-11-03T17:00:00','SCHEDULED');CREATE TABLE group_lesson_participants(lesson_id INTEGER,user_id INTEGER);INSERT INTO group_lesson_participants VALUES(10,1),(10,2),(11,1);""");c.close()
  pkg=types.ModuleType('web_backend');gf=types.ModuleType('web_backend.group_finance');env={'database':db,'group_lessons':types.SimpleNamespace(ensure_schema=lambda:None)}
  tree=ast.parse((ROOT/'web_backend/group_finance.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='ensure_schema');exec(compile(ast.Module(body=[node],type_ignores=[]),'schema','exec'),env);gf.ensure_schema=env['ensure_schema'];gf.ensure_schema();pkg.group_finance=gf;sys.modules['web_backend']=pkg;sys.modules['web_backend.group_finance']=gf
  spec=importlib.util.spec_from_file_location('group_finance_admin',ROOT/'web_backend/group_finance_admin.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
  c=connect();c.executescript("""INSERT INTO group_package_options(id,group_id,lessons_count,total_amount,active,validity_days,sort_order,created_at,updated_at) VALUES(1,1,4,3600,1,30,1,'2026-10-31','2026-10-31');INSERT INTO group_payments(id,group_id,user_id,payment_kind,package_option_id,lessons_count,unit_price,total_amount,status,created_at) VALUES(1,1,1,'PACKAGE',1,4,900,3600,'PENDING','2026-10-31');""");c.close();self.connect=connect
 def tearDown(self):
  for k,v in self.old.items():
   if v is None:sys.modules.pop(k,None)
   else:sys.modules[k]=v
  self.temp.cleanup()
 def test_concurrent_approval_once_and_actor(self):
  with concurrent.futures.ThreadPoolExecutor(2) as p:results=list(p.map(lambda _:self.m.confirm(1,1,77,3600),range(2)))
  c=self.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_subscriptions').fetchone()[0],1);self.assertEqual(c.execute('SELECT teacher_id FROM group_payment_audit').fetchone()[0],77);self.assertEqual(sum(bool(r.get('already_paid')) for r in results),1);c.close()
 def test_wrong_group_or_amount_never_credits(self):
  for gid,amount in [(2,3600),(1,1)]:
   with self.assertRaises(ValueError):self.m.confirm(gid,1,77,amount)
  c=self.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_subscriptions').fetchone()[0],0);c.close()
 def test_available_balance_is_not_reservation_and_readonly(self):
  self.m.confirm(1,1,77,3600);before=self.db.read_bytes();v=self.m.overview(1);self.assertEqual(v['received'],3600);self.assertEqual(v['members'][0]['remaining'],4);self.assertTrue(all(x['status']=='AVAILABLE' for x in v['cells'] if x['user_id']==1));self.assertTrue(all(x['status']=='UNPAID' for x in v['cells'] if x['user_id']==2));self.assertEqual(self.db.read_bytes(),before)
  c=self.connect();sid=c.execute('SELECT id FROM group_subscriptions').fetchone()[0];c.execute("INSERT INTO group_subscription_ledger(subscription_id,lesson_id,delta,reason,created_at) VALUES(?,10,-1,'LESSON_RESERVE','2026-10-31')",(sid,));c.commit();c.close();v=self.m.overview(1);self.assertEqual(next(x for x in v['cells'] if x['lesson_id']==10 and x['user_id']==1)['status'],'RESERVED');self.assertEqual(next(x for x in v['cells'] if x['lesson_id']==11)['status'],'AVAILABLE')
if __name__=='__main__':unittest.main()
