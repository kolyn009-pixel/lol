"""Isolated Calendar provider/SQLite tests. Does not contact Google or send messages."""
import ast
import asyncio
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, AsyncMock, Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TMP=tempfile.TemporaryDirectory()
DB=Path(TMP.name)/'test.db'
def connect():
    c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;return c
fake=types.ModuleType('database');fake.connect=connect
fake.now_iso=lambda:'2030-01-01T00:00:00'
fake.get_setting=lambda k,d=None: 'Europe/Moscow' if k in ('schedule_timezone','bot_timezone') else d
fake.table_exists=lambda c,t:bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone())
def one(table,id):
    c=connect()
    try:return c.execute('SELECT * FROM '+table+' WHERE id=?',(id,)).fetchone()
    finally:c.close()
fake.get_lesson=lambda id:one('lessons',id)
fake.get_user=lambda id:one('users',id)
sys.modules['database']=fake
from integrations import google_calendar as g
from core.lesson_reschedule_details import message,previous
from handlers import calendar_runtime as runtime
class Failure(Exception):
    def __init__(self,status):self.resp=types.SimpleNamespace(status=status)
class Call:
    def __init__(self,fn):self.fn=fn
    def execute(self):return self.fn()
class Provider:
    def __init__(self):self.items={};self.calls=[];self.fail_delete=None;self.inserted=0
    def events(self):return self
    def list(self,**kw):
        owner=kw['privateExtendedProperty'].split('=')[1]
        return Call(lambda:{'items':[dict(v,id=k) for k,v in self.items.items() if v.get('extendedProperties',{}).get('private',{}).get('tutorbot_lesson_id')==owner]})
    def get(self,**kw):
        def work():
            if kw['eventId'] not in self.items:raise Failure(404)
            return self.items[kw['eventId']]
        return Call(work)
    def delete(self,**kw):
        def work():
            self.calls.append(('delete',kw['eventId']))
            if self.fail_delete:raise Failure(self.fail_delete)
            if kw['eventId'] not in self.items:raise Failure(410)
            del self.items[kw['eventId']];return {}
        return Call(work)
    def update(self,**kw):
        def work():
            key=kw['eventId'];self.calls.append(('update',key))
            if key not in self.items:raise Failure(404)
            self.items[key]=dict(kw['body']);return dict(kw['body'],id=key)
        return Call(work)
    def insert(self,**kw):
        def work():
            self.inserted+=1;key='new'+str(self.inserted);self.items[key]=kw['body'];return dict(kw['body'],id=key)
        return Call(work)
def event(owner=None):
    return {'extendedProperties':{'private':{'tutorbot_lesson_id':str(owner)}}} if owner else {}
class Tests(unittest.TestCase):
    def setUp(self):
        c=connect();c.executescript('''DROP TABLE IF EXISTS lessons; DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS lesson_external_integrations; DROP TABLE IF EXISTS slot_change_requests;
        DROP TABLE IF EXISTS calendar_lesson_state;
        CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,grade TEXT,board_url TEXT);
        INSERT INTO users VALUES(1,'Иван','10','');
        CREATE TABLE lessons(id INTEGER PRIMARY KEY,user_id INTEGER,subject TEXT,study_goal TEXT,
          start_time TEXT,end_time TEXT,lesson_status TEXT,payment_status TEXT,google_event_id TEXT,
          rescheduled_from_lesson_id INTEGER,rescheduled_to_lesson_id INTEGER,is_trial INTEGER,finished_at TEXT,updated_at TEXT);
        INSERT INTO lessons VALUES(1,1,'физика','ЕГЭ','2030-02-01T16:30:00','2030-02-01T17:30:00','CANCELLED','TRANSFERRED',NULL,NULL,2,0,NULL,NULL);
        INSERT INTO lessons VALUES(2,1,'физика','ЕГЭ','2030-02-03T15:00:00','2030-02-03T16:00:00','CONFIRMED','PAID',NULL,1,NULL,0,NULL,NULL);
        ''');c.commit();c.close()
        self.provider=Provider();self.patcher=patch.object(g,'_service',return_value=self.provider);self.patcher.start()
    def tearDown(self):self.patcher.stop()
    def sql(self,sql,args=()):
        c=connect();c.execute(sql,args);c.commit();c.close()
    def test_legacy_only_deleted(self):
        self.sql("UPDATE lessons SET google_event_id='old' WHERE id=1")
        self.provider.items={'old':{},'personal':{}}
        g.cancel_lesson(1)
        self.assertEqual(set(self.provider.items),{'personal'})
    def test_all_owned_duplicates_deleted(self):
        self.provider.items={'a':event(1),'b':event(1),'personal':{},'other':event(22)}
        g.cancel_lesson(1)
        self.assertEqual(set(self.provider.items),{'personal','other'})
    def test_reassigned_event_not_deleted(self):
        g._save(1,event_id='shared');self.provider.items={'shared':event(2)}
        g.cancel_lesson(1);self.assertIn('shared',self.provider.items)
    def test_failure_retains_retry_ids(self):
        g._save(1,event_id='old');self.provider.items={'old':event(1)};self.provider.fail_delete=403
        with self.assertRaises(Failure):g.cancel_lesson(1)
        self.assertEqual(g._integration(1)['google_event_id'],'old')
        self.assertIn('google:',g._integration(1)['last_error'])
        self.provider.fail_delete=None;g.cancel_lesson(1);self.assertNotIn('old',self.provider.items)
    def test_transfer_cleanup_and_retry_no_duplicate(self):
        g._save(1,event_id='old');self.provider.items={'old':event(1)}
        g.cancel_lesson(1);g.sync_lesson(2);g.sync_lesson(2)
        self.assertEqual(len(self.provider.items),1);self.assertEqual(self.provider.inserted,1)
    def test_legacy_event_reused(self):
        self.sql("UPDATE lessons SET google_event_id='legacy' WHERE id=2")
        self.provider.items={'legacy':{}}
        self.assertEqual(g.sync_lesson(2)['event_id'],'legacy');self.assertEqual(self.provider.inserted,0)
    def test_active_duplicates_cleaned(self):
        self.provider.items={'a':event(2),'b':event(2),'personal':{}}
        g.sync_lesson(2);self.assertEqual(len(self.provider.items),2);self.assertIn('personal',self.provider.items)
    def test_cancelled_sync_cannot_recreate(self):
        self.provider.items={'old':event(1)};g.sync_lesson(1)
        self.assertEqual(self.provider.items,{});self.assertEqual(self.provider.inserted,0)
    def test_color_class_and_both_times(self):
        body=g._event_body(g._lesson(2))
        self.assertEqual(body['colorId'],'7');self.assertIn('10 класс',body['summary']);self.assertIn('ПЕРЕНЕСЕНО',body['summary'])
        self.assertIn('01.02.2030 · 16:30–17:30',body['description']);self.assertIn('03.02.2030 · 15:00–16:00',body['description'])
        self.assertEqual(body['start']['timeZone'],'Europe/Moscow')
        self.sql("UPDATE lessons SET lesson_status='COMPLETED' WHERE id=2")
        self.assertEqual(g._event_body(g._lesson(2))['colorId'],'10')
    def test_moscow_conversion_missing_grade(self):
        before=dict(fake.get_lesson(1));before.update(start_time='2030-02-01T22:30:00+00:00',end_time='2030-02-01T23:30:00+00:00')
        text=message(before,fake.get_lesson(2),{'name':'Иван','grade':None})
        self.assertIn('02.02.2030 · 01:30–02:30',text);self.assertIn('Класс не указан',text)
    def test_canonical_only_old_lesson_reconciled(self):
        self.sql("UPDATE lessons SET start_time='2020-01-01T16:00:00' WHERE id=1")
        g._save(1,event_id='old');self.provider.items={'old':event(1)}
        runtime._init_state_tables()
        asyncio.run(runtime._sync())
        self.assertNotIn('old',self.provider.items)
    def test_exchange_snapshot_only_when_applied(self):
        self.sql('''CREATE TABLE slot_change_requests(id INTEGER,requester_lesson_id INTEGER,occupant_lesson_id INTEGER,status TEXT,exchange_mode TEXT,desired_start TEXT,apply_requester_before_start TEXT,apply_requester_before_end TEXT,apply_occupant_before_start TEXT,apply_occupant_before_end TEXT,occupant_proposed_start TEXT)''')
        self.sql("UPDATE lessons SET rescheduled_from_lesson_id=NULL WHERE id=2")
        self.sql("INSERT INTO slot_change_requests VALUES(1,2,3,'APPLYING','SHIFT','2030-02-03T15:00:00','2030-02-01T12:00:00','2030-02-01T13:00:00','2030-02-03T15:00:00','2030-02-03T16:00:00','2030-02-03T16:00:00')")
        self.assertEqual(previous(fake.get_lesson(2))['start_time'],'2030-02-01T12:00:00')
        self.sql("UPDATE lessons SET start_time='2030-02-01T12:00:00' WHERE id=2")
        self.assertIsNone(previous(fake.get_lesson(2)))
    def test_telegram_confirm_uses_returned_lesson_row(self):
        tree=ast.parse((ROOT/'final_features/handlers.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='_apply_slot_request')
        refresh,notify=AsyncMock(),AsyncMock()
        slots=types.SimpleNamespace(get_request=lambda _: {'requester_lesson_id':1,'requester_student_id':1,'occupant_lesson_id':None},move_to_requested=lambda _:fake.get_lesson(2))
        ns={'database':fake,'slot_change':slots,'_refresh_calendar_and_reminders':refresh,'_notify_family':notify}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'test','exec'),ns)
        asyncio.run(ns['_apply_slot_request'](None,5))
        refresh.assert_awaited_once_with(None,[2])
        self.assertIn('Было: 01.02.2030',notify.call_args.args[2])
        self.assertIn('Стало: 03.02.2030',notify.call_args.args[2])
    def test_teacher_move_links_to_replacement(self):
        from datetime import datetime,timedelta
        tree=ast.parse((ROOT/'web_backend/teacher_lesson_actions.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='propose_move')
        before=dict(fake.get_lesson(1),lesson_status='CONFIRMED',duration_minutes=60)
        slots=types.SimpleNamespace(create_request=lambda *a,**kw:5,get_request=lambda _:{'occupant_lesson_id':None},move_to_requested=lambda _:fake.get_lesson(2),set_status=Mock())
        delivery=Mock()
        ns={'datetime':datetime,'timedelta':timedelta,'slot_change':slots,'_lesson':lambda _:before,'move_message':message,'push_events':types.SimpleNamespace(student_and_parents=delivery)}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'test','exec'),ns)
        result=ns['propose_move'](1,'2030-02-03T15:00:00',99)
        self.assertEqual(result['lesson_id'],2)
        self.assertEqual(delivery.call_args.args[3],'/app/lesson/?id=2')
        self.assertIn('10 класс',delivery.call_args.args[2])
if __name__=='__main__':unittest.main()
