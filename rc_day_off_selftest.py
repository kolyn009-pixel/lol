from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta

import database
from core import minute_balance
from web_backend import student_self_service, teacher_day_off_state

root = tempfile.mkdtemp(prefix="adelia_rc_day_off_")
db_path = os.path.join(root, "day_off.db")
old_dir, old_db = database.TEST_DATA_DIR, database.TEST_DB_NAME
database.TEST_DATA_DIR, database.TEST_DB_NAME = root, db_path
database.set_test_mode(True)

try:
    database.create_tables()
    minute_balance.ensure_schema()
    teacher_day_off_state.ensure_schema()

    now = datetime.now()
    old_start = now + timedelta(minutes=75)
    old_end = old_start + timedelta(minutes=60)
    new_start = now + timedelta(days=1, hours=3)
    new_end = new_start + timedelta(minutes=60)
    ts = database.now_iso()

    c = database.connect()
    try:
        cur = c.execute(
            """INSERT INTO users(name,grade,study_goal,main_subject,created_at)
               VALUES(?,?,?,?,?)""",
            ("RC Day-Off Student", 11, "EGE", "PHYSICS", ts),
        )
        user_id = int(cur.lastrowid)

        cur = c.execute(
            """INSERT INTO payments(
                   user_id,study_goal,subject,payment_type,lessons_count,
                   price_per_lesson,subtotal,discount_percent,
                   package_discount_amount,promo_discount_amount,total_amount,
                   status,created_at,confirmed_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, "EGE", "PHYSICS", "PACKAGE", 2, 1800, 3600, 0, 0, 0, 3600, "PAID", ts, ts),
        )
        payment_id = int(cur.lastrowid)

        cur = c.execute(
            """INSERT INTO lesson_packages(
                   payment_id,user_id,study_goal,subject,lessons_total,lessons_used,
                   price_per_lesson,discount_percent,amount_paid,status,source_type,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (payment_id, user_id, "EGE", "PHYSICS", 2, 0, 1800, 0, 3600, "ACTIVE", "PAID", ts),
        )
        package_id = int(cur.lastrowid)
        c.execute(
            """UPDATE lesson_packages
               SET minutes_total=120,minutes_used=0,hourly_rate=1800
               WHERE id=?""",
            (package_id,),
        )

        cur = c.execute(
            """INSERT INTO lessons(
                   user_id,study_goal,subject,start_time,end_time,duration_minutes,
                   hourly_rate,price,payment_status,payment_id,package_id,
                   lesson_status,charged,is_trial,is_regular,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user_id, "EGE", "PHYSICS", old_start.isoformat(), old_end.isoformat(), 60,
                1800, 1800, "AWAITING_PAYMENT", payment_id, package_id,
                "CONFIRMED", 0, 0, 0, ts,
            ),
        )
        old_lesson_id = int(cur.lastrowid)
        c.commit()
    finally:
        c.close()

    reserved = minute_balance.reserve_minutes(user_id, 1800, 60, old_lesson_id)
    assert reserved == 60

    old = database.get_lesson(old_lesson_id)
    assert int(old["reserved_minutes"] or 0) == 60
    assert int(old["charged"] or 0) == 1
    assert str(old["payment_status"]) == "RESERVED_BALANCE"

    teacher_day_off_state.mark_lesson(old_lesson_id, 9001)
    assert teacher_day_off_state.is_marked(old_lesson_id)

    # The original lesson is less than two hours away. Day-off entitlement must
    # bypass the normal two-hour reschedule cutoff exactly for this marked lesson.
    new_lesson_id = int(
        database.free_reschedule_lesson(
            old_lesson_id,
            new_start.isoformat(),
            new_end.isoformat(),
        )
    )

    old = database.get_lesson(old_lesson_id)
    new = database.get_lesson(new_lesson_id)
    assert str(old["lesson_status"]) == "CANCELLED"
    assert str(old["payment_status"]) == "TRANSFERRED"
    assert int(old["charged"] or 0) == 0
    assert int(new["reserved_minutes"] or 0) == 60
    assert int(new["reserved_paid_minutes"] or 0) == 60
    assert int(new["reserved_bonus_minutes"] or 0) == 0
    assert int(new["charged"] or 0) == 1
    assert str(new["payment_status"]) == "RESERVED_BALANCE"

    # Durable entitlement belongs only to the originally affected lesson.
    teacher_day_off_state.inherit_marker(old_lesson_id, new_lesson_id)
    assert teacher_day_off_state.is_marked(old_lesson_id)
    assert not teacher_day_off_state.is_marked(new_lesson_id)

    c = database.connect()
    try:
        active_old = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0",
            (old_lesson_id,),
        ).fetchone()["n"])
        active_new = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0",
            (new_lesson_id,),
        ).fetchone()["n"])
        used_before_cancel = int(c.execute(
            "SELECT minutes_used FROM lesson_packages WHERE id=?",
            (package_id,),
        ).fetchone()["minutes_used"])
    finally:
        c.close()
    assert active_old == 0
    assert active_new > 0
    assert used_before_cancel == 60

    first = student_self_service.cancel_lesson(user_id, new_lesson_id)
    assert first["status"] == "ok"
    assert first["lesson_status"] == "CANCELLED"
    assert first["teacher_day_off"] is False

    c = database.connect()
    try:
        used_after_first = int(c.execute(
            "SELECT minutes_used FROM lesson_packages WHERE id=?",
            (package_id,),
        ).fetchone()["minutes_used"])
        refunded_rows = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=1",
            (new_lesson_id,),
        ).fetchone()["n"])
        active_rows = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=0",
            (new_lesson_id,),
        ).fetchone()["n"])
    finally:
        c.close()
    assert used_after_first == 0
    assert refunded_rows > 0
    assert active_rows == 0

    second = student_self_service.cancel_lesson(user_id, new_lesson_id)
    assert second["status"] == "ok"
    assert second.get("already_cancelled") is True

    c = database.connect()
    try:
        used_after_retry = int(c.execute(
            "SELECT minutes_used FROM lesson_packages WHERE id=?",
            (package_id,),
        ).fetchone()["minutes_used"])
        refunded_rows_retry = int(c.execute(
            "SELECT COUNT(*) n FROM lesson_minute_charges WHERE lesson_id=? AND refunded=1",
            (new_lesson_id,),
        ).fetchone()["n"])
    finally:
        c.close()
    assert used_after_retry == 0
    assert refunded_rows_retry == refunded_rows

    # A retry of the original reschedule cannot create another replacement.
    try:
        database.free_reschedule_lesson(
            old_lesson_id,
            (new_start + timedelta(days=1)).isoformat(),
            (new_end + timedelta(days=1)).isoformat(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("reschedule retry unexpectedly created another lesson")

    print("RC DAY-OFF SELFTEST: OK")
    print(
        f"old={old_lesson_id} new={new_lesson_id} "
        f"charge_rows={refunded_rows} package_minutes_used={used_after_retry}"
    )
finally:
    database.set_test_mode(False)
    database.TEST_DATA_DIR, database.TEST_DB_NAME = old_dir, old_db
    shutil.rmtree(root, ignore_errors=True)
