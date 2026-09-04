from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
)

from zoneinfo import ZoneInfo

import database

from . import schema


SUBJECT_NAMES = {

    "PHYSICS":
        "Физика",

    "CHEMISTRY":
        "Химия",
}


# ============================================================
# TIMEZONE
# ============================================================

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
            str(
                name
                or "Europe/Samara"
            )
        )

    except Exception:

        return ZoneInfo(
            "Europe/Samara"
        )


def _lesson_dt(
    raw
):

    dt = datetime.fromisoformat(
        str(raw)
    )


    tz = _timezone()


    if dt.tzinfo is None:

        return dt.replace(
            tzinfo=tz
        )


    return dt.astimezone(
        tz
    )


# ============================================================
# DATABASE
# ============================================================

def initialize():

    c = database.connect()

    try:

        c.execute("""
            CREATE TABLE IF NOT EXISTS
            vk_teacher_notification_log (

                dedupe_key TEXT PRIMARY KEY,

                sent_at TEXT NOT NULL
            )
        """)

        c.commit()

    finally:

        c.close()


def _claim(
    key: str
):

    c = database.connect()

    try:

        cur = c.execute("""
            INSERT OR IGNORE
            INTO vk_teacher_notification_log(
                dedupe_key,
                sent_at
            )

            VALUES(
                ?,?
            )
        """, (
            str(key),
            database.now_iso(),
        ))


        c.commit()


        return (
            cur.rowcount
            > 0
        )

    finally:

        c.close()


# ============================================================
# HELPERS
# ============================================================

def _subject(
    value
):

    raw = str(
        value
        or ""
    ).upper()


    return SUBJECT_NAMES.get(
        raw,
        raw or "Занятие",
    )


def _board_line(
    board_url
):

    value = str(
        board_url
        or ""
    ).strip()


    if not value:
        return ""


    return (
        "\n\n📝 Доска занятия:\n"
        f"{value}"
    )


def _confirmed_lessons():

    c = database.connect()

    try:

        return list(
            c.execute("""
                SELECT

                    l.id,
                    l.user_id,
                    l.start_time,
                    l.subject,

                    u.name,
                    u.board_url

                FROM lessons l

                JOIN users u
                  ON u.id=l.user_id

                WHERE
                    l.lesson_status=
                    'CONFIRMED'

                  AND
                    l.cancelled_at
                    IS NULL

                ORDER BY
                    l.start_time

                LIMIT 300
            """).fetchall()
        )

    finally:

        c.close()


def _started_lessons():

    c = database.connect()

    try:

        return list(
            c.execute("""
                SELECT

                    l.id,
                    l.user_id,
                    l.start_time,
                    l.subject,

                    u.name,
                    u.board_url

                FROM lessons l

                JOIN users u
                  ON u.id=l.user_id

                WHERE
                    l.lesson_status=
                    'IN_PROGRESS'

                  AND
                    l.cancelled_at
                    IS NULL

                ORDER BY
                    l.start_time

                LIMIT 100
            """).fetchall()
        )

    finally:

        c.close()


# ============================================================
# BEFORE LESSON
# ============================================================

def _send_before(
    peers,
    send_teacher,
):

    now = datetime.now(
        _timezone()
    )


    sent = 0


    for lesson in (
        _confirmed_lessons()
    ):

        try:

            start = _lesson_dt(
                lesson[
                    "start_time"
                ]
            )

        except Exception:

            continue


        seconds = (
            start - now
        ).total_seconds()


        # ================================================
        # 20 MINUTES
        # ================================================

        if (
            15 * 60
            <= seconds
            <= 20 * 60
        ):

            key = (
                "lesson20:"
                f"{lesson['id']}:"
                f"{start:%Y%m%d%H%M}"
            )


            if _claim(key):

                text = (
                    "⏰ ЗАНЯТИЕ ЧЕРЕЗ 20 МИНУТ\n\n"

                    f"👤 {lesson['name']}\n"

                    f"📖 "
                    f"{_subject(lesson['subject'])}\n"

                    f"🕐 {start:%H:%M}"

                    f"{_board_line(lesson['board_url'])}"

                    "\n\nОткрой «📅 Сегодня», "
                    "чтобы отправить ученику "
                    "ссылку на занятие или ДЗ."
                )


                for peer in peers:

                    send_teacher(
                        int(peer),
                        text,
                    )

                    sent += 1


        # ================================================
        # 5 MINUTES
        # ================================================

        if (
            0
            <= seconds
            <= 5 * 60
        ):

            key = (
                "lesson5:"
                f"{lesson['id']}:"
                f"{start:%Y%m%d%H%M}"
            )


            if _claim(key):

                text = (
                    "🔔 ЗАНЯТИЕ ЧЕРЕЗ 5 МИНУТ\n\n"

                    f"👤 {lesson['name']}\n"

                    f"📖 "
                    f"{_subject(lesson['subject'])}\n"

                    f"🕐 {start:%H:%M}"

                    f"{_board_line(lesson['board_url'])}"

                    "\n\nПора отправить ученику "
                    "ссылку на подключение 💜"
                )


                for peer in peers:

                    send_teacher(
                        int(peer),
                        text,
                    )

                    sent += 1


    return sent


# ============================================================
# LESSON START
# ============================================================

def _send_started(
    peers,
    send_teacher,
):

    sent = 0


    for lesson in (
        _started_lessons()
    ):

        key = (
            "lesson_started:"
            f"{lesson['id']}"
        )


        if not _claim(
            key
        ):

            continue


        try:

            start = _lesson_dt(
                lesson[
                    "start_time"
                ]
            )

            time_text = (
                f"{start:%H:%M}"
            )

        except Exception:

            time_text = str(
                lesson[
                    "start_time"
                ]
            )


        text = (
            "▶️ ЗАНЯТИЕ НАЧАЛОСЬ\n\n"

            f"👤 {lesson['name']}\n"

            f"📖 "
            f"{_subject(lesson['subject'])}\n"

            f"🕐 {time_text}"

            f"{_board_line(lesson['board_url'])}"

            "\n\nЗанятие переведено "
            "в статус «идёт»."
        )


        for peer in peers:

            send_teacher(
                int(peer),
                text,
            )

            sent += 1


    return sent


# ============================================================
# ENDING SOON
# ============================================================

def _ending_lessons():

    c = database.connect()

    try:

        return list(
            c.execute("""
                SELECT

                    l.id,
                    l.user_id,

                    l.start_time,
                    l.end_time,
                    l.started_at,
                    l.duration_minutes,

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
                    l.started_at IS NOT NULL

                  AND
                    l.end_time IS NOT NULL

                ORDER BY l.end_time
            """).fetchall()
        )

    finally:

        c.close()


def _send_ending(
    peers,
    send_teacher,
):

    now = datetime.now(
        _timezone()
    )

    sent = 0

    for lesson in _ending_lessons():

        try:

            plan_start = _lesson_dt(
                lesson["start_time"]
            )

            plan_end = _lesson_dt(
                lesson["end_time"]
            )

            actual_start = _lesson_dt(
                lesson["started_at"]
            )

            duration = int(
                lesson["duration_minutes"]
                or round(
                    (
                        plan_end
                        - plan_start
                    ).total_seconds()
                    / 60
                )
            )

            from datetime import timedelta

            actual_end = (
                actual_start
                + timedelta(
                    minutes=duration
                )
            )

        except Exception:

            continue

        delta = round(
            (
                actual_start
                - plan_start
            ).total_seconds()
            / 60
        )

        late = max(
            delta,
            0,
        )

        early = max(
            -delta,
            0,
        )

        notification_end = (
            actual_end
            if actual_start < plan_start
            else plan_end
        )

        seconds = (
            notification_end
            - now
        ).total_seconds()

        if not (
            0 <= seconds <= 5 * 60
        ):

            continue

        key = (
            "lesson_smart_end5:"
            f"{lesson['id']}:"
            f"{notification_end:%Y%m%d%H%M}"
        )

        if not _claim(
            key
        ):

            continue

        text = (
            "⏳ ДО КОНЦА ЗАНЯТИЯ 5 МИНУТ\n\n"
            f"👤 {lesson['name']}\n"
            f"📖 {_subject(lesson['subject'])}\n\n"
            f"📅 План: "
            f"{plan_start:%H:%M}"
            "–"
            f"{plan_end:%H:%M}\n"
            f"▶️ Фактически начали: "
            f"{actual_start:%H:%M}\n"
        )

        if early:

            text += (
                f"⏹ Полное время закончится: "
                f"{actual_end:%H:%M}\n"
                f"✅ Начали раньше на "
                f"{early} мин."
            )

        elif late:

            text += (
                f"🕐 По расписанию до: "
                f"{plan_end:%H:%M}\n"
                f"⏱ Полные {duration} минут: "
                f"до {actual_end:%H:%M}\n"
                f"⚠️ Нужно задержаться на "
                f"{late} мин."
            )

        else:

            text += (
                f"⏹ Окончание: "
                f"{plan_end:%H:%M}"
            )

        text += _board_line(
            lesson["board_url"]
        )

        text += (
            "\n\nВ Telegram доступны быстрые действия: "
            "завершить сейчас, завершить по расписанию "
            "и подтвердить предупреждение следующему ученику."
        )

        for peer in peers:

            send_teacher(
                int(peer),
                text,
            )

            sent += 1

    return sent


# ============================================================
# TICK
# ============================================================

def tick(
    send_teacher
):

    initialize()


    peers = (
        schema
        .get_admin_external_ids(
            "VK"
        )
    )


    if not peers:
        return 0


    sent = 0


    sent += _send_before(
        peers,
        send_teacher,
    )


    sent += _send_started(
        peers,
        send_teacher,
    )


    sent += _send_ending(
        peers,
        send_teacher,
    )


    return sent
