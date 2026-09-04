from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
import admin


SUBJECT_NAMES = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}


def initialize():

    c = database.connect()

    try:

        c.execute("""
            CREATE TABLE IF NOT EXISTS
            teacher_lesson_notification_log (

                dedupe_key TEXT PRIMARY KEY,

                sent_at TEXT NOT NULL
            )
        """)

        c.commit()

    finally:

        c.close()


def _claim(key):

    c = database.connect()

    try:

        cur = c.execute("""
            INSERT OR IGNORE INTO
            teacher_lesson_notification_log(
                dedupe_key,
                sent_at
            )

            VALUES (?,?)
        """, (
            str(key),
            database.now_iso(),
        ))

        c.commit()

        return cur.rowcount > 0

    finally:

        c.close()


def _timezone():

    try:

        name = database.get_setting(
            "bot_timezone",
            "Europe/Samara",
        )

    except Exception:

        name = "Europe/Samara"

    try:

        return ZoneInfo(
            str(name or "Europe/Samara")
        )

    except Exception:

        return ZoneInfo(
            "Europe/Samara"
        )


def _dt(raw):

    value = datetime.fromisoformat(
        str(raw)
    )

    tz = _timezone()

    if value.tzinfo is None:

        return value.replace(
            tzinfo=tz
        )

    return value.astimezone(
        tz
    )


def _subject(value):

    raw = str(
        value or ""
    ).upper()

    return SUBJECT_NAMES.get(
        raw,
        raw or "Занятие",
    )


def ending_lessons():

    c = database.connect()

    try:

        return list(
            c.execute("""
                SELECT
                    l.id,
                    l.user_id,
                    l.start_time,
                    l.end_time,
                    l.subject,

                    u.name,
                    u.board_url

                FROM lessons l

                JOIN users u
                  ON u.id=l.user_id

                WHERE
                    l.lesson_status='IN_PROGRESS'

                  AND
                    l.cancelled_at IS NULL

                  AND
                    l.end_time IS NOT NULL

                ORDER BY l.end_time
            """).fetchall()
        )

    finally:

        c.close()


async def job(context):

    initialize()

    now = datetime.now(
        _timezone()
    )

    for lesson in ending_lessons():

        try:

            end = _dt(
                lesson["end_time"]
            )

        except Exception:

            continue

        seconds = (
            end - now
        ).total_seconds()

        # Job идёт каждую минуту.
        # Окно 0–5 минут.
        if not (
            0 <= seconds <= 5 * 60
        ):
            continue

        key = (
            "tg:end5:"
            f"{lesson['id']}:"
            f"{end:%Y%m%d%H%M}"
        )

        if not _claim(key):
            continue

        board = str(
            lesson["board_url"]
            or ""
        ).strip()

        text = (
            "⏳ ДО КОНЦА ЗАНЯТИЯ 5 МИНУТ\n\n"

            f"👤 {lesson['name']}\n"

            f"📖 {_subject(lesson['subject'])}\n"

            f"🕐 По плану до {end:%H:%M}"
        )

        if board:

            text += (
                "\n\n📝 Доска занятия:\n"
                f"{board}"
            )

        text += (
            "\n\nМожно подводить итог "
            "и подготовить домашнее задание."
        )

        rows = []

        if board:

            rows.append([
                InlineKeyboardButton(
                    "📝 Открыть доску",
                    url=board,
                )
            ])

        rows.append([
            InlineKeyboardButton(
                "🏠 Панель преподавателя",
                callback_data="global_home",
            )
        ])

        await context.bot.send_message(
            chat_id=int(admin.ADMIN_ID),
            text=text,
            reply_markup=InlineKeyboardMarkup(
                rows
            ),
        )


def install(application):

    initialize()

    if not application.job_queue:
        return

    existing = {
        job.name
        for job in (
            application
            .job_queue
            .jobs()
        )
    }

    if (
        "teacher_lesson_end5"
        in existing
    ):
        return

    application.job_queue.run_repeating(
        job,
        interval=60,
        first=10,
        name="teacher_lesson_end5",
    )
