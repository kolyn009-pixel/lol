from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta

import database
from core import minute_balance
from web_backend import telemost_precreate_worker

root = tempfile.mkdtemp(prefix="adelia_rc_release_")
db_path = os.path.join(root, "release_gate.db")
old_dir, old_db = database.TEST_DATA_DIR, database.TEST_DB_NAME
database.TEST_DATA_DIR, database.TEST_DB_NAME = root, db_path
database.set_test_mode(True)

try:
    database.create_tables()
    minute_balance.ensure_schema()

    ts = database.now_iso()
    c = database.connect()
    try:
        cur = c.execute(
            """INSERT INTO users(name,grade,study_goal,main_subject,active,created_at)
               VALUES(?,?,?,?,1,?)""",
            ("RC Release Student", 11, "EGE", "PHYSICS", ts),
        )
        user_id = int(cur.lastrowid)
        cur = c.execute(
            """INSERT INTO student_programs(
                   user_id,study_goal,subject,custom_hourly_rate,is_primary,
                   active,approval_status,created_by,created_at
               ) VALUES(?,?,?,?,1,1,'APPROVED','RC_SELFTEST',?)""",
            (user_id, "EGE", "PHYSICS", 1800, ts),
        )
        program_id = int(cur.lastrowid)
        c.commit()
    finally:
        c.close()

    # Payment confirmation must be safely retryable. EGE defaults to 90-minute
    # package units, so 2700 rubles per unit represents an 1800/hour tariff.
    payment_id = database.create_payment(
        user_id=user_id,
        study_goal="EGE",
        subject="PHYSICS",
        lessons_count=2,
        price_per_lesson=2700,
        program_id=program_id,
    )
    package_id = int(database.approve_payment(payment_id))
    retry_package_id = int(database.approve_payment(payment_id))
    assert retry_package_id == package_id

    c = database.connect()
    try:
        packages = c.execute(
            "SELECT * FROM lesson_packages WHERE payment_id=? ORDER BY id",
            (payment_id,),
        ).fetchall()
    finally:
        c.close()
    assert len(packages) == 1
    assert int(packages[0]["minutes_total"] or 0) == 180
    assert int(packages[0]["minutes_used"] or 0) == 0
    assert int(packages[0]["hourly_rate"] or 0) == 1800

    # Reproduce the onboarding materialization state: it deliberately inserts
    # PENDING regular schedules as inactive until the teacher approves them.
    lesson_day = (datetime.now() + timedelta(days=7)).date()
    schedule_id = int(
        database.create_regular_schedule_request(
            user_id,
            "EGE",
            "PHYSICS",
            lesson_day.weekday(),
            "16:00",
            60,
            lesson_day.isoformat(),
            lesson_day.isoformat(),
            program_id=program_id,
        )
    )
    c = database.connect()
    try:
        c.execute("UPDATE regular_schedules SET active=0 WHERE id=?", (schedule_id,))
        c.commit()
    finally:
        c.close()

    database.approve_regular_schedule_v2(schedule_id)
    approved = database.get_regular_schedule(schedule_id)
    assert approved["status"] == "APPROVED"
    assert int(approved["active"] or 0) == 1
    assert any(int(r["id"]) == schedule_id for r in database.get_active_regular_schedules())

    generation = database.generate_regular_lessons(schedule_id)
    assert generation["created_count"] == 1, generation
    lesson_id = int(generation["created"][0])
    lesson = database.get_lesson(lesson_id)
    assert lesson["lesson_status"] == "CONFIRMED"
    assert lesson["payment_status"] == "RESERVED_BALANCE"
    assert int(lesson["charged"] or 0) == 1
    assert int(lesson["reserved_minutes"] or 0) == 60
    assert int(lesson["reserved_paid_minutes"] or 0) == 60

    c = database.connect()
    try:
        used = int(c.execute(
            "SELECT minutes_used FROM lesson_packages WHERE id=?",
            (package_id,),
        ).fetchone()["minutes_used"])
        charge_rows = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0",
            (lesson_id,),
        ).fetchone()["n"])
    finally:
        c.close()
    assert used == 60
    assert charge_rows > 0

    # Telemost precreation must not create conferences for unpaid individual
    # lessons, while admitted lessons in the same time window remain eligible.
    now = datetime.now()
    unpaid_start = now + timedelta(minutes=30)
    unpaid_end = unpaid_start + timedelta(minutes=60)
    unpaid_id = int(
        database.create_admin_lesson(
            user_id=user_id,
            study_goal="EGE",
            subject="PHYSICS",
            start_time=unpaid_start.isoformat(),
            end_time=unpaid_end.isoformat(),
            duration_minutes=60,
            hourly_rate=1800,
            price=1800,
            payment_mode="AWAITING_PAYMENT",
            force=True,
        )
    )

    paid_start = now + timedelta(minutes=40)
    paid_end = paid_start + timedelta(minutes=60)
    paid_id = int(
        database.create_admin_lesson(
            user_id=user_id,
            study_goal="EGE",
            subject="PHYSICS",
            start_time=paid_start.isoformat(),
            end_time=paid_end.isoformat(),
            duration_minutes=60,
            hourly_rate=1800,
            price=1800,
            payment_mode="FREE",
            force=True,
        )
    )

    called = []
    original = telemost_precreate_worker.ensure_individual_conference
    try:
        def fake_ensure(lid):
            called.append(int(lid))
            return {"status": "ok", "conference_id": f"rc-{lid}", "join_url": "https://telemost.yandex.ru/j/rc", "reused": False}
        telemost_precreate_worker.ensure_individual_conference = fake_ensure
        lo = now - timedelta(minutes=1)
        hi = now + timedelta(minutes=60)
        telemost_precreate_worker._prepare_individual(lo, hi)
    finally:
        telemost_precreate_worker.ensure_individual_conference = original

    assert unpaid_id not in called
    assert paid_id in called

    print("RC RELEASE SELFTEST: OK")
    print(
        f"payment={payment_id} package={package_id} schedule={schedule_id} "
        f"lesson={lesson_id} used_minutes={used} telemost_paid={paid_id}"
    )
finally:
    database.set_test_mode(False)
    database.TEST_DATA_DIR, database.TEST_DB_NAME = old_dir, old_db
    shutil.rmtree(root, ignore_errors=True)
