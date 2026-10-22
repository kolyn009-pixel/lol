"""Real SQLite and production slot feed, isolated from messaging/integrations."""
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
# The public-trial dependency is used only for schema initialization here.
# Every queried table exists in the isolated fixture below.
trial=ModuleType('web_backend.public_trial')
trial.ensure_schema=lambda: None
sys.modules['web_backend.public_trial']=trial
import database
from web_backend import availability_guard as guard, public_trial_slots


class TimezoneTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.previous=database.DB_NAME
  database.DB_NAME=str(Path(self.tmp.name)/'test.db')
  self.conn=database.connect()
  self.conn.executescript('''
   CREATE TABLE bot_settings(key TEXT PRIMARY KEY,value TEXT);
   INSERT INTO bot_settings VALUES('schedule_timezone','Europe/Moscow');
   INSERT INTO bot_settings VALUES('bot_timezone','Europe/Moscow');
   CREATE TABLE lessons(id INTEGER PRIMARY KEY,start_time TEXT,end_time TEXT,lesson_status TEXT);
   CREATE TABLE public_trial_requests(id INTEGER PRIMARY KEY,selected_slot_start TEXT,selected_slot_end TEXT,status TEXT,expires_at TEXT);
   CREATE TABLE regular_schedules(id INTEGER PRIMARY KEY,weekday INTEGER,start_time TEXT,duration_minutes INTEGER,status TEXT,start_date TEXT,end_date TEXT,pause_until TEXT,active INTEGER);
   CREATE TABLE working_hours(weekday INTEGER,start_time TEXT,end_time TEXT,active INTEGER,week_type TEXT);
   CREATE TABLE schedule_exceptions(date TEXT,exception_type TEXT,start_time TEXT,end_time TEXT);
  ''')
  self.conn.commit()

 def tearDown(self):
  self.conn.close();database.DB_NAME=self.previous;self.tmp.cleanup()

 def test_mixed_offsets_and_touching_intervals(self):
  self.assertTrue(guard.overlaps('2026-10-28T15:00:00','2026-10-28T16:00:00','2026-10-28T12:00:00Z','2026-10-28T13:00:00Z'))
  self.assertTrue(guard.overlaps('2026-10-28T15:00:00','2026-10-28T16:00:00','2026-10-28T16:00:00+04:00','2026-10-28T17:00:00+04:00'))
  self.assertFalse(guard.overlaps('2026-10-28T16:00:00','2026-10-28T17:00:00','2026-10-28T12:00:00Z','2026-10-28T13:00:00Z'))

 def test_sql_range_does_not_omit_shifted_date(self):
  self.conn.execute("INSERT INTO lessons VALUES(1,'2026-10-27T22:00:00+00:00','2026-10-27T23:00:00+00:00','CONFIRMED')")
  self.conn.commit()
  snap=guard.availability_snapshot('2026-10-28T00:30:00','2026-10-28T02:00:00',conn=self.conn)
  self.assertEqual([x['id'] for x in snap['lessons']],[1])
  self.assertFalse(guard.is_available_from_snapshot('2026-10-28T01:00:00','2026-10-28T01:30:00',snap))

 def test_trial_and_regular_conflicts(self):
  self.conn.execute("INSERT INTO public_trial_requests VALUES(2,'2026-10-28T12:00:00Z',NULL,'LINKING',NULL)")
  self.conn.execute("INSERT INTO regular_schedules VALUES(3,2,'17:00',60,'APPROVED',NULL,NULL,NULL,1)")
  self.conn.commit()
  snap=guard.availability_snapshot('2026-10-28T00:00:00','2026-10-29T00:00:00',conn=self.conn)
  self.assertFalse(guard.is_available_from_snapshot('2026-10-28T15:30:00','2026-10-28T16:00:00',snap))
  self.assertFalse(guard.is_available_from_snapshot('2026-10-28T14:30:00Z','2026-10-28T15:00:00Z',snap))

 def test_terminal_lessons_do_not_block(self):
  self.conn.executemany('INSERT INTO lessons VALUES(?,?,?,?)',[(1,'2026-10-28T12:00:00Z','2026-10-28T13:00:00Z','CANCELLED'),(2,'2026-10-28T12:00:00Z','2026-10-28T13:00:00Z','COMPLETED')])
  self.conn.commit()
  self.assertTrue(guard.is_available('2026-10-28T15:00:00','2026-10-28T16:00:00'))

 def test_public_feed_blocks_mixed_lesson_and_converts_student_time(self):
  from zoneinfo import ZoneInfo
  day=(datetime.now(ZoneInfo('Europe/Moscow'))+timedelta(days=1)).date()
  self.conn.executemany('INSERT INTO working_hours VALUES(?,?,?,?,?)',[(day.weekday(),'10:00','13:00',1,'ALL'),(day.weekday(),'16:00','18:00',1,'ALL')])
  # 08:00 UTC is 11:00 in the Moscow schedule.
  self.conn.execute('INSERT INTO lessons VALUES(1,?,?,?)',(f'{day}T08:00:00Z',f'{day}T09:00:00Z','CONFIRMED'))
  self.conn.commit()
  result=public_trial_slots.feed('Europe/Samara',days=2)
  slots=[s for d in result['items'] for s in d['slots'] if s['start_time'].startswith(str(day))]
  starts=[s['start_time'][11:16] for s in slots]
  self.assertIn('10:00',starts)
  self.assertIn('12:00',starts)
  self.assertNotIn('10:30',starts)
  self.assertNotIn('11:00',starts)
  self.assertNotIn('11:30',starts)
  self.assertNotIn('14:00',starts)
  first=next(s for s in slots if s['start_time'][11:16]=='10:00')
  self.assertEqual(first['label'],'11:00')


if __name__=='__main__':unittest.main()
