import importlib.util,sys,types,unittest,json
from pathlib import Path
from zoneinfo import ZoneInfo
from group_finance_admin_selftest import Tests,ROOT

def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class Reports(Tests):
 def setUp(self):
  super().setUp();self.extra={k:sys.modules.get(k) for k in ['core','core.lesson_time']};core=types.ModuleType('core');lt=types.ModuleType('core.lesson_time');lt.lesson_timezone=lambda:ZoneInfo('Europe/Moscow');core.lesson_time=lt;sys.modules['core']=core;sys.modules['core.lesson_time']=lt
  c=self.connect();c.executescript("ALTER TABLE group_lessons ADD COLUMN price_per_student INTEGER DEFAULT 900;ALTER TABLE group_lesson_participants ADD COLUMN attendance_status TEXT DEFAULT 'EXPECTED';CREATE TABLE parent_accounts(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);INSERT INTO parent_accounts VALUES(100,'Мама',1),(200,'Другой родитель',1);CREATE TABLE parent_student_links(parent_id INTEGER,student_id INTEGER);INSERT INTO parent_student_links VALUES(100,1),(100,2),(200,99);");c.close()
  self.reports=load('reports','web_backend/group_finance_reports.py')
  def financial(lid,uid):return {'covered':True,'status':'COVERED'} if uid==1 else {'covered':False,'status':'UNPAID'}
  sys.modules['web_backend'].group_finance.financial_status_for_lesson=financial
  singles=[{'user_id':uid,'lesson_id':uid,'subject':'PHYSICS','start_time':'2026-10-30T16:00:00','lesson_payment_status':'PAID' if uid==1 else 'UNPAID','lesson_status':'CONFIRMED','price':2000,'payment':None,'is_trial':False} for uid in (1,2,99)]
  sys.modules['web_backend'].calendar_week_invoices=types.SimpleNamespace(candidates=lambda **kw:{'items':singles})
 def tearDown(self):
  for k,v in self.extra.items():
   if v is None:sys.modules.pop(k,None)
   else:sys.modules[k]=v
  super().tearDown()
 def test_forecast_is_separate_from_received_and_excludes_other_week(self):
  self.m.confirm(1,1,77,3600);before=self.db.read_bytes();d=self.reports.forecast(1,'2026-10-31');self.assertEqual(d['start'],'2026-10-26');self.assertEqual(d['scheduled_estimate'],1800);self.assertEqual(d['received'],3600);self.assertEqual(d['completed_estimate'],0);self.assertEqual(self.db.read_bytes(),before)
 def test_family_draft_does_not_double_bill_pending_balance(self):
  before=self.db.read_bytes();d=self.reports.family_week(1,100,'2026-10-31');self.assertTrue(d['draft']);self.assertEqual(d['draft_total'],2900);self.assertEqual(d['needs_review'],1);self.assertEqual(len(d['items']),4);self.assertEqual(self.db.read_bytes(),before)
  with self.assertRaises(ValueError):self.reports.family_week(1,200,'2026-10-31')
 def test_receipt_scope_path_and_content_checks(self):
  m=load('receipts','web_backend/group_finance_receipts.py');root=Path(self.temp.name)/'receipts';root.mkdir();m.ROOTS=(root,);file=root/'p.pdf';file.write_bytes(b'%PDF-1.7\nfixture');c=self.connect();c.execute('UPDATE group_payments SET receipt_ref=? WHERE id=1',(str(file),));c.commit();c.close();self.assertEqual(m.read(1,1)[1],'application/pdf')
  with self.assertRaises(ValueError):m.read(2,1)
  file.write_bytes(b'<html>unsafe</html>')
  with self.assertRaises(ValueError):m.read(1,1)
  file.unlink();outside=Path(self.temp.name)/'outside.pdf';outside.write_bytes(b'%PDF-1.7');file.symlink_to(outside)
  with self.assertRaises(ValueError):m.read(1,1)

class Hooks(unittest.TestCase):
 def test_idempotence(self):
  module=load('installer','scripts/install_release_ui.py');hs=json.loads((ROOT/'scripts/group_finance_hooks.json').read_text());new=(ROOT/'web_backend/group_workspace_api.py').read_text();h=hs['web_backend/group_workspace_api.py'];old=new
  for item in reversed(h):old=old.replace(item['new'],item['old'])
  self.assertEqual(module.apply_hunks(old,h),new);self.assertEqual(module.apply_hunks(new,h),new);self.assertEqual(module.apply_hunks('# external edit\n'+old,h),'# external edit\n'+new)
if __name__=='__main__':unittest.main()
