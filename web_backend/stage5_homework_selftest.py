"""Isolated smoke test for Stage 5 Homework Center.

Run against a COPY of tutor.db, never production:
  ADELIA_DB_PATH=/tmp/tutor-stage5.db python -m web_backend.stage5_homework_selftest

The test creates its own student/homework rows inside the supplied database and
verifies the canonical manual + structured revision lifecycle. It intentionally
fails when pointed at the default production DB path.
"""
from __future__ import annotations
import os, sys

DB_PATH=os.environ.get('ADELIA_DB_PATH','').strip()
if not DB_PATH or DB_PATH in {'tutor.db','/opt/tutorbot/tutor.db'}:
    raise SystemExit('Refusing to run: set ADELIA_DB_PATH to an isolated database copy')

from database import connect, now_iso
from web_backend.assessment import ensure_tables, homework_lifecycle
from web_backend.manual_homework import submit as manual_submit
from web_backend.homework_review_flow import finalize


def check(ok,msg):
    if not ok:raise AssertionError(msg)


def main():
    ensure_tables();conn=connect();now=now_iso()
    # Reuse an existing active student from the isolated copy so schema defaults
    # and project-specific user constraints remain authoritative.
    user=conn.execute("SELECT id FROM users WHERE active=1 ORDER BY id LIMIT 1").fetchone()
    check(user is not None,'isolated DB has no active student');uid=int(user['id'])
    cur=conn.execute("INSERT INTO homework(user_id,study_goal,subject,title,description,homework_type,source_type,status,assigned_at,updated_at) VALUES(?,?,?,?,?,'MAIN','CUSTOM','ASSIGNED',?,?)",(uid,'GENERAL','PHYSICS','Stage5 manual selftest','manual lifecycle',now,now));hid=int(cur.lastrowid);conn.commit();conn.close()
    try:
        first=manual_submit(hid,uid);check(first.get('status')=='ok','manual submit failed')
        blocked=manual_submit(hid,uid);check(blocked.get('status')=='attempt_pending_review','duplicate attempt was not blocked')
        rev=finalize(hid,uid,'REVISION','selftest revision',1);check(rev.get('status')=='ok','revision finalize failed')
        life=homework_lifecycle(hid,uid);check(life.get('retry_allowed') and life.get('next_attempt_number')==2,'revision did not unlock retry')
        second=manual_submit(hid,uid);check(second.get('attempt_number')==2,'second attempt number invalid')
        accepted=finalize(hid,uid,'ACCEPTED','selftest accepted',2);check(accepted.get('status')=='ok','accept finalize failed')
        repeat=finalize(hid,uid,'ACCEPTED','selftest accepted',2);check(repeat.get('already_finalized') is True,'finalize is not idempotent')
        life=homework_lifecycle(hid,uid);check(life.get('completed') and not life.get('can_submit'),'accepted homework still allows submission')
        print('STAGE5_HOMEWORK_SELFTEST_OK')
    finally:
        conn=connect();conn.execute('DELETE FROM homework_reviews WHERE homework_id=?',(hid,));conn.execute('DELETE FROM homework_submissions WHERE homework_id=?',(hid,));conn.execute('DELETE FROM homework WHERE id=?',(hid,));conn.commit();conn.close()

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('STAGE5_HOMEWORK_SELFTEST_FAILED:',repr(exc),file=sys.stderr);raise
