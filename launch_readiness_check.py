import os
import sys
import sqlite3
import tempfile
import traceback
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent
SOURCE_DB = ROOT / "tutor.db"

PASS = 0
FAIL = 0
WARN = 0
RESULTS = []


def ok(name, details=""):
    global PASS
    PASS += 1
    RESULTS.append(("PASS", name, details))
    print(f"✅ PASS  {name}" + (f" — {details}" if details else ""))


def fail(name, details=""):
    global FAIL
    FAIL += 1
    RESULTS.append(("FAIL", name, details))
    print(f"❌ FAIL  {name}" + (f" — {details}" if details else ""))


def warn(name, details=""):
    global WARN
    WARN += 1
    RESULTS.append(("WARN", name, details))
    print(f"⚠️ WARN  {name}" + (f" — {details}" if details else ""))


def section(title):
    print()
    print("=" * 68)
    print(title)
    print("=" * 68)


tmpdir = Path(tempfile.mkdtemp(prefix="adelia_launch_readiness_"))
sandbox_db = tmpdir / "tutor.db"

print("=" * 68)
print("ADELIA / TUTORBOT — LAUNCH READINESS CHECK")
print("=" * 68)
print("Sandbox:", tmpdir)
print("Production DB:", SOURCE_DB)
print()


# ============================================================
# 1. SAFE DATABASE SNAPSHOT
# ============================================================

section("1. SAFE SANDBOX")

try:
    src = sqlite3.connect(str(SOURCE_DB))
    dst = sqlite3.connect(str(sandbox_db))
    src.backup(dst)
    dst.close()
    src.close()
    ok("Production DB snapshot")
except Exception as e:
    fail("Production DB snapshot", repr(e))
    sys.exit(1)


# Импортируем только после создания sandbox.
import database

database.DB_NAME = str(sandbox_db)
database.TEST_DATA_DIR = str(tmpdir / "testdata")
database.TEST_DB_NAME = str(tmpdir / "testdata" / "tutor_test.db")
database.set_test_mode(False)

from core import minute_balance

try:
    minute_balance.ensure_schema()
except Exception:
    pass


# ============================================================
# 2. DB INTEGRITY
# ============================================================

section("2. DATABASE INTEGRITY")

try:
    conn = database.connect()

    integrity = conn.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    foreign = conn.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    conn.close()

    if integrity == "ok":
        ok("SQLite integrity_check")
    else:
        fail("SQLite integrity_check", str(integrity))

    if not foreign:
        ok("SQLite foreign_key_check")
    else:
        fail(
            "SQLite foreign_key_check",
            f"{len(foreign)} violation(s)"
        )

except Exception as e:
    fail("Database integrity", repr(e))


# ============================================================
# 3. STATIC CRITICAL BUTTON AUDIT
# ============================================================

section("3. CRITICAL TELEGRAM BUTTON AUDIT")

try:
    bot_text = (ROOT / "bot.py").read_text(
        encoding="utf-8",
        errors="ignore"
    )

    payments_text = (ROOT / "payments.py").read_text(
        encoding="utf-8",
        errors="ignore"
    )

    critical = [
        "single_draft_pay",
        "single_draft_receipt",
        "single_draft_balance",
        "single_draft_subscription",
        "single_draft_cancel",
        "single_draft_change_time",
        "payment_admin_approve",
        "payment_admin_reject",
    ]

    for callback in critical:
        refs = bot_text.count(callback) + payments_text.count(callback)

        if refs >= 2:
            ok(
                f"Callback exists: {callback}",
                f"refs={refs}"
            )
        else:
            fail(
                f"Callback coverage: {callback}",
                f"refs={refs}"
            )

    placeholder = (
        '"single_draft_subscription",'
        in bot_text
        and '"single_draft_balance",'
        in bot_text
        and "Этот способ оплаты подключаем следующим шагом."
        in bot_text
    )

    if placeholder:
        fail(
            "Balance/subscription booking flow",
            "single_draft_balance и single_draft_subscription "
            "сейчас ведут в заглушку"
        )
    else:
        ok("Balance/subscription booking flow")

    receipt_handlers = payments_text.count(
        'if data.startswith("single_draft_receipt|")'
    )

    if receipt_handlers == 1:
        ok(
            "Single-draft receipt handler uniqueness",
            "1 handler"
        )
    else:
        fail(
            "Single-draft receipt handler uniqueness",
            f"handlers={receipt_handlers}"
        )

except Exception as e:
    fail("Static callback audit", repr(e))


# ============================================================
# 4. PICK EXISTING SANDBOX STUDENT + PROGRAM
# ============================================================

section("4. TEST SUBJECT")

user = None
program = None
rate = None
duration = None

try:
    conn = database.connect()

    program = conn.execute(
        """
        SELECT sp.*
        FROM student_programs sp
        JOIN users u ON u.id = sp.user_id
        ORDER BY sp.id
        LIMIT 1
        """
    ).fetchone()

    if program:
        user = conn.execute(
            "SELECT * FROM users WHERE id=?",
            (int(program["user_id"]),)
        ).fetchone()

    conn.close()

    if not user or not program:
        warn(
            "Sandbox student",
            "Нет student_programs — dynamic booking flow пропущен"
        )
    else:
        rate_info = database.get_program_rate_info(
            int(program["id"])
        )

        rate = int(rate_info["effective_rate"])

        try:
            duration = int(
                minute_balance.get_program_duration(
                    int(program["id"])
                )
            )
        except Exception:
            duration = 60

        if duration <= 0:
            duration = 60

        ok(
            "Sandbox student/program selected",
            f"user={user['id']} program={program['id']} "
            f"rate={rate} duration={duration}"
        )

except Exception as e:
    warn("Sandbox student/program selection", repr(e))


# ============================================================
# 5. DIRECT SINGLE LESSON PAYMENT FLOW
# ============================================================

section("5. SINGLE BOOKING → PAYMENT → RECEIPT → APPROVAL")

if user and program and rate:

    try:
        # Далёкая дата, чтобы не конфликтовать с реальным расписанием
        start = datetime(
            2099, 12, 20, 12, 0,
            tzinfo=timezone.utc
        )

        end = start + timedelta(minutes=duration)

        price = int(round(rate * duration / 60))

        before = minute_balance.get_balance(
            int(user["id"]),
            hourly_rate=rate
        )

        draft_id = database.save_booking_draft(
            user_id=int(user["id"]),
            program_id=int(program["id"]),
            study_goal=program["study_goal"],
            subject=program["subject"],
            start_time=start.isoformat(),
            end_time=end.isoformat(),
            duration_minutes=duration,
            hourly_rate=rate,
            price=price,
        )

        draft = database.get_booking_draft(
            draft_id,
            int(user["id"])
        )

        if draft and draft["status"] == "DRAFT":
            ok("Create single booking draft")
        else:
            fail(
                "Create single booking draft",
                str(dict(draft)) if draft else "missing"
            )

        payment_id = database.create_payment(
            user_id=int(user["id"]),
            study_goal=draft["study_goal"],
            subject=draft["subject"],
            lessons_count=1,
            price_per_lesson=int(draft["price"]),
            lesson_id=None,
            minutes_total=int(draft["duration_minutes"]),
            base_duration_minutes=int(draft["duration_minutes"]),
            hourly_rate=int(draft["hourly_rate"]),
            program_id=int(draft["program_id"]),
        )

        database.update_booking_draft(
            draft_id,
            status="PAYMENT_PENDING",
            payment_choice="SINGLE",
            payment_id=payment_id,
        )

        payment = database.get_payment(payment_id)

        if payment and payment["status"] == "WAITING":
            ok("Create direct lesson payment")
        else:
            fail("Create direct lesson payment")

        receipt_id = database.add_receipt(
            payment_id=payment_id,
            user_id=int(user["id"]),
            file_id="SELFTEST_TELEGRAM_FILE",
            file_type="PHOTO",
            source_platform="SELFTEST",
        )

        payment = database.get_payment(payment_id)

        if payment["status"] == "RECEIPT_SENT":
            ok(
                "Attach receipt",
                f"receipt={receipt_id}"
            )
        else:
            fail(
                "Attach receipt",
                f"payment_status={payment['status']}"
            )

        database.update_booking_draft(
            draft_id,
            status="PAYMENT_ATTACHED"
        )

        # Реальный production admin-flow:
        # booking_draft обрабатывается специальным approver,
        # который НЕ начисляет свободные минуты.
        draft_result = (
            database.approve_paid_booking_draft_payment(
                payment_id
            )
        )

        if draft_result is None:
            fail(
                "Approve direct booking payment",
                "booking draft was not detected"
            )
            package_id = None
            lesson_id = None
        else:
            package_id, lesson_id = draft_result

        payment_after_approve = database.get_payment(
            payment_id
        )

        if payment_after_approve["status"] == "PAID":
            ok("Approve payment")
        else:
            fail(
                "Approve payment",
                payment_after_approve["status"]
            )

        if lesson_id:
            ok(
                "Convert paid draft to lesson",
                f"lesson={lesson_id}"
            )
        else:
            fail("Convert paid draft to lesson")

        final_draft = database.get_booking_draft(
            draft_id,
            int(user["id"])
        )

        lesson = (
            database.get_lesson(lesson_id)
            if lesson_id
            else None
        )

        final_payment = database.get_payment(
            payment_id
        )

        after = minute_balance.get_balance(
            int(user["id"]),
            hourly_rate=rate
        )

        if final_draft["status"] == "CONFIRMED":
            ok("Draft final status", "CONFIRMED")
        else:
            fail(
                "Draft final status",
                final_draft["status"]
            )

        if lesson and lesson["lesson_status"] == "CONFIRMED":
            ok("Lesson status", "CONFIRMED")
        else:
            fail(
                "Lesson status",
                lesson["lesson_status"] if lesson else "missing"
            )

        if lesson and lesson["payment_status"] == "PAID":
            ok("Lesson payment status", "PAID")
        else:
            fail(
                "Lesson payment status",
                lesson["payment_status"] if lesson else "missing"
            )

        if (
            final_payment["lesson_id"]
            and int(final_payment["lesson_id"]) == int(lesson_id)
        ):
            ok(
                "Payment linked to created lesson",
                f"lesson_id={lesson_id}"
            )
        else:
            fail(
                "Payment linked to created lesson",
                f"payment.lesson_id={final_payment['lesson_id']}"
            )

        # КРИТИЧЕСКАЯ ПРОВЕРКА:
        # отдельная оплата занятия НЕ должна ещё и подарить
        # ученику новый пакет минут.
        balance_delta = int(after["total"]) - int(before["total"])

        if balance_delta == 0:
            ok(
                "Direct-payment balance isolation",
                "balance unchanged"
            )
        else:
            fail(
                "Direct-payment balance isolation",
                f"до={before['total']} мин, "
                f"после={after['total']} мин, "
                f"delta=+{balance_delta} мин. "
                "Оплата одного занятия одновременно "
                "начисляет минуты на баланс."
            )

        # Повторный finalize не должен создавать дубль.
        # Повторная попытка не должна создавать второй урок.
        # После успешного approve draft уже CONFIRMED, поэтому legacy
        # finalize ничего создавать не должен.
        second_lesson_id = database.confirm_paid_booking_draft(
            payment_id
        )

        conn = database.connect()

        duplicates = conn.execute(
            """
            SELECT COUNT(*)
            FROM lessons
            WHERE user_id=?
              AND start_time=?
              AND end_time=?
            """,
            (
                int(user["id"]),
                start.isoformat(),
                end.isoformat(),
            )
        ).fetchone()[0]

        conn.close()

        if duplicates == 1:
            ok("Duplicate lesson protection")
        else:
            fail(
                "Duplicate lesson protection",
                f"lessons={duplicates}"
            )

    except Exception as e:
        fail(
            "Single booking end-to-end flow",
            f"{type(e).__name__}: {e}"
        )
        traceback.print_exc()


# ============================================================
# 6. MINUTE RESERVATION MODEL
# ============================================================

section("6. MINUTE BALANCE MODEL")

if user and program and rate:

    try:
        # Добавляем бонусы только в sandbox.
        bonus_package = minute_balance.add_bonus_minutes(
            int(user["id"]),
            int(program["id"]),
            duration,
            reason="LAUNCH_READINESS_SELFTEST",
        )

        balance = minute_balance.get_balance(
            int(user["id"]),
            hourly_rate=rate
        )

        if balance["total"] >= duration:
            ok(
                "Credit test minutes",
                f"balance={balance['total']}"
            )
        else:
            fail(
                "Credit test minutes",
                str(balance)
            )

        start2 = datetime(
            2099, 12, 21, 12, 0,
            tzinfo=timezone.utc
        )

        end2 = start2 + timedelta(minutes=duration)

        lesson2 = database.create_lesson_request(
            user_id=int(user["id"]),
            study_goal=program["study_goal"],
            subject=program["subject"],
            start_time=start2.isoformat(),
            end_time=end2.isoformat(),
            duration_minutes=duration,
            hourly_rate=rate,
            price=int(round(rate * duration / 60)),
            is_trial=False,
            program_id=int(program["id"]),
        )

        database.approve_lesson_request(lesson2)

        reserved = database.get_lesson(lesson2)

        if (
            reserved
            and reserved["lesson_status"] == "CONFIRMED"
            and reserved["payment_status"] == "RESERVED_BALANCE"
        ):
            ok(
                "Reserve minutes for approved lesson",
                f"lesson={lesson2}"
            )
        else:
            fail(
                "Reserve minutes for approved lesson",
                str(dict(reserved)) if reserved else "missing"
            )

        balance_after = minute_balance.get_balance(
            int(user["id"]),
            hourly_rate=rate
        )

        if balance_after["total"] <= balance["total"] - duration:
            ok(
                "Minutes consumed/reserved",
                f"{balance['total']} → {balance_after['total']}"
            )
        else:
            fail(
                "Minutes consumed/reserved",
                f"{balance['total']} → {balance_after['total']}"
            )

        refunded = minute_balance.refund_lesson_minutes(
            lesson2
        )

        restored = minute_balance.get_balance(
            int(user["id"]),
            hourly_rate=rate
        )

        if refunded and restored["total"] == balance["total"]:
            ok(
                "Minute refund after cancellation",
                f"restored={restored['total']}"
            )
        else:
            fail(
                "Minute refund after cancellation",
                f"before={balance['total']} "
                f"after={restored['total']} refunded={refunded}"
            )

    except Exception as e:
        fail(
            "Minute balance lifecycle",
            f"{type(e).__name__}: {e}"
        )
        traceback.print_exc()


# ============================================================
# 7. PRODUCTION FILE SAFETY
# ============================================================

section("7. PRODUCTION SAFETY")

try:
    conn = sqlite3.connect(str(SOURCE_DB))

    integrity = conn.execute(
        "PRAGMA integrity_check"
    ).fetchone()[0]

    conn.close()

    if integrity == "ok":
        ok("Production DB still readable")
    else:
        fail(
            "Production DB integrity after test",
            integrity
        )

except Exception as e:
    fail("Production DB safety", repr(e))


# ============================================================
# FINAL REPORT
# ============================================================

section("FINAL RESULT")

print(f"✅ PASS: {PASS}")
print(f"⚠️ WARN: {WARN}")
print(f"❌ FAIL: {FAIL}")
print()

critical_failures = [
    (name, details)
    for status, name, details in RESULTS
    if status == "FAIL"
]

if critical_failures:
    print("BLOCKERS:")
    for name, details in critical_failures:
        print(f"  ❌ {name}")
        if details:
            print(f"     {details}")

    print()
    print("🔴 LAUNCH READINESS: NOT READY")
else:
    print("🟢 LAUNCH READINESS: READY")

print()
print("Sandbox DB:", sandbox_db)
print("Production DB was not modified.")

sys.exit(1 if FAIL else 0)
