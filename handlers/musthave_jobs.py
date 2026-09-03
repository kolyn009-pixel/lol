from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

from core import admin_roles
from automation import schedule_tools

import database


def _admins():
    try:
        return [
            int(r["telegram_id"])
            for r in admin_roles.list_admins()
            if r["active"]
        ]
    except Exception:
        return []


def _timezone():
    name = database.get_setting(
        "bot_timezone",
        "Europe/Samara",
    ) or "Europe/Samara"

    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Samara")


def _today_iso():
    return datetime.now(_timezone()).date().isoformat()


def _weekly_text():
    c = database.connect()

    try:
        done = c.execute("""
            SELECT COUNT(*)
            FROM lessons
            WHERE finished_at IS NOT NULL
              AND datetime(finished_at)>=datetime('now','-7 days')
        """).fetchone()[0]

        cancelled = c.execute("""
            SELECT COUNT(*)
            FROM lessons
            WHERE cancelled_at IS NOT NULL
              AND datetime(cancelled_at)>=datetime('now','-7 days')
        """).fetchone()[0]

        unpaid = c.execute("""
            SELECT COUNT(*), COALESCE(SUM(l.price),0)
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
        """).fetchone()

        active = c.execute("""
            SELECT COUNT(*)
            FROM users
            WHERE active=1
        """).fetchone()[0]

        msgs = 0

        try:
            msgs = c.execute("""
                SELECT COUNT(*)
                FROM crm_student_messages
                WHERE direction='IN'
                  AND datetime(created_at)>=datetime('now','-7 days')
            """).fetchone()[0]
        except Exception:
            pass

    finally:
        c.close()

    return (
        "💜 АДЕЛИЯ • НЕДЕЛЯ\n\n"
        "Я собрала короткий итог за последние 7 дней.\n\n"
        f"✅ Проведено занятий: {done}\n"
        f"❌ Отменено: {cancelled}\n"
        f"💬 Входящих сообщений: {msgs}\n"
        f"💳 Ближайших занятий ждут оплаты: {int(unpaid[0] or 0)} · "
        f"{int(unpaid[1] or 0):,} ₽\n"
        f"👥 Активных учеников: {active}\n\n"
        "Если хотите разобраться подробнее — откройте "
        "«Требует внимания» или «Долги и оплаты»."
    ).replace(",", " ")


def _active_students():
    c = database.connect()

    try:
        return c.execute("""
            SELECT
                id,
                name,
                grade,
                telegram_id,
                telegram_username,
                COALESCE(trial_used,0) AS trial_used
            FROM users
            WHERE active=1
              AND telegram_id IS NOT NULL
            ORDER BY grade, name COLLATE NOCASE
        """).fetchall()
    finally:
        c.close()


def _attention_reasons_v2(student_id):
    uid = int(student_id)
    reasons = []
    today = _today_iso()

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

        if not upcoming and not schedule_tools.is_paused(uid, today):
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


def _today_dashboard_v2():
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
            SELECT
                u.id AS user_id,
                l.payment_status
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
        unpaid = sum(
            1 for r in nearest
            if str(r["payment_status"]) == "AWAITING_PAYMENT"
        )

        students = c.execute(
            "SELECT id,name FROM users WHERE active=1 ORDER BY name"
        ).fetchall()
    finally:
        c.close()

    attention = []
    for u in students:
        rs = _attention_reasons_v2(u["id"])
        if rs:
            attention.append((u["id"], u["name"], rs))

    return {
        "lessons": lessons,
        "open_messages": int(open_msgs or 0),
        "unpaid": int(unpaid),
        "attention": attention,
    }


def _debts_v2(limit=40):
    c = database.connect()
    try:
        return c.execute("""
            SELECT
                u.id,
                u.name,
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


def _recent_students_active(admin_id, limit=5):
    from ux_final import schema as ux_schema
    ux_schema.initialize()
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


def _pinned_students_active(admin_id, limit=10):
    from ux_final import schema as ux_schema
    ux_schema.initialize()
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


async def _ensure_google_event_v2(lesson_id):
    """Keep every future confirmed lesson in Google Calendar, paid or not."""
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
        event_id = await asyncio.to_thread(
            runtime.create_google_event,
            user,
            lesson,
        )
        runtime.save_google_event_id(int(lesson_id), event_id)
        print("GOOGLE CALENDAR CREATED V2:", lesson_id, event_id)
        return event_id
    except Exception as exc:
        print("GOOGLE CALENDAR CREATE V2 ERROR:", lesson_id, repr(exc))
        return None


async def _sync_google_calendar_v2(application=None):
    """Calendar status follows the lesson itself, not its payment status."""
    import __main__ as runtime

    now_iso = datetime.now(runtime.TIMEZONE).isoformat()
    c = database.connect()
    try:
        stale_rows = c.execute("""
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

        missing_rows = c.execute("""
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

    for row in stale_rows:
        try:
            ok = await asyncio.to_thread(
                runtime.delete_google_event,
                row["google_event_id"],
            )
            if ok:
                runtime.save_google_event_id(row["id"], None)
                deleted += 1
        except Exception as exc:
            print("GOOGLE CALENDAR CLEANUP V2 ERROR:", row["id"], repr(exc))

    for row in missing_rows:
        if await _ensure_google_event_v2(row["id"]):
            created += 1

    if created or deleted:
        print("GOOGLE CALENDAR SYNC V2:", f"created={created}", f"deleted={deleted}")

    return {"created": created, "deleted": deleted}


def _install_runtime_patches():
    """Install compatibility-safe business rules without touching production data."""
    try:
        from crm_plus import service as crm_service
        crm_service.attention_reasons = _attention_reasons_v2
        crm_service.today_dashboard = _today_dashboard_v2
    except Exception as exc:
        print("ADELIA PATCH CRM ERROR:", repr(exc))

    try:
        from handlers import musthave_admin
        musthave_admin._debts = _debts_v2
    except Exception as exc:
        print("ADELIA PATCH DEBTS ERROR:", repr(exc))

    try:
        from ux_final import service as ux_service
        ux_service.recent_students = _recent_students_active
        ux_service.pinned_students = _pinned_students_active
    except Exception as exc:
        print("ADELIA PATCH STUDENT LISTS ERROR:", repr(exc))

    try:
        import __main__ as runtime
        if hasattr(runtime, "create_google_event") and hasattr(runtime, "save_google_event_id"):
            runtime.ensure_google_event = _ensure_google_event_v2
            runtime.sync_google_calendar = _sync_google_calendar_v2
    except Exception as exc:
        print("ADELIA PATCH GOOGLE ERROR:", repr(exc))


async def regular_series_sync_job(context):
    """Fill approved permanent schedules through their actual end_date."""
    import __main__ as runtime

    today = _today_iso()
    c = database.connect()
    try:
        schedules = c.execute("""
            SELECT id,end_date
            FROM regular_schedules
            WHERE status='APPROVED'
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

        created_ids = list(result.get("created") or [])
        total_created += len(created_ids)

        for lesson_id in created_ids:
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
        await _sync_google_calendar_v2(context.application)
    except Exception as exc:
        print("REGULAR SERIES CALENDAR ERROR:", repr(exc))

    if total_created:
        print("REGULAR SERIES FULL SYNC:", f"created={total_created}")


async def weekly_booking_reminders(context):
    enabled = str(
        database.get_setting(
            "weekly_booking_reminder_enabled",
            "1",
        )
    ).lower()

    if enabled in ("0", "false", "off", "no"):
        return

    today = _today_iso()

    sent = 0
    paused_count = 0
    future_count = 0
    blocked = []
    errors = 0

    for student in _active_students():
        uid = int(student["id"])
        tid = int(student["telegram_id"])

        try:
            if schedule_tools.is_paused(uid, today):
                paused_count += 1
                continue

            if database.get_upcoming_lessons(uid):
                future_count += 1
                continue

            name = student["name"] or "Привет"
            trial_available = not bool(int(student["trial_used"] or 0))

            if trial_available:
                text = (
                    f"💜 {name}, привет!\n\n"
                    "Я посмотрела расписание и пока не вижу следующего занятия.\n\n"
                    "У тебя ещё доступно пробное занятие — можно выбрать удобную дату и познакомиться с форматом 👇"
                )
                button = "🎁 Записаться на пробное"
            else:
                text = (
                    f"💜 {name}, привет!\n\n"
                    "Я посмотрела твоё расписание и пока не вижу следующего занятия.\n\n"
                    "Чтобы не выпадать из подготовки, можешь заранее выбрать удобную дату и время 👇"
                )
                button = "📅 Записаться"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(button, callback_data="booking")],
                [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
            ])

            await context.bot.send_message(
                chat_id=tid,
                text=text,
                reply_markup=keyboard,
            )

            database.log_automation_delivery(
                "weekly_booking_reminder",
                "OK",
                "STUDENT",
                uid,
            )

            sent += 1

        except Forbidden as exc:
            if "blocked by the user" in str(exc).lower():
                database.set_user_active(uid, False)

                username = str(
                    student["telegram_username"] or ""
                ).strip().lstrip("@")

                blocked.append(
                    f"• {student['name'] or 'Без имени'}"
                    + (f" — @{username}" if username else " — ник не указан")
                )

                database.log_automation_delivery(
                    "weekly_booking_reminder",
                    "SKIPPED",
                    "STUDENT",
                    uid,
                    "BOT_BLOCKED",
                )
            else:
                errors += 1
                database.log_automation_delivery(
                    "weekly_booking_reminder",
                    "ERROR",
                    "STUDENT",
                    uid,
                    repr(exc),
                )

        except Exception as exc:
            errors += 1
            database.log_automation_delivery(
                "weekly_booking_reminder",
                "ERROR",
                "STUDENT",
                uid,
                repr(exc),
            )

    database.set_setting(
        "weekly_booking_reminder_last_stats",
        (
            f"sent={sent};"
            f"future={future_count};"
            f"pause={paused_count};"
            f"blocked={len(blocked)};"
            f"errors={errors}"
        ),
    )

    if blocked:
        text = (
            "🚫 АДЕЛИЯ • БЛОКИРОВКИ\n\n"
            f"Новых блокировок обнаружено: {len(blocked)}\n\n"
            + "\n".join(blocked)
            + "\n\n"
            "Я убрала их из активных учеников. "
            "В количестве по классам они больше не учитываются."
        )

        for aid in _admins():
            try:
                await context.bot.send_message(aid, text)
            except Exception:
                pass


async def weekly_job(context):
    if str(
        database.get_setting(
            "notify_weekly",
            "1",
        )
    ).lower() in ("0", "false", "off", "no"):
        return

    text = _weekly_text()

    for aid in _admins():
        try:
            await context.bot.send_message(aid, text)
            database.log_automation_delivery(
                "weekly_summary",
                "OK",
                "ADMIN",
                aid,
            )
        except Exception as exc:
            database.log_automation_delivery(
                "weekly_summary",
                "ERROR",
                "ADMIN",
                aid,
                repr(exc),
            )


async def weekly_dispatcher(context):
    if str(
        database.get_setting(
            "notify_weekly",
            "1",
        )
    ).lower() in ("0", "false", "off", "no"):
        return

    now = datetime.now(_timezone())

    if now.weekday() != 0:
        return

    target = database.get_setting(
        "weekly_summary_time",
        "09:00",
    ) or "09:00"

    if now.strftime("%H:%M") != target:
        return

    day = now.date().isoformat()

    if (
        database.get_setting(
            "weekly_summary_last_day",
            "",
        ) or ""
    ) == day:
        return

    await weekly_job(context)
    await weekly_booking_reminders(context)

    database.set_setting(
        "weekly_summary_last_day",
        day,
    )


def register(application):
    _install_runtime_patches()

    jq = application.job_queue
    if not jq:
        return

    jq.run_repeating(
        weekly_dispatcher,
        interval=60,
        first=20,
        name="adelia_weekly_dispatcher",
    )

    # Heal existing permanent series shortly after startup and then keep them
    # filled through the student's real end_date. This also repairs Google
    # Calendar for already-created AWAITING_PAYMENT lessons.
    jq.run_repeating(
        regular_series_sync_job,
        interval=6 * 60 * 60,
        first=45,
        name="adelia_regular_full_sync",
    )
