"""Absence previews, privacy, payment preservation and concurrent slot claims."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sys,tempfile,unittest,ast,inspect
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database
from web_backend import day_off_planner as p,group_lessons
from deploy_day_off_20261022 import patch_database

# The installer preserves server edits by applying a narrow AST-located guard.
# Test exactly that candidate function without publishing full runtime files.
candidate=ast.parse(patch_database(inspect.getsource(database)))
guarded=next(n for n in candidate.body if isinstance(n,ast.FunctionDef) and n.name=='auto_cancel_unpaid_lesson')
exec(compile(ast.Module(body=[guarded],type_ignores=[]),'candidate_database_guard','exec'),database.__dict__)

class DayOff(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=database.DB_NAME;database.DB_NAME=str(Path(self.temp.name)/'test.db');database.create_tables();group_lessons.ensure_schema();p.ensure_schema()
  self.clock=patch.object(p,'now',return_value=datetime(2026,11,1,10));self.clock.start();self.worker=patch.object(p,'start_worker');self.worker.start()
  from core import schedule_sync
  self.sync=patch.object(schedule_sync,'sync_lessons_blocking',return_value={'failed':[]});self.sync.start()
  c=database.connect()
  for uid in (1,2):c.execute("INSERT INTO users(id,name,grade,study_goal,main_subject,active,created_at) VALUES(?,?,11,'EGE','PHYSICS',1,'2026-01-01')",(uid,'Ученик '+str(uid)))
  for d in range(7):c.execute("INSERT INTO working_hours(weekday,start_time,end_time,active,week_type,created_at) VALUES(?,'08:00','22:00',1,'ALL','2026-01-01')",(d,))
  self.add_lesson(c,37,1,'2026-11-03T18:30:00','2026-11-03T19:30:00')
  c.execute("CREATE TABLE IF NOT EXISTS parent_accounts(id INTEGER PRIMARY KEY,active INTEGER,telegram_id INTEGER)")
  c.execute('CREATE TABLE IF NOT EXISTS parent_student_links(parent_id INTEGER,student_id INTEGER)');c.execute("INSERT INTO parent_accounts(id,active,telegram_id,name,created_at) VALUES(5,1,555,'Мама','2026-01-01')");c.execute("INSERT INTO parent_student_links(parent_id,student_id,created_at) VALUES(5,1,'2026-01-01')");c.commit();c.close()
  self.body={'date':'2026-11-03','end_date':'2026-11-03','whole_day':True,'reason':'Моя секретная причина','share_reason':False}

 def tearDown(self):self.sync.stop();self.worker.stop();self.clock.stop();database.DB_NAME=self.old;self.temp.cleanup()
 def add_lesson(self,c,lid,uid,start,end):
  c.execute("INSERT INTO lessons(id,user_id,study_goal,subject,start_time,end_time,duration_minutes,price,payment_status,charged,lesson_status,created_at) VALUES(?,?,'EGE','PHYSICS',?,?,60,900,'PAID',1,'CONFIRMED','2026-01-01')",(lid,uid,start,end))
 def save(self,body=None):return p.save({'preview_token':p.preview(body or self.body)['preview_token']})

 def test_preview_is_read_only_and_parent_text_and_private_reason(self):
  d=p.preview(self.body);self.assertEqual(d['affected_count'],1);self.assertEqual(len(d['messages']),2)
  self.assertTrue(any(x['role']=='parent' and 'Ученик 1' in x['body'] for x in d['messages']))
  self.assertNotIn(self.body['reason'],str(d['messages']));c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM schedule_exceptions').fetchone()[0],0);c.close()
  self.save();self.assertNotIn(self.body['reason'],str(p.invitations(1)));self.assertIn(self.body['reason'],str(p.invitations(teacher=True)))

 def test_same_preview_and_overlapping_day_do_not_duplicate_messages(self):
  preview=p.preview(self.body);a=p.save(preview);b=p.save(preview);self.assertEqual(a['batch_id'],b['batch_id']);self.assertTrue(b['already_saved']);self.save()
  c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM day_off_invitations').fetchone()[0],1);self.assertEqual(c.execute('SELECT COUNT(*) FROM schedule_exceptions').fetchone()[0],1);self.assertEqual(c.execute('SELECT COUNT(*) FROM day_off_deliveries').fetchone()[0],3);c.close()

 def test_stale_preview_is_rejected_and_new_bookings_are_not_missed(self):
  d=p.preview(self.body);c=database.connect();self.add_lesson(c,38,2,'2026-11-03T20:00:00','2026-11-03T21:00:00');c.commit();c.close()
  with self.assertRaisesRegex(ValueError,'изменилось'):p.save(d)
  self.assertEqual(len(p.invitations(teacher=True)['items']),0)

 def test_interval_boundary_and_offset_aware_overnight(self):
  d=p.preview({**self.body,'whole_day':False,'start_time':'19:30','end_time':'20:30'});self.assertEqual(d['affected_count'],0)
  c=database.connect();self.add_lesson(c,38,2,'2026-11-02T22:30:00+00:00','2026-11-02T23:30:00+00:00');c.commit();c.close()
  self.assertEqual(p.preview(self.body)['affected_count'],2)

 def test_private_or_public_custom_reason(self):
  d=p.preview({**self.body,'share_reason':True,'reason':'Срочная поездка'});self.assertTrue(all('Срочная поездка' in x['body'] for x in d['messages']))

 def test_quarter_hour_adjacent_and_closed_slots(self):
  self.save();iid=p.invitations(1)['items'][0]['id'];c=database.connect();self.add_lesson(c,38,2,'2026-11-04T18:00:00','2026-11-04T18:30:00');c.commit();c.close()
  starts={s['start_time'] for d in p.slots(iid,1)['items'] for s in d['slots']}
  self.assertIn('2026-11-04T18:30:00',starts);self.assertIn('2026-11-04T18:45:00',starts);self.assertNotIn('2026-11-03T18:30:00',starts)

 def test_move_keeps_same_lesson_price_payment_and_consumes_entitlement(self):
  self.save();iid=p.invitations(1)['items'][0]['id'];self.assertTrue(p.suppress_reminder(37));r=p.move(iid,'2026-11-04T18:45:00',1)
  self.assertTrue(r['payment_preserved']);self.assertFalse(p.suppress_reminder(37));c=database.connect();l=c.execute('SELECT * FROM lessons WHERE id=37').fetchone();self.assertEqual(l['payment_status'],'PAID');self.assertEqual(l['price'],900);self.assertEqual(l['charged'],1);self.assertEqual(l['end_time'],'2026-11-04T19:45:00');self.assertEqual(c.execute('SELECT COUNT(*) FROM lessons').fetchone()[0],1);self.assertEqual(c.execute('SELECT COUNT(*) FROM teacher_day_off_lessons').fetchone()[0],0);c.close()
  with self.assertRaises(ValueError):p.move(iid,'2026-11-04T20:00:00',1)

 def test_ownership_and_bad_starts(self):
  self.save();iid=p.invitations(1)['items'][0]['id'];self.assertEqual(p.invitations(2)['items'],[])
  with self.assertRaises(PermissionError):p.slots(iid,2)
  with self.assertRaises(PermissionError):p.move(iid,'2026-11-04T18:45:00',2)
  for start in ['2026-11-03T18:30:00','2026-11-04T18:17:00','2026-10-01T18:30:00']:
   with self.assertRaises(ValueError):p.move(iid,start,1)

 def test_concurrent_moves_cannot_double_book(self):
  c=database.connect();self.add_lesson(c,38,2,'2026-11-03T20:00:00','2026-11-03T21:00:00');c.commit();c.close();self.save();items=p.invitations(teacher=True)['items']
  def reserve(r):
   try:p.move(r['id'],'2026-11-04T18:45:00',teacher=True);return True
   except ValueError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,items))
  self.assertEqual(sorted(results),[False,True])

 def test_group_is_moved_together_by_teacher_and_keeps_participant_payment(self):
  group=group_lessons.create_group('ЕГЭ','PHYSICS','EGE',900);slot=group_lessons.add_initial_slot(group['id'],1,'20:00',90);lid=group_lessons.generate_lesson(group['id'],slot['slot_id'],'2026-11-03T20:00:00')['lesson_id']
  c=database.connect();c.execute("INSERT OR REPLACE INTO group_lesson_participants(lesson_id,user_id,attendance_status,payment_status,created_at,updated_at) VALUES(?,1,'PLANNED','PAID',?,?)",(lid,database.now_iso(),database.now_iso()));c.commit();c.close();self.save();item=next(x for x in p.invitations(teacher=True)['items'] if x['kind']=='GROUP')
  with self.assertRaises(PermissionError):p.move(item['id'],'2026-11-04T18:45:00',1)
  p.move(item['id'],'2026-11-04T18:45:00',teacher=True);c=database.connect();self.assertEqual(c.execute('SELECT payment_status FROM group_lesson_participants WHERE lesson_id=?',(lid,)).fetchone()[0],'PAID');self.assertEqual(c.execute('SELECT end_time FROM group_lessons WHERE id=?',(lid,)).fetchone()[0],'2026-11-04T20:15:00');c.close()

 def test_delete_exception_does_not_remove_free_move_offer(self):
  self.save();c=database.connect();c.execute('DELETE FROM schedule_exceptions');c.commit();c.close();self.assertTrue(p.suppress_reminder(37));self.assertEqual(p.invitations(1)['items'][0]['status'],'WAITING')

 def test_delivery_claim_is_not_repeated(self):
  self.save();c=database.connect();c.execute("UPDATE day_off_deliveries SET status='SENT'");c.commit();c.close();self.assertEqual(p.dispatch()['SENT'],3)

 def test_student_timezone_and_parent_ownership(self):
  c=database.connect();c.execute('CREATE TABLE student_desktop_timezones(user_id INTEGER PRIMARY KEY,zone_name TEXT,label TEXT,updated_at TEXT)');c.execute("INSERT INTO student_desktop_timezones VALUES(1,'Europe/Samara','Самара','2026-10-22')");c.commit();c.close()
  d=p.preview(self.body);self.assertTrue(all('19:30' in x['body'] for x in d['messages']));self.save();item=p.invitations(1)['items'][0];self.assertEqual(item['viewer_timezone'],'Europe/Samara')
  from web_backend.day_off_api import DayOffMixin
  api=DayOffMixin();self.assertEqual(api._dayoff_uid('parent',{'id':5},item['id']),1)
  with self.assertRaises(PermissionError):api._dayoff_uid('parent',{'id':99},item['id'])
  api._json=lambda code,body:(code,body);api.path='/api/teacher/day-off/invitations';api._teacher=lambda:None;self.assertEqual(api.do_GET()[0],401)
  api.path='/api/teacher/day-off/save';api._same_origin_write=lambda:False;self.assertEqual(api.do_POST()[0],403)

 def test_calendar_queue_and_stale_job_suppression(self):
  self.save();iid=p.invitations(1)['items'][0]['id'];p.move(iid,'2026-11-04T18:45:00',1)
  self.assertTrue(p.suppress_reminder(37,'LESSON_2H'));self.assertFalse(p.suppress_reminder(37))
  p.sync_calendar_jobs();c=database.connect();self.assertEqual(c.execute('SELECT status FROM day_off_calendar_jobs').fetchone()[0],'DONE');c.close()

 def test_unpaid_lesson_is_not_cancelled_by_old_deadline(self):
  c=database.connect();c.execute("UPDATE lessons SET payment_status='AWAITING_PAYMENT',payment_deadline='2026-11-01T08:00:00',charged=0 WHERE id=37");c.commit();c.close();self.save();iid=p.invitations(1)['items'][0]['id']
  self.assertTrue(p.hold_auto_cancel(37));self.assertFalse(database.auto_cancel_unpaid_lesson(37))
  p.move(iid,'2026-11-04T18:45:00',1);self.assertTrue(p.hold_auto_cancel(37));self.assertFalse(database.auto_cancel_unpaid_lesson(37));c=database.connect();r=c.execute('SELECT lesson_status,payment_deadline FROM lessons WHERE id=37').fetchone();self.assertEqual(r['lesson_status'],'CONFIRMED');self.assertEqual(r['payment_deadline'],'2026-11-04T16:45:00');c.close()

if __name__=='__main__':unittest.main()
