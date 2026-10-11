"""Isolated read-marker and conversation-boundary regression tests."""
import pathlib
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
tmp=tempfile.TemporaryDirectory()
def connect():
    conn=sqlite3.connect(str(pathlib.Path(tmp.name)/'test.db'))
    conn.row_factory=sqlite3.Row
    return conn
db=types.ModuleType('database');db.connect=connect;db.now_iso=lambda:'2026-10-04T16:00:00'
sys.modules['database']=db
from web_backend import unified_messaging as um
from web_backend.message_read_sync import mark_conversation_read
from web_backend.message_receipts import receipt,utc_timestamp

class Tests(unittest.TestCase):
    def setUp(self):
        um.ensure_tables();conn=connect()
        conn.executescript('DELETE FROM unified_messages; DELETE FROM unified_conversations; CREATE TABLE IF NOT EXISTS crm_student_messages(id INTEGER PRIMARY KEY,student_id INTEGER,direction TEXT,status TEXT,read_at TEXT); DELETE FROM crm_student_messages;')
        conn.commit();conn.close()
    def test_read_boundary_and_first_timestamp(self):
        first=um.record_message(1,'IN','first',status='QUEUED')
        second=um.record_message(1,'IN','arrived after history',status='DELIVERED')
        out=um.record_message(1,'OUT','teacher message')
        other=um.record_message(2,'IN','other student')
        cid=um.conversation(1)['id']
        result=mark_conversation_read(cid,first)
        rows={r['id']:r for r in um.history(cid)}
        self.assertEqual(rows[first]['status'],'READ')
        stamp=rows[first]['read_at'];self.assertIsNotNone(datetime.fromisoformat(stamp).tzinfo)
        self.assertIsNone(rows[second]['read_at']);self.assertIsNone(rows[out]['read_at'])
        self.assertIsNone(um.history(um.conversation(2)['id'])[0]['read_at'])
        self.assertEqual(result['changed'],1)
        self.assertEqual(mark_conversation_read(cid,first)['changed'],0)
        self.assertEqual(um.history(cid)[-1]['read_at'],stamp)
    def test_parent_does_not_clear_student(self):
        student=um.record_message(1,'IN','student',legacy_source='crm_student_messages',legacy_id=50)
        parent=um.record_message(1,'IN','parent',participant_type='PARENT',participant_id=7)
        conn=connect();conn.execute("INSERT INTO crm_student_messages VALUES(50,1,'IN','DELIVERED',NULL)");conn.commit();conn.close()
        mark_conversation_read(um.conversation(1,'PARENT',7)['id'],parent)
        self.assertIsNone(um.history(um.conversation(1)['id'])[0]['read_at'])
        conn=connect();self.assertIsNone(conn.execute('SELECT read_at FROM crm_student_messages').fetchone()[0]);conn.close()
        mark_conversation_read(um.conversation(1)['id'],student)
        conn=connect();self.assertIsNotNone(conn.execute('SELECT read_at FROM crm_student_messages').fetchone()[0]);conn.close()
    def test_utc_normalization_and_status(self):
        self.assertEqual(utc_timestamp('2026-10-04T20:00:00+04:00'),'2026-10-04T16:00:00+00:00')
        self.assertIsNone(utc_timestamp('not a date'))
        self.assertEqual(receipt({'status':'DELIVERED'})['status'],'DELIVERED')
        self.assertEqual(receipt({'status':'QUEUED'})['status'],'SENT')
        self.assertEqual(receipt({'status':'QUEUED','read_at':'2026-10-04T16:00:00Z'})['status'],'READ')

if __name__=='__main__':unittest.main()
