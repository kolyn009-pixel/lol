"""Isolated Stage 8 smoke/self-test.

Run manually from the repository root. It switches database.py into test mode and
never touches tutor.db. The test verifies the most important finance invariants:
shared tariffs, student overrides, package quotes, immutable lesson snapshots and
calendar/prepayment analytics.
"""
from __future__ import annotations
from datetime import datetime,timedelta
import os, tempfile

_tmp=tempfile.TemporaryDirectory(prefix='tutorbot-stage8-')
os.environ['TUTORBOT_TEST_DATA_DIR']=_tmp.name
os.environ['TUTORBOT_TEST_DB']=os.path.join(_tmp.name,'stage8.db')

import database
database.set_test_mode(True)
database.create_tables()

from web_backend.finance_pricing import set_price,lesson_snapshot,save_package
from web_backend.finance_price_sync import set_override,delete_override,quote,package_quote
from web_backend.finance_reporting import calendar_analytics


def eq(actual,expected,label):
    if actual!=expected:raise AssertionError(f'{label}: expected {expected!r}, got {actual!r}')


def truth(value,label):
    if not value:raise AssertionError(label)


def add_student(name='Stage8 Test',grade=11,goal='EGE',subject='PHYSICS'):
    conn=database.connect();cur=conn.execute("INSERT INTO users(name,grade,study_goal,main_subject,active,created_at) VALUES(?,?,?,?,1,?)",(name,grade,goal,subject,database.now_iso()));uid=int(cur.lastrowid);conn.execute("INSERT INTO student_programs(user_id,study_goal,subject,is_primary,active,approval_status,created_by,created_at) VALUES(?,?,?,1,1,'APPROVED','SELFTEST',?)",(uid,goal,subject,database.now_iso()));conn.commit();conn.close();return uid


def main():
    uid=add_student()
    set_price('EGE_PHYSICS',2000)
    q=quote(uid,None,90)
    eq(q['tariff_key'],'EGE_PHYSICS','automatic tariff')
    eq(q['amount'],3000,'90 minute catalog quote')

    set_override(uid,'EGE_PHYSICS',2250,'selftest')
    q=quote(uid,None,60)
    eq(q['amount'],2250,'web override quote')
    eq(q['source'],'STUDENT_OVERRIDE','override priority')
    conn=database.connect();u=conn.execute('SELECT ege_physics_rate FROM users WHERE id=?',(uid,)).fetchone();p=conn.execute("SELECT custom_hourly_rate FROM student_programs WHERE user_id=? AND study_goal='EGE' AND subject='PHYSICS'",(uid,)).fetchone();conn.close()
    eq(int(u['ege_physics_rate']),2250,'legacy user rate sync')
    eq(int(p['custom_hourly_rate']),2250,'student program sync')

    snap=lesson_snapshot(uid,60,'EGE','PHYSICS',11,'SCHOOL')
    eq(snap['price'],2250,'lesson snapshot')
    conn=database.connect();now=datetime.now();start=(now-timedelta(days=1)).replace(microsecond=0).isoformat();end=(now+timedelta(hours=1)).replace(microsecond=0).isoformat();cur=conn.execute("INSERT INTO lessons(user_id,start_time,end_time,duration_minutes,subject,study_goal,hourly_rate,price,lesson_status,payment_status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uid,start,end,60,'PHYSICS','EGE',snap['hourly_rate'],snap['price'],'COMPLETED','PAID',database.now_iso()));lesson_id=int(cur.lastrowid);conn.commit();conn.close()

    set_override(uid,'EGE_PHYSICS',2500,'new price')
    conn=database.connect();old=conn.execute('SELECT price,hourly_rate FROM lessons WHERE id=?',(lesson_id,)).fetchone();conn.close()
    eq(int(old['price']),2250,'historical lesson price immutable')
    eq(int(old['hourly_rate']),2250,'historical hourly rate immutable')

    save_package('TEST4','4 занятия',4,10,None,'EGE_PHYSICS')
    pq=package_quote(uid,'TEST4',None,60)
    eq(pq['lesson_amount'],2500,'package uses current student rate')
    eq(pq['total_amount'],9000,'package discount')

    delete_override(uid,'EGE_PHYSICS')
    q=quote(uid,None,60)
    eq(q['amount'],2000,'return to catalog after override removal')
    conn=database.connect();u=conn.execute('SELECT ege_physics_rate FROM users WHERE id=?',(uid,)).fetchone();p=conn.execute("SELECT custom_hourly_rate FROM student_programs WHERE user_id=? AND study_goal='EGE' AND subject='PHYSICS'",(uid,)).fetchone();conn.close()
    eq(u['ege_physics_rate'],None,'legacy user rate cleared')
    eq(p['custom_hourly_rate'],None,'student program rate cleared')

    analytics=calendar_analytics()
    truth('week' in analytics and 'month' in analytics,'calendar analytics shape')
    for period in ('week','month'):
        truth('planned' in analytics[period],f'{period} planned')
        truth('worked' in analytics[period],f'{period} worked')
        truth('remaining' in analytics[period],f'{period} remaining')
        truth('received_confirmed' in analytics[period],f'{period} received')
        truth('already_paid_before_period' in analytics[period],f'{period} prepaid')

    print('Stage 8 selftest: OK')

if __name__=='__main__':
    try:main()
    finally:_tmp.cleanup()
