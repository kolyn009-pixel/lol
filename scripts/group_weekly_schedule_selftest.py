"""Weekly group planning against real SQLite, including collisions and rollback."""
from datetime import datetime
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import group_workspace_selftest as base
import database
from web_backend import group_workspace as groups,group_lessons,group_weekly_schedule as planner
# Schema initialization is not needed by availability_snapshot when a connection is provided.
trial=ModuleType('web_backend.public_trial');trial.ensure_schema=lambda:None
sys.modules.setdefault('web_backend.public_trial',trial)
from web_backend import availability_guard as guard


class Frozen(datetime):
    @classmethod
    def now(cls,tz=None):return cls(2026,10,22,12,0,tzinfo=tz)


class Weekly(base.Groups):
    def setUp(self):
        super().setUp()
        self.freeze=patch.object(planner,'datetime',Frozen);self.freeze.start()
        c=database.connect();c.executescript('''
        CREATE TABLE lessons(id INTEGER PRIMARY KEY,start_time TEXT,end_time TEXT,lesson_status TEXT);
        CREATE TABLE public_trial_requests(id INTEGER PRIMARY KEY,selected_slot_start TEXT,selected_slot_end TEXT,status TEXT,expires_at TEXT);
        DROP TABLE regular_schedules;
        CREATE TABLE regular_schedules(id INTEGER PRIMARY KEY,weekday INTEGER,start_time TEXT,duration_minutes INTEGER,status TEXT,start_date TEXT,end_date TEXT,pause_until TEXT,active INTEGER);
        ''');c.commit();c.close()
        self.body={'weekday':2,'start_time':'18:15','duration_minutes':60,'starts_on':'2026-10-26','weeks':8}

    def tearDown(self):self.freeze.stop();super().tearDown()

    def test_increase_frequency_builds_all_lessons_and_preserves_old(self):
        oldslot=group_lessons.add_initial_slot(self.gid,0,'18:15',60)
        old=group_lessons.generate_lesson(self.gid,oldslot['slot_id'],'2026-10-26T18:15:00')
        groups.join(self.token,1)
        result=planner.add(self.gid,self.body)
        self.assertEqual(result['lesson_count'],8)
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_schedule_slots').fetchone()[0],2)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM group_lessons').fetchone()[0],9)
        p=c.execute("SELECT COUNT(*) FROM group_lesson_participants WHERE payment_status='PENDING' AND access_granted=0").fetchone()[0]
        self.assertEqual(p,9)
        self.assertEqual(c.execute('SELECT start_time FROM group_lessons WHERE id=?',(old['lesson_id'],)).fetchone()[0],'2026-10-26T18:15:00');c.close()
        planner.add(self.gid,self.body)
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_lessons').fetchone()[0],9);c.close()

    def test_late_conflict_leaves_no_partial_schedule(self):
        c=database.connect();c.execute("INSERT INTO lessons VALUES(1,'2026-12-16T15:30:00Z','2026-12-16T16:30:00Z','CONFIRMED')");c.commit();c.close()
        with self.assertRaisesRegex(ValueError,'schedule_conflict:16.12.2026'):planner.add(self.gid,self.body)
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM group_schedule_slots').fetchone()[0],0)
        self.assertEqual(c.execute('SELECT COUNT(*) FROM group_lessons').fetchone()[0],0);c.close()

    def test_adjacent_group_allowed_and_public_booking_sees_group(self):
        slot=group_lessons.add_initial_slot(self.gid,2,'17:15',60)
        group_lessons.generate_lesson(self.gid,slot['slot_id'],'2026-10-28T17:15:00')
        planner.add(self.gid,self.body)
        c=database.connect();snap=guard.availability_snapshot('2026-10-28T17:00','2026-10-28T20:00',conn=c);c.close()
        self.assertFalse(guard.is_available_from_snapshot('2026-10-28T18:30','2026-10-28T19:30',snap))
        self.assertTrue(guard.is_available_from_snapshot('2026-10-28T19:15','2026-10-28T20:15',snap))

    def test_recurring_group_without_lessons_blocks_overlap(self):
        other=group_lessons.create_group('Другая группа','PHYSICS','EGE',1200)
        group_lessons.add_initial_slot(other['id'],2,'18:30',60)
        with self.assertRaisesRegex(ValueError,'schedule_conflict:'):planner.add(self.gid,self.body)

    def test_terminal_individual_lesson_does_not_block(self):
        c=database.connect();c.execute("INSERT INTO lessons VALUES(1,'2026-10-28T18:15','2026-10-28T19:15','CANCELLED')");c.commit();c.close()
        self.assertEqual(planner.add(self.gid,self.body)['lesson_count'],8)

    def test_invalid_grid_and_bounds(self):
        for change in [{'start_time':'18:10'},{'weeks':0},{'weeks':27},{'duration_minutes':10},{'weekday':7},{'start_time':'23:45','duration_minutes':60}]:
            with self.assertRaises(ValueError):planner.add(self.gid,{**self.body,**change})


if __name__=='__main__':unittest.main()
