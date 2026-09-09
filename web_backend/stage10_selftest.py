"""Isolated Stage 10 unified messaging self-test.

Uses only a temporary TutorBot database. It verifies conversation deduplication,
legacy import, per-channel delivery state and read-state synchronization without
making real Telegram/VK network calls.
"""
from __future__ import annotations
import os,tempfile

_tmp=tempfile.TemporaryDirectory(prefix='tutorbot-stage10-')
os.environ['TUTORBOT_TEST_DATA_DIR']=_tmp.name
os.environ['TUTORBOT_TEST_DB']=os.path.join(_tmp.name,'stage10.db')

import database
database.set_test_mode(True)
database.create_tables()

from crm_plus import schema as crm_schema
crm_schema.initialize()

from web_backend import unified_messaging as um
from web_backend.message_read_sync import mark_conversation_read


def eq(actual,expected,label):
    if actual!=expected:raise AssertionError(f'{label}: expected {expected!r}, got {actual!r}')


def truth(value,label):
    if not value:raise AssertionError(label)


def seed_user():
    conn=database.connect();now=database.now_iso();cur=conn.execute("INSERT INTO users(name,grade,study_goal,main_subject,active,created_at) VALUES(?,?,?,?,1,?)",('Stage10 Student',9,'OGE','PHYSICS',now));uid=int(cur.lastrowid);conn.commit();conn.close();return uid


def main():
    uid=seed_user();um.ensure_tables()
    c1=um.conversation(uid);c2=um.conversation(uid)
    eq(c1['id'],c2['id'],'one logical student conversation')

    inbound=um.record_message(uid,'IN','Привет с сайта',origin_channel='WEB',sender_type='STUDENT',sender_id=uid,status='DELIVERED')
    outbound=um.record_message(uid,'OUT','Ответ преподавателя',origin_channel='WEB',sender_type='TEACHER',status='QUEUED')
    truth(inbound!=outbound,'separate logical messages')
    um.record_delivery(outbound,'TELEGRAM','STUDENT','12345','SENT')
    um.record_delivery(outbound,'VK','STUDENT','54321','FAILED',error_code='transport_error')
    hist=um.history(c1['id'],10)
    out=next(x for x in hist if x['id']==outbound)
    statuses={x['channel']:x['status'] for x in out['deliveries']}
    eq(statuses.get('TELEGRAM'),'SENT','telegram delivery tracked')
    eq(statuses.get('VK'),'FAILED','vk delivery tracked independently')

    # Legacy CRM import is idempotent and must not duplicate the same row.
    conn=database.connect();now=database.now_iso();cur=conn.execute("INSERT INTO crm_student_messages(student_id,direction,target,body,status,created_at) VALUES(?, 'IN','TEACHER',?,'DELIVERED',?)",(uid,'Legacy hello',now));legacy_id=int(cur.lastrowid);conn.commit();conn.close()
    um.import_legacy();um.import_legacy()
    conn=database.connect();count=conn.execute("SELECT COUNT(*) c FROM unified_messages WHERE legacy_source='crm_student_messages' AND legacy_id=?",(legacy_id,)).fetchone()['c'];conn.close();eq(int(count),1,'legacy import idempotent')

    # Read bridge clears both the unified unread flag and the matching legacy CRM row.
    mark_conversation_read(c1['id'])
    conn=database.connect();unread=conn.execute("SELECT COUNT(*) c FROM unified_messages WHERE conversation_id=? AND direction='IN' AND read_at IS NULL",(int(c1['id']),)).fetchone()['c'];legacy=conn.execute("SELECT status,read_at FROM crm_student_messages WHERE id=?",(legacy_id,)).fetchone();conn.close()
    eq(int(unread),0,'unified unread cleared')
    eq(str(legacy['status']),'READ','legacy status synchronized')
    truth(legacy['read_at'] is not None,'legacy read timestamp synchronized')

    dialogs=um.conversations(20)
    eq(len(dialogs),1,'one dialog in inbox')
    eq(int(dialogs[0]['unread'] or 0),0,'inbox unread synchronized')
    print('Stage 10 selftest: OK')

if __name__=='__main__':
    try:main()
    finally:_tmp.cleanup()
