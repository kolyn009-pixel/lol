"""Isolated SQLite read-model verification; no production database or messages."""
import importlib.util,sqlite3,sys,tempfile,types,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db'
  def connect():
   c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row;return c
  self.connect=connect;fake=types.ModuleType('database');fake.connect=connect;fake.get_setting=lambda k,d=None:'Europe/Moscow';sys.modules['database']=fake
  spec=importlib.util.spec_from_file_location('read_model',ROOT/'web_backend/lesson_calendar.py');self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
  c=connect();c.executescript('CREATE TABLE lessons(id INTEGER PRIMARY KEY,rescheduled_from_lesson_id INTEGER,is_trial INTEGER);INSERT INTO lessons VALUES(1,22,0);INSERT INTO lessons VALUES(2,NULL,1);');c.commit();c.close()
  self.items=[{'id':1,'start_time':'2026-10-30T16:00:00'},{'id':2,'start_time':'2026-10-30T18:00:00'}]
 def tearDown(self):self.tmp.cleanup()
 def test_legacy_database_read_only(self):
  before=self.path.read_bytes();d=self.module.enrich_schedule('2026-10-30','2026-11-01',self.items,500)
  self.assertEqual(d['items'],self.items);self.assertTrue(d['calendar_items'][0]['rescheduled']);self.assertEqual(d['calendar_items'][1]['is_trial'],1)
  self.assertEqual(before,self.path.read_bytes());self.assertNotIn('kind',self.items[0])
 def test_group_lessons_are_real_records_and_separate_ids(self):
  c=self.connect();c.executescript('''CREATE TABLE study_groups(id INTEGER,name TEXT,subject TEXT,study_goal TEXT);INSERT INTO study_groups VALUES(3,'ЕГЭ','PHYSICS','EGE');CREATE TABLE group_lessons(id INTEGER,group_id INTEGER,start_time TEXT,end_time TEXT,status TEXT,price_per_student INTEGER);INSERT INTO group_lessons VALUES(1,3,'2026-10-30T17:00:00','2026-10-30T18:00:00','SCHEDULED',900);INSERT INTO group_lessons VALUES(2,3,'2026-12-30T17:00:00','2026-12-30T18:00:00','SCHEDULED',900);''');c.commit();c.close()
  d=self.module.enrich_schedule('2026-10-30','2026-11-01',self.items,500);groups=[x for x in d['calendar_items'] if x['kind']=='GROUP'];self.assertEqual(len(groups),1);self.assertEqual(groups[0]['id'],'group-1');self.assertEqual(groups[0]['group_id'],3);self.assertFalse(d['calendar_limit_reached'])
 def test_only_applied_exchange_at_current_target_marked(self):
  c=self.connect();c.executescript('''CREATE TABLE slot_change_requests(requester_lesson_id INTEGER,occupant_lesson_id INTEGER,status TEXT,exchange_mode TEXT,apply_requester_before_start TEXT,apply_occupant_before_start TEXT,desired_start TEXT,occupant_proposed_start TEXT);INSERT INTO slot_change_requests VALUES(2,NULL,'APPLIED','SHIFT','2026-10-30T17:00:00',NULL,'2026-10-30T18:00:00',NULL);''');c.commit();c.close()
  d=self.module.enrich_schedule('2026-10-30','2026-11-01',self.items,500);self.assertTrue(d['calendar_items'][1]['rescheduled'])
  self.items[1]['start_time']='2026-10-30T19:00:00';d=self.module.enrich_schedule('2026-10-30','2026-11-01',self.items,500);self.assertFalse(d['calendar_items'][1]['rescheduled'])
if __name__=='__main__':unittest.main()
