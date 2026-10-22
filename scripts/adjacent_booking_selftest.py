"""Regression: 18:30 finish permits an 18:30 booking/reschedule."""
import ast
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import database


def extracted(path,name,namespace):
 tree=ast.parse(path.read_text())
 node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
 return namespace[name]


class AdjacentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=database.DB_NAME
  database.DB_NAME=str(Path(self.tmp.name)/'test.db')
  self.c=database.connect()
  self.c.executescript('''CREATE TABLE bot_settings(key TEXT PRIMARY KEY,value TEXT);
  INSERT INTO bot_settings VALUES('schedule_timezone','Europe/Moscow');
  CREATE TABLE lessons(id INTEGER PRIMARY KEY,start_time TEXT,end_time TEXT,lesson_status TEXT);
  ''')
  self.tz=ZoneInfo('Europe/Moscow')
  self.day=(datetime.now(self.tz)+timedelta(days=2)).date().isoformat()
  self.insert(1,'17:30:00+03:00','18:30:00+03:00')
  self.occupant=extracted(ROOT/'final_features/slot_change.py','find_occupant',dict(database=database,datetime=datetime,ACTIVE_STATUSES=('PENDING','CONFIRMED','IN_PROGRESS')))

 def tearDown(self):
  self.c.close();database.DB_NAME=self.old;self.tmp.cleanup()

 def stamp(self,clock):return f'{self.day}T{clock}'

 def insert(self,lid,start,end,status='CONFIRMED'):
  self.c.execute('INSERT INTO lessons VALUES(?,?,?,?)',(lid,self.stamp(start),self.stamp(end),status));self.c.commit()

 def test_touching_offset_and_short_precision_are_available(self):
  for clock in ('18:30','18:30:00','18:30:00+03:00','15:30:00Z','19:30:00+04:00'):
   end=datetime.fromisoformat(self.stamp(clock))+timedelta(minutes=60)
   self.assertFalse(database.is_slot_reserved(self.stamp(clock),end.isoformat()),clock)
   self.assertIsNone(self.occupant(datetime.fromisoformat(self.stamp(clock)),end),clock)

 def test_real_overlap_still_blocked(self):
  for start,end in [('18:00:00','19:00:00'),('18:29:00','19:29:00'),('16:00:00','19:00:00')]:
   self.assertTrue(database.is_slot_reserved(self.stamp(start),self.stamp(end)))
   self.assertEqual(self.occupant(self.stamp(start),self.stamp(end))['id'],1)

 def test_next_lesson_at_1930_allows_1830_hour(self):
  self.insert(2,'19:30:00','20:30:00')
  self.assertFalse(database.is_slot_reserved(self.stamp('18:30:00'),self.stamp('19:30:00')))
  self.assertTrue(database.is_slot_reserved(self.stamp('18:30:00'),self.stamp('20:00:00')))

 def test_reschedule_ignores_only_requested_lesson(self):
  self.assertFalse(database.is_slot_reserved(self.stamp('17:30:00'),self.stamp('18:30:00'),exclude_lesson_id=1))
  self.assertIsNone(self.occupant(self.stamp('17:30:00'),self.stamp('18:30:00'),exclude_lesson_id=1))
  self.insert(2,'18:00:00','19:00:00','PENDING')
  self.assertTrue(database.is_slot_reserved(self.stamp('17:30:00'),self.stamp('18:30:00'),exclude_lesson_id=1))
  self.assertEqual(self.occupant(self.stamp('17:30:00'),self.stamp('18:30:00'),exclude_lesson_id=1)['id'],2)

 def test_cancelled_lesson_does_not_block(self):
  self.insert(2,'18:30:00','19:30:00','CANCELLED')
  self.assertFalse(database.is_slot_reserved(self.stamp('18:30:00'),self.stamp('19:30:00')))

 def test_actual_bot_slot_generator_returns_1830(self):
  start=datetime.fromisoformat(self.stamp('17:00:00')).replace(tzinfo=self.tz)
  end=start.replace(hour=21)
  ns=dict(database=database,datetime=datetime,timedelta=timedelta,TIMEZONE=self.tz,SLOT_STEP_MINUTES=30,
          get_work_intervals=lambda day:[(start,end)],get_busy_periods=lambda day:[])
  slots=extracted(ROOT/'bot.py','get_free_slots',ns)(start.date(),60)
  labels=[x.strftime('%H:%M') for x in slots]
  self.assertIn('18:30',labels)
  self.assertNotIn('18:00',labels)


if __name__=='__main__':unittest.main()
