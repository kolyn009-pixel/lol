"""Real SQLite read-only fixtures: evidence, unknown legacy actor, group isolation and correction log."""
import importlib.util,json,sqlite3,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class HistoryTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'data.db';c=sqlite3.connect(self.path)
  c.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);INSERT INTO users VALUES(1,'Ученик'),(2,'Другой');
CREATE TABLE payments(id INTEGER PRIMARY KEY,user_id INTEGER,status TEXT,total_amount INTEGER,confirmed_at TEXT,created_at TEXT,source_type TEXT,source_platform TEXT);
INSERT INTO payments VALUES(7,1,'PAID',3000,'2026-10-31','2026-10-30',NULL,NULL);
CREATE TABLE lessons(id INTEGER PRIMARY KEY,user_id INTEGER,start_time TEXT,payment_status TEXT,payment_id INTEGER,package_id INTEGER);
INSERT INTO lessons VALUES(8,1,'2026-11-02T16:00','PAID',7,NULL),(9,1,'2026-11-05T16:00','RESERVED_BALANCE',NULL,10);
CREATE TABLE lesson_packages(id INTEGER PRIMARY KEY,user_id INTEGER,payment_id INTEGER);INSERT INTO lesson_packages VALUES(10,1,7);
CREATE TABLE group_payments(id INTEGER PRIMARY KEY,group_id INTEGER,user_id INTEGER,group_lesson_id INTEGER,status TEXT,total_amount INTEGER,receipt_ref TEXT,confirmed_at TEXT,created_at TEXT);
INSERT INTO group_payments VALUES(7,5,1,NULL,'PAID',1000,'private-secret','2026-10-31','2026-10-30');
CREATE TABLE group_lessons(id INTEGER PRIMARY KEY,group_id INTEGER,start_time TEXT);INSERT INTO group_lessons VALUES(20,5,'2026-11-03T16:00');
CREATE TABLE group_lesson_participants(lesson_id INTEGER,user_id INTEGER);INSERT INTO group_lesson_participants VALUES(20,1);
CREATE TABLE group_subscriptions(id INTEGER PRIMARY KEY,group_id INTEGER,user_id INTEGER,source_payment_id INTEGER);INSERT INTO group_subscriptions VALUES(30,5,1,7);
CREATE TABLE group_subscription_ledger(id INTEGER PRIMARY KEY,subscription_id INTEGER,lesson_id INTEGER,delta INTEGER,reason TEXT,created_at TEXT);
INSERT INTO group_subscription_ledger VALUES(1,30,20,-1,'LESSON_RESERVE','2026-10-31'),(2,30,20,1,'LESSON_REFUND','2026-11-01');
CREATE TABLE group_payment_audit(id INTEGER PRIMARY KEY,group_id INTEGER,payment_id INTEGER,teacher_id INTEGER,action TEXT,created_at TEXT);
INSERT INTO group_payment_audit VALUES(1,5,7,99,'CONFIRM','2026-10-31');
CREATE TABLE payment_reversals(payment_id INTEGER PRIMARY KEY,actor_id INTEGER,source TEXT,reason TEXT,snapshot TEXT,result TEXT,reversed_at TEXT);
''')
  c.execute('INSERT INTO payment_reversals VALUES(?,?,?,?,?,?,?)',(7,99,'WEB','Ошибка',json.dumps({'payment':{'user_id':1,'total_amount':3000,'private':'secret'}}),json.dumps({'lesson_ids':[8,9]}),'2026-11-01'));c.commit();c.close()
  fake=types.ModuleType('database')
  def connect():
   db=sqlite3.connect('file:'+str(self.path)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
  fake.connect=connect;self.old=sys.modules.get('database');sys.modules['database']=fake
  spec=importlib.util.spec_from_file_location('history',ROOT/'web_backend/payment_history.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
  self.before=self.path.read_bytes()
 def tearDown(self):
  self.assertEqual(self.before,self.path.read_bytes(),'reader changed the database')
  if self.old:sys.modules['database']=self.old
  else:sys.modules.pop('database',None)
  self.temp.cleanup()
 def test_legacy_unknown_not_invented(self):
  d=self.m.trace({'lesson_id':['8']});self.assertEqual(d['status'],'PAID');self.assertEqual(d['evidence'],[]);self.assertEqual(d['payment_id'],7)
 def test_package_link(self):
  d=self.m.trace({'lesson_id':['9']});self.assertEqual(d['status'],'RESERVED_BALANCE');self.assertEqual(d['payment_id'],7)
 def test_group_namespace_and_private_ref(self):
  d=self.m.trace({'kind':['group'],'group_id':['5'],'payment_id':['7']});self.assertEqual(d['amount'],1000);self.assertEqual(d['evidence'][0]['actor'],99);self.assertNotIn('private-secret',json.dumps(d))
  with self.assertRaises(ValueError):self.m.trace({'kind':['group'],'group_id':['6'],'payment_id':['7']})
 def test_group_reserve_matches_participant(self):
  d=self.m.trace({'kind':['group'],'group_id':['5'],'lesson_id':['20'],'user_id':['1']});self.assertEqual(len(d['evidence']),2)
  with self.assertRaises(ValueError):self.m.trace({'kind':['group'],'group_id':['5'],'lesson_id':['20'],'user_id':['2']})
 def test_journal_snapshot_not_exposed(self):
  d=self.m.journal();self.assertEqual(len(d['items']),2);x=next(x for x in d['items'] if x['amount']==3000);self.assertEqual(x['actor'],99);self.assertEqual(x['lesson_ids'],[8,9]);self.assertNotIn('secret',json.dumps(d));self.assertEqual(len(self.m.journal(5)['items']),1)
 def test_routes_require_teacher(self):
  import ast
  from urllib.parse import urlparse,parse_qs
  tree=ast.parse((ROOT/'web_backend/receipt_tools_api.py').read_text());node=next(x for x in tree.body if isinstance(x,ast.ClassDef));scope={'urlparse':urlparse,'parse_qs':parse_qs}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'routes','exec'),scope)
  for path in ['/api/teacher/finance/payment/trace?payment_id=7','/api/teacher/finance/payment/journal']:
   h=scope['ReceiptToolsMixin']();h.path=path;h._teacher=lambda:None;h._json=lambda status,body:(status,body)
   self.assertEqual(h.do_GET()[0],401)
 def test_bad_ids(self):
  with self.assertRaises(ValueError):self.m.trace({'payment_id':['7 OR 1=1']})

if __name__=='__main__':unittest.main()
