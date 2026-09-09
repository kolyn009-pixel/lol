"""Isolated Stage 9 parent-cabinet self-test.

The test uses a temporary TutorBot database only. It verifies the core privacy
invariant (a parent can read only linked students), one-time web authentication,
and the stable parent dashboard/progress payload shape.
"""
from __future__ import annotations
import os, tempfile
from datetime import datetime, timedelta

_tmp=tempfile.TemporaryDirectory(prefix='tutorbot-stage9-')
os.environ['TUTORBOT_TEST_DATA_DIR']=_tmp.name
os.environ['TUTORBOT_TEST_DB']=os.path.join(_tmp.name,'stage9.db')

import database
database.set_test_mode(True)
database.create_tables()

from learning import schema as learning_schema
learning_schema.initialize(database.DB_PATH)

from web_backend.parent_auth import create_parent_login_code,consume_parent_login_code
from web_backend.parent_portal import dashboard,student,schedule,linked_students


def eq(actual,expected,label):
    if actual!=expected:raise AssertionError(f'{label}: expected {expected!r}, got {actual!r}')


def truth(value,label):
    if not value:raise AssertionError(label)


def denied(fn,label):
    try:fn()
    except PermissionError:return
    raise AssertionError(label+': permission error not raised')


def seed():
    now=database.now_iso();conn=database.connect()
    p1=conn.execute("INSERT INTO parent_accounts(name,phone,telegram_id,active,created_at) VALUES(?,?,?,?,?)",('Parent One','+70000000001',900001,1,now)).lastrowid
    p2=conn.execute("INSERT INTO parent_accounts(name,phone,telegram_id,active,created_at) VALUES(?,?,?,?,?)",('Parent Two','+70000000002',900002,1,now)).lastrowid
    s1=conn.execute("INSERT INTO users(name,grade,study_goal,main_subject,active,created_at) VALUES(?,?,?,?,1,?)",('Child One',9,'OGE','PHYSICS',now)).lastrowid
    s2=conn.execute("INSERT INTO users(name,grade,study_goal,main_subject,active,created_at) VALUES(?,?,?,?,1,?)",('Child Two',11,'EGE','PHYSICS',now)).lastrowid
    conn.execute("INSERT INTO parent_student_links(parent_id,student_id,notify_schedule) VALUES(?,?,1)",(p1,s1))
    conn.execute("INSERT INTO parent_student_links(parent_id,student_id,notify_schedule) VALUES(?,?,1)",(p2,s2))
    conn.execute("INSERT INTO student_programs(user_id,study_goal,subject,is_primary,active,approval_status,created_by,created_at) VALUES(?,?,?,1,1,'APPROVED','SELFTEST',?)",(s1,'OGE','PHYSICS',now))
    future=(datetime.now()+timedelta(days=1)).replace(microsecond=0);end=future+timedelta(hours=1)
    conn.execute("INSERT INTO lessons(user_id,start_time,end_time,duration_minutes,subject,study_goal,hourly_rate,price,lesson_status,payment_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(s1,future.isoformat(),end.isoformat(),60,'PHYSICS','OGE',1800,1800,'CONFIRMED','WAITING',now))
    conn.execute("INSERT INTO payments(user_id,study_goal,subject,lessons_count,price_per_lesson,total_amount,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(s1,'OGE','PHYSICS',1,1800,1800,'WAITING',now))
    conn.execute("INSERT INTO student_goals(user_id,subject,study_goal,target_text,target_score,target_date,status,created_at,updated_at) VALUES(?,?,?,?,?,?, 'ACTIVE',?,?)",(s1,'PHYSICS','OGE','Сдать ОГЭ уверенно',30,(datetime.now()+timedelta(days=120)).date().isoformat(),now,now))
    conn.commit();conn.close();return int(p1),int(p2),int(s1),int(s2)


def main():
    p1,p2,s1,s2=seed()
    issued=create_parent_login_code(p1)
    truth(len(issued['code'])==6 and issued['code'].isdigit(),'six digit parent code')
    first=consume_parent_login_code(issued['code']);eq(first['status'],'ok','first code use');eq(int(first['parent']['id']),p1,'code parent identity')
    second=consume_parent_login_code(issued['code']);eq(second['status'],'used_code','code is single use')

    children=linked_students(p1);eq([int(x['id']) for x in children],[s1],'linked student scope')
    data=dashboard(p1);eq(data['summary']['students'],1,'dashboard student count');eq(data['summary']['upcoming_lessons'],1,'dashboard upcoming');eq(data['summary']['waiting_amount'],1800,'dashboard waiting amount')
    card=student(p1,s1);eq(card['student']['name'],'Child One','own child card');truth('progress' in card,'progress exposed');truth(card['progress']['goal'] is not None,'goal exposed')
    denied(lambda:student(p1,s2),'foreign child card blocked')
    denied(lambda:schedule(p1,s2),'foreign child schedule blocked')

    # Parent payload must not expose teacher-private note tables or answer keys.
    for forbidden in ('student_private_notes','private_notes','solution','answer'):
        truth(forbidden not in repr(card).lower(),f'private field hidden: {forbidden}')

    print('Stage 9 selftest: OK')

if __name__=='__main__':
    try:main()
    finally:_tmp.cleanup()
