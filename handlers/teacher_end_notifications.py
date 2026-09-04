from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database
import admin


SUBJECT_NAMES = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}


# ============================================================
# SCHEMA
# ============================================================

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

        c.execute("""
            CREATE TABLE IF NOT EXISTS
            teacher_scheduled_lesson_finishes (

                lesson_id INTEGER PRIMARY KEY,

                finish_at TEXT NOT NULL,

                created_at TEXT NOT NULL,

                completed_at TEXT
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


# ============================================================
# TIME
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


def _iso(dt):

    # database.finish_lesson умеет работать
    # с ISO timestamp.
    return dt.isoformat()


def _subject(value):

    raw = str(
        value or ""
    ).upper()

    return SUBJECT_NAMES.get(
        raw,
        raw or "Занятие",
    )


# ============================================================
# LESSON CONTEXT
# ============================================================

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


def _context(lesson):

    plan_start = _dt(
        lesson["start_time"]
    )

    plan_end = _dt(
        lesson["end_time"]
    )

    actual_start = _dt(
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

    actual_end = (
        actual_start
        + timedelta(
            minutes=duration
        )
    )

    delta_minutes = round(
        (
            actual_start
            - plan_start
        ).total_seconds()
        / 60
    )

    late_minutes = max(
        delta_minutes,
        0,
    )

    early_minutes = max(
        -delta_minutes,
        0,
    )

    # Требование:
    #
    # начали раньше ->
    # предупреждаем относительно фактического конца;
    #
    # начали позже/вовремя ->
    # предупреждаем относительно планового конца.
    if actual_start < plan_start:

        notification_end = actual_end

    else:

        notification_end = plan_end

    return {
        "plan_start": plan_start,
        "plan_end": plan_end,
        "actual_start": actual_start,
        "actual_end": actual_end,
        "duration": duration,
        "late_minutes": late_minutes,
        "early_minutes": early_minutes,
        "notification_end": notification_end,
    }


def _next_lesson(current):

    c = database.connect()

    try:

        return c.execute("""
            SELECT

                l.id,
                l.user_id,
                l.start_time,
                l.subject,

                u.name

            FROM lessons l

            JOIN users u
              ON u.id=l.user_id

            WHERE
                l.id != ?

              AND
                l.cancelled_at IS NULL

              AND
                l.lesson_status IN (
                    'CONFIRMED',
                    'SCHEDULED'
                )

              AND
                l.start_time >= ?

            ORDER BY l.start_time

            LIMIT 1
        """, (
            int(current["id"]),
            str(current["end_time"]),
        )).fetchone()

    finally:

        c.close()


# ============================================================
# SCHEDULED FINISH
# ============================================================

def _schedule_finish(
    lesson_id,
    finish_at,
):

    c = database.connect()

    try:

        c.execute("""
            INSERT INTO
            teacher_scheduled_lesson_finishes(

                lesson_id,
                finish_at,
                created_at,
                completed_at
            )

            VALUES (?,?,?,NULL)

            ON CONFLICT(lesson_id)
            DO UPDATE SET

                finish_at=excluded.finish_at,
                created_at=excluded.created_at,
                completed_at=NULL
        """, (
            int(lesson_id),
            _iso(finish_at),
            database.now_iso(),
        ))

        c.commit()

    finally:

        c.close()


async def _process_scheduled_finishes(
    context,
):

    now = datetime.now(
        _timezone()
    )

    c = database.connect()

    try:

        rows = c.execute("""
            SELECT *
            FROM teacher_scheduled_lesson_finishes

            WHERE completed_at IS NULL
            ORDER BY finish_at
        """).fetchall()

    finally:

        c.close()

    for row in rows:

        finish_at = _dt(
            row["finish_at"]
        )

        if finish_at > now:
            continue

        lesson_id = int(
            row["lesson_id"]
        )

        lesson = database.get_lesson(
            lesson_id
        )

        # Уже завершено вручную.
        if (
            not lesson
            or lesson["lesson_status"]
            != "IN_PROGRESS"
        ):

            c = database.connect()

            try:

                c.execute("""
                    UPDATE
                    teacher_scheduled_lesson_finishes

                    SET completed_at=?

                    WHERE lesson_id=?
                """, (
                    database.now_iso(),
                    lesson_id,
                ))

                c.commit()

            finally:

                c.close()

            continue

        try:

            result = database.finish_lesson(
                lesson_id,
                finished_at=_iso(
                    finish_at
                ),
            )

        except Exception as error:

            print(
                "SCHEDULED LESSON FINISH ERROR:",
                repr(error),
            )

            continue

        c = database.connect()

        try:

            c.execute("""
                UPDATE
                teacher_scheduled_lesson_finishes

                SET completed_at=?

                WHERE lesson_id=?
            """, (
                database.now_iso(),
                lesson_id,
            ))

            c.commit()

        finally:

            c.close()

        user = database.get_user(
            int(lesson["user_id"])
        )

        bonus = int(
            result[
                "bonus_minutes_awarded"
            ]
            or 0
        )

        # Уведомляем ученика сразу в оба канала.
        try:

            from vk_adapter.channel_delivery import (
                send_student,
            )

            text = (
                "✅ ЗАНЯТИЕ ЗАВЕРШЕНО\n\n"
                f"⏱ Фактически: "
                f"{result['actual_minutes']} минут"
            )

            if bonus:

                text += (
                    "\n\n🎁 "
                    f"{bonus} минут добавлено "
                    "в бонусный баланс."
                )

            send_student(
                int(lesson["user_id"]),
                text,
            )

        except Exception as error:

            print(
                "SCHEDULED FINISH STUDENT NOTIFY:",
                repr(error),
            )

        teacher_text = (
            "✅ ЗАНЯТИЕ ЗАВЕРШЕНО ПО РАСПИСАНИЮ\n\n"
            f"👤 {user['name']}\n"
            f"⏱ Фактически: "
            f"{result['actual_minutes']} минут\n"
            f"⏳ Недоработано: "
            f"{result['underworked_minutes']} минут"
        )

        if bonus:

            teacher_text += (
                "\n🎁 Начислено бонусом: "
                f"{bonus} минут"
            )

        try:

            await context.bot.send_message(
                chat_id=int(
                    admin.ADMIN_ID
                ),
                text=teacher_text,
            )

        except Exception as error:

            print(
                "SCHEDULED FINISH TEACHER NOTIFY:",
                repr(error),
            )


# ============================================================
# END-5 JOB
# ============================================================

async def job(context):

    initialize()

    await _process_scheduled_finishes(
        context
    )

    now = datetime.now(
        _timezone()
    )

    for lesson in ending_lessons():

        try:

            info = _context(
                lesson
            )

        except Exception as error:

            print(
                "END5 CONTEXT ERROR:",
                repr(error),
            )

            continue

        seconds = (
            info["notification_end"]
            - now
        ).total_seconds()

        if not (
            0 <= seconds <= 5 * 60
        ):

            continue

        key = (
            "tg:smart_end5:"
            f"{lesson['id']}:"
            f"{info['notification_end']:%Y%m%d%H%M}"
        )

        if not _claim(
            key
        ):

            continue

        board = str(
            lesson["board_url"]
            or ""
        ).strip()

        text = (
            "⏳ ДО КОНЦА ЗАНЯТИЯ 5 МИНУТ\n\n"
            f"👤 {lesson['name']}\n"
            f"📖 {_subject(lesson['subject'])}\n\n"
            f"📅 План: "
            f"{info['plan_start']:%H:%M}"
            "–"
            f"{info['plan_end']:%H:%M}\n"
            f"▶️ Фактически начали: "
            f"{info['actual_start']:%H:%M}\n"
        )

        if info["early_minutes"]:

            text += (
                f"⏹ Полное время закончится: "
                f"{info['actual_end']:%H:%M}\n"
                f"✅ Начали раньше на "
                f"{info['early_minutes']} мин."
            )

        elif info["late_minutes"]:

            text += (
                f"🕐 По расписанию до: "
                f"{info['plan_end']:%H:%M}\n"
                f"⏱ Полные "
                f"{info['duration']} минут будут в: "
                f"{info['actual_end']:%H:%M}\n"
                f"⚠️ Чтобы провести всё время, "
                f"нужно задержаться на "
                f"{info['late_minutes']} мин."
            )

        else:

            text += (
                f"⏹ Окончание: "
                f"{info['plan_end']:%H:%M}"
            )

        next_lesson = (
            _next_lesson(
                lesson
            )
            if info["late_minutes"]
            else None
        )

        next_delay = 0

        if next_lesson:

            try:

                next_start = _dt(
                    next_lesson[
                        "start_time"
                    ]
                )

                next_delay = max(
                    round(
                        (
                            info["actual_end"]
                            - next_start
                        ).total_seconds()
                        / 60
                    ),
                    0,
                )

            except Exception:

                next_delay = 0

        if (
            next_lesson
            and next_delay > 0
        ):

            text += (
                "\n\n👤 Следующий ученик: "
                f"{next_lesson['name']} "
                f"в {_dt(next_lesson['start_time']):%H:%M}\n"
                f"⚠️ Возможная задержка: "
                f"{next_delay} мин."
            )

        if board:

            text += (
                "\n\n📝 Доска:\n"
                f"{board}"
            )

        rows = []

        # При позднем старте можно заранее
        # выбрать завершение строго по плану.
        if info["late_minutes"]:

            rows.append([
                InlineKeyboardButton(
                    "⏹ Завершить по расписанию",
                    callback_data=(
                        f"tend_plan|{lesson['id']}"
                    ),
                )
            ])

        rows.append([
            InlineKeyboardButton(
                "⏹ Завершить сейчас",
                callback_data=(
                    f"tend_now|{lesson['id']}"
                ),
            )
        ])

        if (
            next_lesson
            and next_delay > 0
        ):

            rows.append([
                InlineKeyboardButton(
                    (
                        "📨 Предупредить "
                        f"{next_lesson['name']}"
                    ),
                    callback_data=(
                        "tend_warn|"
                        f"{lesson['id']}|"
                        f"{next_lesson['id']}|"
                        f"{next_delay}"
                    ),
                )
            ])

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
            chat_id=int(
                admin.ADMIN_ID
            ),
            text=text,
            reply_markup=InlineKeyboardMarkup(
                rows
            ),
        )


# ============================================================
# CALLBACKS
# ============================================================

async def _finish_now(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    lesson_id = int(
        q.data.split("|")[1]
    )

    lesson = database.get_lesson(
        lesson_id
    )

    if (
        not lesson
        or lesson["lesson_status"]
        != "IN_PROGRESS"
    ):

        await q.answer(
            "Занятие уже завершено.",
            show_alert=True,
        )

        return

    user = database.get_user(
        int(lesson["user_id"])
    )

    await q.edit_message_text(
        (
            "⏹ ЗАВЕРШИТЬ ЗАНЯТИЕ СЕЙЧАС?\n\n"
            f"👤 {user['name']}\n\n"
            "Фактическое время будет "
            "зафиксировано в момент подтверждения.\n"
            "Если есть недоработанные минуты, "
            "они автоматически уйдут ученику бонусом."
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Да, завершить",
                    callback_data=(
                        f"tend_now_confirm|{lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="global_home",
                )
            ],
        ]),
    )


async def _finish_now_confirm(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    lesson_id = int(
        q.data.split("|")[1]
    )

    # Используем существующий admin-flow:
    # он фиксирует занятие и все связанные данные.
    await admin.finish_lesson(
        q,
        context,
        lesson_id,
    )


async def _finish_plan(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    lesson_id = int(
        q.data.split("|")[1]
    )

    lesson = database.get_lesson(
        lesson_id
    )

    if not lesson:

        return

    info = _context(
        lesson
    )

    actual_if_plan = max(
        round(
            (
                info["plan_end"]
                - info["actual_start"]
            ).total_seconds()
            / 60
        ),
        0,
    )

    missing = max(
        info["duration"]
        - actual_if_plan,
        0,
    )

    await q.edit_message_text(
        (
            "⏹ ЗАВЕРШИТЬ ПО РАСПИСАНИЮ?\n\n"
            f"📅 Плановый конец: "
            f"{info['plan_end']:%H:%M}\n"
            f"▶️ Начали: "
            f"{info['actual_start']:%H:%M}\n"
            f"⏱ Будет проведено: "
            f"{actual_if_plan} мин\n"
            f"🎁 Ученику бонусом: "
            f"{missing} мин\n\n"
            "После подтверждения бот сам завершит "
            "занятие в плановое время."
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    (
                        "✅ Завершить "
                        f"+ {missing} бонус мин"
                    ),
                    callback_data=(
                        f"tend_plan_confirm|{lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data="global_home",
                )
            ],
        ]),
    )


async def _finish_plan_confirm(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    lesson_id = int(
        q.data.split("|")[1]
    )

    lesson = database.get_lesson(
        lesson_id
    )

    if (
        not lesson
        or lesson["lesson_status"]
        != "IN_PROGRESS"
    ):

        await q.answer(
            "Занятие уже завершено.",
            show_alert=True,
        )

        return

    info = _context(
        lesson
    )

    _schedule_finish(
        lesson_id,
        info["plan_end"],
    )

    await q.edit_message_text(
        (
            "✅ ЗАВЕРШЕНИЕ ЗАПЛАНИРОВАНО\n\n"
            f"⏹ Занятие будет завершено "
            f"в {info['plan_end']:%H:%M}.\n\n"
            "Если фактического времени окажется меньше "
            "оплаченного, недостающие минуты "
            "автоматически начислятся ученику бонусом."
        )
    )


def _warning_text(
    next_lesson,
    delay,
):

    next_start = _dt(
        next_lesson["start_time"]
    )

    expected = (
        next_start
        + timedelta(
            minutes=delay
        )
    )

    return (
        "⏳ НЕМНОГО ЗАДЕРЖИВАЮСЬ\n\n"
        "Предыдущее занятие немного сдвинулось.\n\n"
        f"Планировали начать в "
        f"{next_start:%H:%M}, "
        f"ориентировочно начнём в "
        f"{expected:%H:%M}.\n\n"
        f"Задержка примерно "
        f"{delay} минут 💜"
    )


async def _warn_preview(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    _, lesson_id, next_id, delay = (
        q.data.split("|")
    )

    lesson_id = int(
        lesson_id
    )

    next_id = int(
        next_id
    )

    delay = int(
        delay
    )

    next_lesson = database.get_lesson(
        next_id
    )

    user = database.get_user(
        int(next_lesson["user_id"])
    )

    text = _warning_text(
        next_lesson,
        delay,
    )

    less = max(
        delay - 5,
        1,
    )

    more = delay + 5

    await q.edit_message_text(
        (
            "📨 ПРЕДПРОСМОТР СООБЩЕНИЯ\n\n"
            f"👤 {user['name']}\n\n"
            f"{text}"
        ),
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    f"➖ {less} мин",
                    callback_data=(
                        "tend_warn|"
                        f"{lesson_id}|"
                        f"{next_id}|"
                        f"{less}"
                    ),
                ),
                InlineKeyboardButton(
                    f"➕ {more} мин",
                    callback_data=(
                        "tend_warn|"
                        f"{lesson_id}|"
                        f"{next_id}|"
                        f"{more}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    "✅ Отправить в TG + VK",
                    callback_data=(
                        "tend_warn_send|"
                        f"{lesson_id}|"
                        f"{next_id}|"
                        f"{delay}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Не отправлять",
                    callback_data="global_home",
                )
            ],
        ]),
    )


async def _warn_send(
    update,
    context,
):

    q = update.callback_query
    await q.answer()

    _, lesson_id, next_id, delay = (
        q.data.split("|")
    )

    next_id = int(
        next_id
    )

    delay = int(
        delay
    )

    next_lesson = database.get_lesson(
        next_id
    )

    user_id = int(
        next_lesson["user_id"]
    )

    text = _warning_text(
        next_lesson,
        delay,
    )

    from vk_adapter.channel_delivery import (
        send_student,
    )

    delivered = send_student(
        user_id,
        text,
    )

    c = database.connect()

    try:

        c.execute("""
            UPDATE lessons

            SET
                tutor_delay_minutes=?,
                tutor_delay_notified_at=?,
                updated_at=?

            WHERE id=?
        """, (
            delay,
            database.now_iso(),
            database.now_iso(),
            next_id,
        ))

        c.commit()

    finally:

        c.close()

    user = database.get_user(
        user_id
    )

    await q.edit_message_text(
        (
            "✅ УЧЕНИК ПРЕДУПРЕЖДЁН\n\n"
            f"👤 {user['name']}\n"
            f"⏳ Задержка: {delay} мин\n\n"
            f"Telegram: "
            f"{'✅' if delivered['telegram'] else '—'}\n"
            f"VK: "
            f"{'✅' if delivered['vk'] else '—'}"
        )
    )


# ============================================================
# INSTALL
# ============================================================

def install(application):

    initialize()

    application.add_handler(
        CallbackQueryHandler(
            _finish_now,
            pattern=r"^tend_now\|",
        ),
        group=-169,
    )

    application.add_handler(
        CallbackQueryHandler(
            _finish_now_confirm,
            pattern=r"^tend_now_confirm\|",
        ),
        group=-169,
    )

    application.add_handler(
        CallbackQueryHandler(
            _finish_plan,
            pattern=r"^tend_plan\|",
        ),
        group=-169,
    )

    application.add_handler(
        CallbackQueryHandler(
            _finish_plan_confirm,
            pattern=r"^tend_plan_confirm\|",
        ),
        group=-169,
    )

    application.add_handler(
        CallbackQueryHandler(
            _warn_preview,
            pattern=r"^tend_warn\|",
        ),
        group=-169,
    )

    application.add_handler(
        CallbackQueryHandler(
            _warn_send,
            pattern=r"^tend_warn_send\|",
        ),
        group=-169,
    )

    if not application.job_queue:

        return

    existing = {
        item.name
        for item in (
            application
            .job_queue
            .jobs()
        )
    }

    if (
        "teacher_lesson_end5"
        not in existing
    ):

        application.job_queue.run_repeating(
            job,
            interval=60,
            first=10,
            name="teacher_lesson_end5",
        )
