from __future__ import annotations

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
            SELECT COUNT(*), COALESCE(SUM(price),0)
            FROM lessons
            WHERE lesson_status='CONFIRMED'
              AND payment_status='AWAITING_PAYMENT'
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
        f"💳 Неоплаченных сейчас: {int(unpaid[0] or 0)} · "
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
                telegram_username
            FROM users
            WHERE active=1
              AND telegram_id IS NOT NULL
            ORDER BY grade, name COLLATE NOCASE
        """).fetchall()
    finally:
        c.close()


async def weekly_booking_reminders(context):
    enabled = str(
        database.get_setting(
            "weekly_booking_reminder_enabled",
            "1",
        )
    ).lower()

    if enabled in ("0", "false", "off", "no"):
        return

    today = datetime.now(_timezone()).date().isoformat()

    sent = 0
    paused_count = 0
    future_count = 0
    blocked = []
    errors = 0

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📅 Записаться",
                callback_data="booking",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Главная",
                callback_data="global_home",
            )
        ],
    ])

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

            text = (
                f"💜 {name}, привет!\n\n"
                "Я посмотрела твоё расписание и пока не вижу "
                "следующего занятия.\n\n"
                "Чтобы не выпадать из подготовки, можешь заранее "
                "выбрать удобную дату и время 👇"
            )

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
                    + (
                        f" — @{username}"
                        if username
                        else " — ник не указан"
                    )
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
                await context.bot.send_message(
                    aid,
                    text,
                )
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

    # Понедельник.
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
    jq = application.job_queue

    if not jq:
        return

    jq.run_repeating(
        weekly_dispatcher,
        interval=60,
        first=20,
        name="adelia_weekly_dispatcher",
    )
