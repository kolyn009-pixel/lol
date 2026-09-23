from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta

import database
from web_backend import finance_reporting, onboarding_schedule_options, public_trial_slots

root=tempfile.mkdtemp(prefix="adelia_rc_operational_")
db_path=os.path.join(root,"operational.db")
old_dir,old_db=database.TEST_DATA_DIR,database.TEST_DB_NAME
database.TEST_DATA_DIR,database.TEST_DB_NAME=root,db_path
database.set_test_mode(True)

try:
    database.create_tables()
    ts=database.now_iso()
    conn=database.connect()
    try:
        user_id=int(conn.execute(
            "INSERT INTO users(name,grade,study_goal,main_subject,created_at) VALUES(?,?,?,?,?)",
            ("RC Operations Student",11,"EGE","PHYSICS",ts),
        ).lastrowid)
        conn.commit()
    finally:
        conn.close()

    # A CLOSED exception must suppress both a whole day and overlapping intervals
    # in the booking flows that expose availability outside Telegram.
    closed_day=(datetime.now()+timedelta(days=3)).date()
    database.add_schedule_exception(closed_day.isoformat(),"CLOSED")
    assert onboarding_schedule_options._closed_by_exception(closed_day,10*60,11*60) is True

    conn=database.connect()
    try:
        tz=public_trial_slots._client_tz("Europe/Moscow")[1]
        start=datetime.combine(closed_day,datetime.min.time(),tzinfo=tz).replace(hour=10)
        end=start+timedelta(hours=1)
        assert public_trial_slots._closed_by_exception(conn,closed_day,start,end) is True
    finally:
        conn.close()

    partial_day=closed_day+timedelta(days=1)
    database.add_schedule_exception(partial_day.isoformat(),"CLOSED","12:00","14:00")
    assert onboarding_schedule_options._closed_by_exception(partial_day,12*60+30,13*60+30) is True
    assert onboarding_schedule_options._closed_by_exception(partial_day,9*60,10*60) is False

    # Teacher can record money received outside Adelia against a concrete lesson.
    start=datetime.now()+timedelta(days=2)
    lesson_id=int(database.create_admin_lesson(
        user_id=user_id,
        study_goal="EGE",
        subject="PHYSICS",
        start_time=start.isoformat(timespec="seconds"),
        end_time=(start+timedelta(minutes=60)).isoformat(timespec="seconds"),
        duration_minutes=60,
        hourly_rate=1800,
        price=1800,
        payment_mode="AWAITING_PAYMENT",
        force=True,
    ))
    result=finance_reporting.mark_lesson_paid(lesson_id)
    assert result["status"]=="ok"
    lesson=database.get_lesson(lesson_id)
    assert str(lesson["payment_status"])=="PAID"
    assert int(lesson["charged"] or 0)==1
    assert lesson["payment_id"] is not None
    assert lesson["package_id"] is not None

    conn=database.connect()
    try:
        payment=conn.execute("SELECT status,total_amount FROM payments WHERE id=?",(lesson["payment_id"],)).fetchone()
        packages=int(conn.execute("SELECT COUNT(*) n FROM lesson_packages WHERE payment_id=?",(lesson["payment_id"],)).fetchone()["n"])
    finally:
        conn.close()
    assert str(payment["status"])=="PAID"
    assert int(payment["total_amount"] or 0)==1800
    assert packages==1

    # Repeated UI/API action is idempotent and must not create another payment/package.
    retry=finance_reporting.mark_lesson_paid(lesson_id)
    assert retry["status"]=="already_paid"
    conn=database.connect()
    try:
        payment_count=int(conn.execute("SELECT COUNT(*) n FROM payments WHERE user_id=?",(user_id,)).fetchone()["n"])
        package_count=int(conn.execute("SELECT COUNT(*) n FROM lesson_packages WHERE user_id=?",(user_id,)).fetchone()["n"])
    finally:
        conn.close()
    assert payment_count==1
    assert package_count==1

    print("RC OPERATIONAL SELFTEST: OK")
    print(f"closed_day={closed_day.isoformat()} lesson_id={lesson_id} payment_id={lesson['payment_id']}")
finally:
    database.set_test_mode(False)
    database.TEST_DATA_DIR,database.TEST_DB_NAME=old_dir,old_db
    shutil.rmtree(root,ignore_errors=True)
