from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import database
from automation import schedule_tools


def _tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Samara")


def _today_iso():
    return datetime.now(_tz()).date().isoformat()


def attention_reasons(student_id):
    uid = int(student_id)
    reasons = []
    c = database.connect()
    try:
        upcoming = c.execute("""
            SELECT id
            FROM lessons
            WHERE user_id=?
              AND cancelled_at IS NULL
              AND finished_at IS NULL
              AND lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
              AND datetime(start_time)>=datetime('now')
            ORDER BY datetime(start_time)
            LIMIT 1
        """, (uid,)).fetchone()
        if not upcoming and not schedule_tools.is_paused(uid, _today_iso()):
            reasons.append("Нет следующего занятия")
        try:
            hw = c.execute("""
                SELECT COUNT(*) n
                FROM homework
                WHERE user_id=?
                  AND status IN ('ASSIGNED','REVISION')
                  AND deadline IS NOT NULL
                  AND datetime(deadline)<datetime('now')
            """, (uid,)).fetchone()["n"]
            if hw:
                reasons.append(f"Просрочено ДЗ: {int(hw)}")
        except Exception:
            pass
    finally:
        c.close()
    return reasons


def today_dashboard():
    c = database.connect()
    try:
        lessons = c.execute("""
            SELECT l.id,l.user_id,l.start_time,l.duration_minutes,u.name
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE date(l.start_time)=date('now','localtime')
              AND l.cancelled_at IS NULL
              AND u.active=1
            ORDER BY datetime(l.start_time)
        """).fetchall()
        open_msgs = c.execute(
            "SELECT COUNT(*) n FROM teacher_inbox WHERE status='OPEN'"
        ).fetchone()["n"]
        nearest = c.execute("""
            SELECT l.payment_status
            FROM users u
            JOIN lessons l
              ON l.id = (
                  SELECT l2.id
                  FROM lessons l2
                  WHERE l2.user_id=u.id
                    AND l2.lesson_status='CONFIRMED'
                    AND l2.cancelled_at IS NULL
                    AND datetime(l2.start_time)>=datetime('now')
                  ORDER BY datetime(l2.start_time)
                  LIMIT 1
              )
            WHERE u.active=1
        """).fetchall()
        unpaid = sum(1 for r in nearest if r["payment_status"] == "AWAITING_PAYMENT")
        students = c.execute(
            "SELECT id,name FROM users WHERE active=1 ORDER BY name"
        ).fetchall()
    finally:
        c.close()

    attention = []
    for u in students:
        rs = attention_reasons(u["id"])
        if rs:
            attention.append((u["id"], u["name"], rs))
    return {
        "lessons": lessons,
        "open_messages": int(open_msgs or 0),
        "unpaid": int(unpaid),
        "attention": attention,
    }


def debts(limit=40):
    c = database.connect()
    try:
        return c.execute("""
            SELECT
                u.id,u.name,
                1 AS cnt,
                COALESCE(l.price,0) AS amount,
                l.start_time AS since
            FROM users u
            JOIN lessons l
              ON l.id = (
                  SELECT l2.id
                  FROM lessons l2
                  WHERE l2.user_id=u.id
                    AND l2.lesson_status='CONFIRMED'
                    AND l2.cancelled_at IS NULL
                    AND datetime(l2.start_time)>=datetime('now')
                  ORDER BY datetime(l2.start_time)
                  LIMIT 1
              )
            WHERE u.active=1
              AND l.payment_status='AWAITING_PAYMENT'
            ORDER BY datetime(l.start_time)
            LIMIT ?
        """, (int(limit),)).fetchall()
    finally:
        c.close()


def recent_students(admin_id, limit=5):
    from ux_final import schema
    schema.initialize()
    c = database.connect()
    try:
        return c.execute("""
            SELECT u.id,u.name,u.grade,u.active
            FROM admin_recent_students r
            JOIN users u ON u.id=r.student_id
            WHERE r.admin_id=? AND u.active=1
            ORDER BY r.opened_at DESC
            LIMIT ?
        """, (int(admin_id), int(limit))).fetchall()
    finally:
        c.close()


def pinned_students(admin_id, limit=10):
    from ux_final import schema
    schema.initialize()
    c = database.connect()
    try:
        return c.execute("""
            SELECT u.id,u.name,u.grade,u.active
            FROM admin_pinned_students p
            JOIN users u ON u.id=p.student_id
            WHERE p.admin_id=? AND u.active=1
            ORDER BY p.created_at DESC
            LIMIT ?
        """, (int(admin_id), int(limit))).fetchall()
    finally:
        c.close()


async def ensure_google_event(lesson_id):
    import __main__ as runtime

    lesson = database.get_lesson(int(lesson_id))
    if lesson is None or lesson["lesson_status"] != "CONFIRMED":
        return None
    user = database.get_user(lesson["user_id"])
    if user is None or not user["active"]:
        return None
    if lesson["google_event_id"]:
        return lesson["google_event_id"]

    try:
        event_id = await asyncio.to_thread(runtime.create_google_event, user, lesson)
        runtime.save_google_event_id(int(lesson_id), event_id)
        return event_id
    except Exception as exc:
        print("GOOGLE CALENDAR CREATE V2 ERROR:", lesson_id, repr(exc))
        return None


async def sync_google_calendar(application=None):
    import __main__ as runtime

    now_iso = datetime.now(runtime.TIMEZONE).isoformat()
    c = database.connect()
    try:
        stale = c.execute("""
            SELECT DISTINCT l.id,l.google_event_id
            FROM lessons l
            LEFT JOIN pending_reschedules pr
              ON pr.lesson_id=l.id AND pr.status='PENDING'
            LEFT JOIN users u ON u.id=l.user_id
            WHERE l.google_event_id IS NOT NULL
              AND l.google_event_id!=''
              AND (
                    l.lesson_status!='CONFIRMED'
                    OR pr.id IS NOT NULL
                    OR COALESCE(u.active,0)!=1
              )
        """).fetchall()
        missing = c.execute("""
            SELECT l.id
            FROM lessons l
            JOIN users u ON u.id=l.user_id AND u.active=1
            LEFT JOIN pending_reschedules pr
              ON pr.lesson_id=l.id AND pr.status='PENDING'
            WHERE l.lesson_status='CONFIRMED'
              AND l.start_time>?
              AND pr.id IS NULL
              AND (l.google_event_id IS NULL OR l.google_event_id='')
            ORDER BY l.start_time
        """, (now_iso,)).fetchall()
    finally:
        c.close()

    deleted = 0
    created = 0
    for row in stale:
        try:
            if await asyncio.to_thread(runtime.delete_google_event, row["google_event_id"]):
                runtime.save_google_event_id(row["id"], None)
                deleted += 1
        except Exception as exc:
            print("GOOGLE CALENDAR CLEANUP V2 ERROR:", row["id"], repr(exc))
    for row in missing:
        if await ensure_google_event(row["id"]):
            created += 1
    if created or deleted:
        print("GOOGLE CALENDAR SYNC V2:", f"created={created}", f"deleted={deleted}")
    return {"created": created, "deleted": deleted}


async def regular_series_sync_job(context):
    import __main__ as runtime

    today = _today_iso()
    c = database.connect()
    try:
        schedules = c.execute("""
            SELECT id,end_date
            FROM regular_schedules
            WHERE active=1
              AND status='APPROVED'
              AND end_date IS NOT NULL
              AND date(end_date)>=date(?)
            ORDER BY id
        """, (today,)).fetchall()
    finally:
        c.close()

    total_created = 0
    for schedule in schedules:
        try:
            result = database.generate_regular_lessons(
                int(schedule["id"]),
                until_date=str(schedule["end_date"]),
            )
        except Exception as exc:
            print("REGULAR SERIES FULL SYNC ERROR:", schedule["id"], repr(exc))
            continue

        created = list(result.get("created") or [])
        total_created += len(created)
        for lesson_id in created:
            lesson = database.get_lesson(int(lesson_id))
            if not lesson:
                continue
            try:
                if lesson["payment_status"] == "AWAITING_PAYMENT":
                    runtime.schedule_payment_reminders(context.application, int(lesson_id))
                else:
                    runtime.schedule_lesson_reminders(context.application, int(lesson_id))
            except Exception as exc:
                print("REGULAR SERIES REMINDER ERROR:", lesson_id, repr(exc))

    try:
        await sync_google_calendar(context.application)
    except Exception as exc:
        print("REGULAR SERIES CALENDAR ERROR:", repr(exc))

    if total_created:
        print("REGULAR SERIES FULL SYNC:", f"created={total_created}")


def install(application):
    from crm_plus import service as crm_service
    from handlers import musthave_admin
    from ux_final import service as ux_service

    crm_service.attention_reasons = attention_reasons
    crm_service.today_dashboard = today_dashboard
    musthave_admin._debts = debts
    ux_service.recent_students = recent_students
    ux_service.pinned_students = pinned_students

    try:
        import __main__ as runtime
        if hasattr(runtime, "create_google_event") and hasattr(runtime, "save_google_event_id"):
            runtime.ensure_google_event = ensure_google_event
            runtime.sync_google_calendar = sync_google_calendar
    except Exception as exc:
        print("ADELIA PATCH GOOGLE ERROR:", repr(exc))
