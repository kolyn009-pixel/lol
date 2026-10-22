"""Quarter-hour start times with production generators and real collision data."""
import ast
from datetime import date,datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest
from zoneinfo import ZoneInfo
from availability_timezone_selftest import TimezoneTests,database,guard,public_trial_slots

ROOT=Path(__file__).resolve().parents[1]

def functions(path,names,scope):
 tree=ast.parse(path.read_text())
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),scope)
 return scope

def constant(path,name):
 for node in ast.parse(path.read_text()).body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):return ast.literal_eval(node.value)
 raise AssertionError('Missing constant '+name)


class QuarterHourTests(unittest.TestCase):
 setUp=TimezoneTests.setUp
 tearDown=TimezoneTests.tearDown

 def schedule(self):
  day=(datetime.now(ZoneInfo('Europe/Moscow'))+timedelta(days=2)).date()
  self.conn.execute('INSERT INTO working_hours VALUES(?,?,?,?,?)',(day.weekday(),'17:00','21:00',1,'ALL'))
  self.conn.execute('INSERT INTO lessons VALUES(1,?,?,?)',(f'{day}T17:30:00+03:00',f'{day}T18:30:00+03:00','CONFIRMED'))
  self.conn.commit();return day

 def test_public_trial_every_quarter_after_any_busy_end(self):
  day=self.schedule()
  for end in ('18:15','18:30','18:45'):
   self.conn.execute('UPDATE lessons SET end_time=? WHERE id=1',(f'{day}T{end}:00+03:00',));self.conn.commit()
   slots=[s for d in public_trial_slots.feed('Europe/Moscow',days=3)['items'] for s in d['slots'] if s['start_time'].startswith(str(day))]
   labels={s['label'] for s in slots}
   self.assertIn(end,labels)
   previous=(datetime.fromisoformat(f'{day}T{end}')-timedelta(minutes=15)).strftime('%H:%M')
   self.assertNotIn(previous,labels)
   self.assertTrue(all(datetime.fromisoformat(s['end_time'])-datetime.fromisoformat(s['start_time'])==timedelta(minutes=60) for s in slots))

 def test_student_one_off_and_reschedule_generator(self):
  day=self.schedule()
  path=ROOT/'web_backend/student_booking.py'
  scope=dict(database=database,availability_guard=guard,datetime=datetime,date=date,timedelta=timedelta,
             DEFAULT_DURATION=60,STEP_MINUTES=constant(path,'STEP_MINUTES'),_program_owned=lambda *_:None)
  fn=functions(path,{'free_slots'},scope)['free_slots']
  labels={s['label'] for d in fn(1,1,days=3) if d['date']==str(day) for s in d['slots']}
  self.assertTrue({'18:30','18:45','19:00','19:15','19:30','19:45','20:00'}<=labels)
  self.assertNotIn('18:15',labels)

 def test_telegram_slot_generator(self):
  day=self.schedule();tz=ZoneInfo('Europe/Moscow');start=datetime.combine(day,datetime.min.time(),tzinfo=tz).replace(hour=17)
  scope=dict(database=database,datetime=datetime,timedelta=timedelta,TIMEZONE=tz,
             SLOT_STEP_MINUTES=constant(ROOT/'bot.py','SLOT_STEP_MINUTES'),get_work_intervals=lambda _: [(start,start.replace(hour=21))],get_busy_periods=lambda _:[])
  fn=functions(ROOT/'bot.py',{'get_free_slots'},scope)['get_free_slots']
  labels={s.strftime('%H:%M') for s in fn(day,60)}
  self.assertTrue({'18:30','18:45','19:00','19:15'}<=labels)
  self.assertNotIn('18:15',labels)

 def test_permanent_schedule_default_step(self):
  day=self.schedule()
  values=database.get_regular_recurring_slots(day.weekday(),60,anchor_date=day)
  self.assertTrue({'17:00','17:15','17:30','17:45','18:00'}<=set(values))
  self.assertEqual(len(values),13)

 def test_returning_student_schedule_options(self):
  day=self.schedule();path=ROOT/'web_backend/onboarding_schedule_options.py'
  scope=dict(database=database,datetime=datetime,timedelta=timedelta,ZoneInfo=ZoneInfo,
    student_onboarding=SimpleNamespace(status_payload=lambda _:dict(status='REGION_SET',timezone='Europe/Moscow')),
    STEP_MINUTES=constant(path,'STEP_MINUTES'),DURATION_MINUTES=60,DAY_KEYS=['MON','TUE','WED','THU','FRI','SAT','SUN'])
  fn=functions(path,{'_minutes','_recurring_busy','_closed_by_exception','feed'},scope)['feed']
  values={s['time'] for d in fn('fixture')['items'] if d['date']==str(day) for s in d['slots']}
  self.assertTrue({'17:00','17:15','17:30','17:45'}<=values)

 def test_cascade_can_shift_another_quarter(self):
  day=self.schedule();start=datetime.fromisoformat(f'{day}T18:15:00')
  scope=dict(datetime=datetime,timedelta=timedelta,is_inside_working_hours=lambda *_:True,
    find_occupant=lambda candidate,end,**_:candidate==start)
  fn=functions(ROOT/'final_features/slot_change.py',{'_cascade_target'},scope)['_cascade_target']
  occupant=dict(id=2,start_time=f'{day}T18:00:00',end_time=f'{day}T19:00:00')
  result=fn(occupant,start,1)
  self.assertEqual(result[0].strftime('%H:%M'),'18:30')
  self.assertEqual(result[1]-result[0],timedelta(minutes=60))


if __name__=='__main__':unittest.main()
