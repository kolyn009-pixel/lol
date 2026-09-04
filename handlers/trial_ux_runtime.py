from __future__ import annotations

import inspect
import json
import random

from datetime import (
    datetime,
    timedelta,
)

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
)

import database


# ============================================================
# SCHEMA
# ============================================================

def initialize():

    c = database.connect()

    try:

        c.execute("""
            CREATE TABLE IF NOT EXISTS
            trial_followup_log (

                lesson_id INTEGER PRIMARY KEY,

                user_id INTEGER NOT NULL,

                sent_at TEXT NOT NULL
            )
        """)

        c.commit()

    finally:

        c.close()


# ============================================================
# TRIAL AVAILABILITY
# ============================================================

def trial_available(
    user_id: int
) -> bool:

    user_id = int(user_id)

    user = database.get_user(
        user_id
    )

    if not user:
        return False

    # Фактически использованное пробное.
    if bool(
        user["trial_used"]
    ):
        return False

    c = database.connect()

    try:

        # ----------------------------------------------------
        # Если уже существует занятие —
        # пробное повторно не предлагаем.
        #
        # Это включает:
        # - назначенное пробное;
        # - обычное разовое занятие;
        # - ожидающее оплаты;
        # - подтверждённое занятие.
        # ----------------------------------------------------

        lesson = c.execute("""
            SELECT id

            FROM lessons

            WHERE user_id=?

              AND lesson_status
                  NOT IN (
                    'CANCELLED',
                    'REJECTED'
                  )

            LIMIT 1
        """, (
            user_id,
        )).fetchone()

        if lesson:
            return False


        # ----------------------------------------------------
        # Постоянное расписание
        # ----------------------------------------------------

        try:

            regular = c.execute("""
                SELECT id

                FROM regular_schedules

                WHERE user_id=?

                  AND COALESCE(
                        active,
                        1
                      )=1

                  AND COALESCE(
                        status,
                        'PENDING'
                      )
                      NOT IN (
                        'CANCELLED',
                        'REJECTED'
                      )

                LIMIT 1
            """, (
                user_id,
            )).fetchone()

        except Exception:

            try:

                regular = c.execute("""
                    SELECT id

                    FROM regular_schedules

                    WHERE user_id=?
                      AND active=1

                    LIMIT 1
                """, (
                    user_id,
                )).fetchone()

            except Exception:

                regular = None


        if regular:
            return False


        # ----------------------------------------------------
        # Уже созданные заявки
        # ----------------------------------------------------

        try:

            if database.get_pending_booking(
                user_id
            ):
                return False

        except Exception:
            pass


        try:

            if (
                database
                .student_has_pending_regular_schedule(
                    user_id
                )
            ):
                return False

        except Exception:
            pass


        return True

    finally:

        c.close()


# ============================================================
# STUDENT MENU FILTER
# ============================================================

def install_student_menu_patch():

    import bot as bot_module

    original = getattr(
        bot_module,
        "student_menu",
        None,
    )

    if not callable(original):
        return

    if getattr(
        original,
        "_trial_availability_v2",
        False,
    ):
        return


    def wrapped(
        user_id=None
    ):

        markup = original(
            user_id
        )

        if (
            markup is None
            or user_id is None
        ):
            return markup


        if trial_available(
            int(user_id)
        ):
            return markup


        rows = []

        for row in (
            markup.inline_keyboard
        ):

            new_row = []

            for button in row:

                text = str(
                    button.text
                    or ""
                ).lower()

                callback = str(
                    button.callback_data
                    or ""
                )

                if (
                    "пробн" in text
                    or callback == "trial"
                ):
                    continue

                new_row.append(
                    button
                )


            if new_row:

                rows.append(
                    new_row
                )


        return InlineKeyboardMarkup(
            rows
        )


    wrapped._trial_availability_v2 = (
        True
    )

    bot_module.student_menu = (
        wrapped
    )


# ============================================================
# OLD TRIAL BUTTON GUARD
# ============================================================

async def trial_guard(
    update,
    context,
):

    q = update.callback_query

    if not q:
        return


    user = (
        database
        .get_user_by_telegram_id(
            int(
                update
                .effective_user
                .id
            )
        )
    )


    if not user:
        return


    if trial_available(
        int(
            user["id"]
        )
    ):

        # Передаём управление
        # штатному trial handler.
        return


    await q.answer(
        "Пробное уже недоступно",
        show_alert=True,
    )


    await q.edit_message_text(
        (
            "🎁 Пробное занятие "
            "больше недоступно.\n\n"

            "У тебя уже есть запись "
            "на занятие или "
            "постоянное расписание."
        ),

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 Главное меню",
                        callback_data="main",
                    )
                ]
            ])
        ),
    )


    raise ApplicationHandlerStop


# ============================================================
# EDUCATION BUTTON — GUARANTEED
# ============================================================

async def student_card_post(
    update,
    context,
):

    q = update.callback_query

    if (
        not q
        or not q.message
    ):
        return


    try:

        user_id = int(
            q.data.split(
                "|",
                1
            )[1]
        )

    except Exception:

        return


    markup = (
        q.message.reply_markup
    )


    rows = [
        list(row)

        for row in (
            markup.inline_keyboard
            if markup
            else []
        )
    ]


    # Если кнопка уже реально присутствует
    # в отправленной карточке —
    # ничего не меняем.

    for row in rows:

        for button in row:

            if (
                button.callback_data
                ==
                f"edu_programs|{user_id}"
            ):

                return


    rows.insert(
        0,
        [
            InlineKeyboardButton(
                "🎓 Обучение и направления",

                callback_data=(
                    f"edu_programs|"
                    f"{user_id}"
                ),
            )
        ],
    )


    try:

        await q.edit_message_reply_markup(
            reply_markup=(
                InlineKeyboardMarkup(
                    rows
                )
            )
        )

    except Exception as exc:

        print(
            "EDUCATION CARD PATCH:",
            repr(exc),
        )


# ============================================================
# PRIMARY PROGRAM
# ============================================================

def _primary_program(
    user_id
):

    c = database.connect()

    try:

        return c.execute("""
            SELECT *

            FROM student_programs

            WHERE user_id=?
              AND active=1

            ORDER BY
                is_primary DESC,
                id

            LIMIT 1
        """, (
            int(user_id),
        )).fetchone()

    finally:

        c.close()


# ============================================================
# LESSON DURATION
# ============================================================

def _duration(
    lesson
):

    keys = set(
        lesson.keys()
    )


    if (
        "duration_minutes"
        in keys
        and lesson[
            "duration_minutes"
        ]
    ):

        return int(
            lesson[
                "duration_minutes"
            ]
        )


    start = datetime.fromisoformat(
        str(
            lesson[
                "start_time"
            ]
        )
    )

    end = datetime.fromisoformat(
        str(
            lesson[
                "end_time"
            ]
        )
    )


    return max(
        30,
        int(
            (
                end - start
            ).total_seconds()
            // 60
        ),
    )


# ============================================================
# CREATE SAME-TIME REGULAR REQUEST
# ============================================================

def create_same_time_request(
    user_id: int,
    lesson_id: int,
):

    user_id = int(user_id)
    lesson_id = int(lesson_id)


    lesson = database.get_lesson(
        lesson_id
    )


    if not lesson:

        return (
            False,
            "Занятие не найдено."
        )


    if int(
        lesson["user_id"]
    ) != user_id:

        return (
            False,
            "Это занятие другого ученика."
        )


    if not bool(
        lesson["is_trial"]
    ):

        return (
            False,
            "Это не пробное занятие."
        )


    if (
        str(
            lesson[
                "lesson_status"
            ]
        ).upper()
        != "COMPLETED"
    ):

        return (
            False,
            (
                "Сначала пробное "
                "занятие должно "
                "быть завершено."
            ),
        )


    try:

        if (
            database
            .student_has_pending_regular_schedule(
                user_id
            )
        ):

            return (
                False,
                (
                    "Заявка на постоянное "
                    "расписание уже создана."
                ),
            )

    except Exception:
        pass


    program = _primary_program(
        user_id
    )

    user = database.get_user(
        user_id
    )


    study_goal = (
        str(
            program[
                "study_goal"
            ]
        )

        if program

        else str(
            user[
                "study_goal"
            ]
        )
    )


    subject = (
        str(
            program[
                "subject"
            ]
        )

        if program

        else str(
            user[
                "main_subject"
            ]
        )
    )


    start = datetime.fromisoformat(
        str(
            lesson[
                "start_time"
            ]
        )
    )


    duration = _duration(
        lesson
    )


    weekday = int(
        start.weekday()
    )


    start_time = (
        start.strftime(
            "%H:%M"
        )
    )


    start_date = (
        start.date()
        + timedelta(
            days=7
        )
    )


    end_date = (
        start_date
        + timedelta(
            days=120
        )
    )


    fn = (
        database
        .create_regular_schedule_request
    )


    signature = (
        inspect.signature(
            fn
        )
    )


    values = {

        "user_id":
            user_id,

        "study_goal":
            study_goal,

        "subject":
            subject,

        "weekday":
            weekday,

        "start_time":
            start_time,

        "duration_minutes":
            duration,

        "start_date":
            start_date.isoformat(),

        "end_date":
            end_date.isoformat(),

        "request_source":
            "TRIAL_FOLLOWUP",
    }


    kwargs = {}


    for (
        name,
        parameter
    ) in (
        signature
        .parameters
        .items()
    ):

        if name in values:

            kwargs[
                name
            ] = values[
                name
            ]


        elif (
            parameter.default
            is inspect._empty
        ):

            return (
                False,
                (
                    "Backend постоянного "
                    "расписания требует "
                    f"параметр {name}."
                ),
            )


    try:

        schedule_id = fn(
            **kwargs
        )

    except Exception as exc:

        return (
            False,
            (
                "Не удалось создать "
                "заявку: "
                f"{exc}"
            ),
        )


    return (
        True,
        (
            "✅ Заявка создана.\n\n"

            "Ты выбрал постоянные "
            "занятия в то же время:\n\n"

            f"🕐 {start_time}\n"
            f"📅 День недели: "
            f"{weekday + 1}\n\n"

            "Преподаватель подтвердит "
            "постоянный слот 💜"
        ),
    )


# ============================================================
# FOLLOWUP CLAIM
# ============================================================

def _claim(
    lesson_id,
    user_id,
):

    c = database.connect()

    try:

        cur = c.execute("""
            INSERT OR IGNORE
            INTO trial_followup_log(
                lesson_id,
                user_id,
                sent_at
            )

            VALUES(
                ?,?,?
            )
        """, (
            int(
                lesson_id
            ),

            int(
                user_id
            ),

            database.now_iso(),
        ))


        c.commit()


        return (
            cur.rowcount
            > 0
        )

    finally:

        c.close()


def _unclaim(
    lesson_id
):

    c = database.connect()

    try:

        c.execute("""
            DELETE
            FROM trial_followup_log

            WHERE lesson_id=?
        """, (
            int(
                lesson_id
            ),
        ))

        c.commit()

    finally:

        c.close()


# ============================================================
# VK PEER
# ============================================================

def _vk_peer(
    user_id
):

    try:

        from vk_adapter.service import (
            vk_peer_for_user
        )

        return vk_peer_for_user(
            int(
                user_id
            )
        )

    except Exception:

        return None


# ============================================================
# TRIAL FOLLOW-UP JOB
# ============================================================

async def trial_followup_job(
    context
):

    initialize()


    now = datetime.now()


    c = database.connect()

    try:

        rows = list(
            c.execute("""
                SELECT
                    l.id,
                    l.user_id,
                    l.start_time,
                    l.end_time,

                    u.name,
                    u.telegram_id

                FROM lessons l

                JOIN users u
                  ON u.id=l.user_id

                LEFT JOIN
                    trial_followup_log f
                  ON f.lesson_id=l.id

                WHERE l.is_trial=1

                  AND
                    l.lesson_status=
                    'COMPLETED'

                  AND
                    u.active=1

                  AND
                    f.lesson_id
                    IS NULL

                ORDER BY l.id DESC

                LIMIT 30
            """).fetchall()
        )

    finally:

        c.close()


    for lesson in rows:

        # Не рассылаем follow-up
        # по старым пробным занятиям.

        try:

            end_dt = (
                datetime.fromisoformat(
                    str(
                        lesson[
                            "end_time"
                        ]
                    )
                )
            )


            if (
                now - end_dt.replace(
                    tzinfo=None
                )
                >
                timedelta(
                    hours=24
                )
            ):

                _claim(
                    lesson["id"],
                    lesson["user_id"],
                )

                continue

        except Exception:
            pass


        user_id = int(
            lesson[
                "user_id"
            ]
        )


        # Если после пробного
        # уже появилась нормальная запись —
        # follow-up не нужен.

        c = database.connect()

        try:

            normal = c.execute("""
                SELECT id

                FROM lessons

                WHERE user_id=?

                  AND is_trial=0

                  AND lesson_status
                      NOT IN (
                        'CANCELLED',
                        'REJECTED'
                      )

                LIMIT 1
            """, (
                user_id,
            )).fetchone()


            try:

                regular = c.execute("""
                    SELECT id

                    FROM regular_schedules

                    WHERE user_id=?

                      AND
                        COALESCE(
                            active,
                            1
                        )=1

                      AND
                        COALESCE(
                            status,
                            'PENDING'
                        )
                        NOT IN (
                            'CANCELLED',
                            'REJECTED'
                        )

                    LIMIT 1
                """, (
                    user_id,
                )).fetchone()

            except Exception:

                regular = None

        finally:

            c.close()


        if (
            normal
            or regular
        ):

            _claim(
                lesson[
                    "id"
                ],
                user_id,
            )

            continue


        if not _claim(
            lesson[
                "id"
            ],
            user_id,
        ):

            continue


        text = (
            "🎉 Пробное занятие завершено!\n\n"

            "Если тебе подошёл формат, "
            "можно закрепить это же время "
            "за тобой на постоянной основе 💜"
        )


        delivered = False


        # ----------------------------------------------------
        # TELEGRAM
        # ----------------------------------------------------

        if lesson[
            "telegram_id"
        ]:

            try:

                await context.bot.send_message(

                    chat_id=int(
                        lesson[
                            "telegram_id"
                        ]
                    ),

                    text=text,

                    reply_markup=(
                        InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(
                                    (
                                        "✅ Постоянно "
                                        "в это же время"
                                    ),

                                    callback_data=(
                                        "trial_keep_slot|"
                                        f"{lesson['id']}"
                                    ),
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🗓 Выбрать другое время",

                                    callback_data=(
                                        "booking_regular"
                                    ),
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "🏠 Главное меню",

                                    callback_data="main",
                                )
                            ],
                        ])
                    ),
                )


                delivered = True

            except Exception as exc:

                print(
                    "TRIAL FOLLOWUP TG:",
                    repr(exc),
                )


        # ----------------------------------------------------
        # VK
        # ----------------------------------------------------

        peer = _vk_peer(
            user_id
        )


        if peer:

            try:

                from vk_adapter import (
                    app as vk_app
                )


                keyboard = {

                    "one_time":
                        False,

                    "inline":
                        False,

                    "buttons": [

                        [
                            {
                                "action": {
                                    "type":
                                        "text",

                                    "label":
                                        (
                                            "✅ Постоянно "
                                            "в это же время"
                                        ),

                                    "payload":
                                        json.dumps(
                                            {
                                                "command":
                                                    (
                                                        "trial_keep_slot|"
                                                        f"{lesson['id']}"
                                                    )
                                            },

                                            ensure_ascii=False,
                                        ),
                                },

                                "color":
                                    "positive",
                            }
                        ],

                        [
                            {
                                "action": {
                                    "type":
                                        "text",

                                    "label":
                                        "🗓 Выбрать другое время",

                                    "payload":
                                        json.dumps(
                                            {
                                                "command":
                                                    "booking"
                                            },

                                            ensure_ascii=False,
                                        ),
                                },

                                "color":
                                    "primary",
                            }
                        ],
                    ],
                }


                vk_app.api(

                    "messages.send",

                    peer_id=int(
                        peer
                    ),

                    random_id=(
                        random.randint(
                            1,
                            2_000_000_000,
                        )
                    ),

                    message=text,

                    keyboard=(
                        json.dumps(
                            keyboard,
                            ensure_ascii=False,
                        )
                    ),
                )


                delivered = True

            except Exception as exc:

                print(
                    "TRIAL FOLLOWUP VK:",
                    repr(exc),
                )


        if not delivered:

            _unclaim(
                lesson[
                    "id"
                ]
            )


# ============================================================
# TG SAME TIME CALLBACK
# ============================================================

async def same_time_callback(
    update,
    context,
):

    q = update.callback_query

    if not q:
        return


    await q.answer()


    lesson_id = int(
        q.data.split(
            "|",
            1
        )[1]
    )


    user = (
        database
        .get_user_by_telegram_id(
            int(
                update
                .effective_user
                .id
            )
        )
    )


    if not user:

        await q.message.reply_text(
            "Ученик не найден."
        )

        return


    ok, text = (
        create_same_time_request(
            int(
                user[
                    "id"
                ]
            ),

            lesson_id,
        )
    )


    await q.message.reply_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🏠 Главное меню",

                        callback_data="main",
                    )
                ]
            ])
        ),
    )


# ============================================================
# INSTALL
# ============================================================

def install(
    application
):

    initialize()

    install_student_menu_patch()


    application.add_handler(
        CallbackQueryHandler(
            trial_guard,

            pattern=r"^trial$",
        ),

        group=-172,
    )


    application.add_handler(
        CallbackQueryHandler(
            same_time_callback,

            pattern=(
                r"^trial_keep_slot\|"
            ),
        ),

        group=-169,
    )


    # Выполняется после обычной
    # student_view карточки.

    # student_view is owned by handlers.admin_student_router.
    # No late reply_markup rewrite is needed here.


    if application.job_queue:

        application.job_queue.run_repeating(
            trial_followup_job,

            interval=5 * 60,

            first=20,

            name="trial_followup",
        )
