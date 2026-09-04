import os
import asyncio

from datetime import (
    datetime,
    timedelta,
    date,
)

from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
)

from telegram.error import NetworkError, TimedOut, BadRequest

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    TypeHandler,
    ApplicationHandlerStop,
    filters,
)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import database
import admin
import payments
import students_admin
import schedule_admin
import channel_admin

from core import admin_roles
from core import audit_log as core_audit_log
from core import backup_manager as core_backup_manager
from core import event_center as core_event_center
from core import minute_balance
from core import financial_ledger as core_financial_ledger
from core import maintenance as core_maintenance
from core import teacher_tasks
from core import test_lab as core_test_lab
from core import stage1_admin as core_stage1_admin
from core import user_timezone
from learning import schema as learning_schema
from learning import curriculum as learning_curriculum
from handlers import learning_handlers
from learning import formula_study
from learning import homework_flow
from automation import schema as automation_schema
from automation import notifications as automation_notifications
from automation import schedule_tools as automation_schedule_tools
from automation import jobs as automation_jobs
from handlers import stage3_handlers
from handlers import stage3_role_ux
from handlers import stage3_admin_extras
from handlers import minute_admin_handlers
from handlers import admin_inbox_handlers
from handlers import musthave_admin
from handlers import musthave_jobs
from handlers import task_admin
from handlers import ai_provider_admin
from handlers import adelia_content
from handlers import student_message_handlers
from handlers import message_center_handlers
from handlers import global_home_handlers
from handlers import timezone_handlers
from final_features import schema as final_schema
from final_features import curriculum_full as final_curriculum
from final_features import handlers as final_handlers
from final_features import jobs as final_jobs
from crm_plus import schema as crm_schema
from crm_plus import handlers as crm_handlers
from crm_plus import jobs as crm_jobs
from final_features import ledger as final_minute_ledger
from ux_final import schema as ux_schema
from ux_final import handlers as ux_handlers


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

TOKEN_FILE = os.path.join(
    BASE_DIR,
    "token.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

CALENDAR_ID = "primary"

TIMEZONE_NAME = "Europe/Samara"

TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)

def apply_bot_timezone(name=None):
    """Apply TutorBot timezone to all runtime scheduling and local-time helpers."""
    global TIMEZONE_NAME, TIMEZONE
    name = name or database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        tz = ZoneInfo(name)
    except Exception:
        name = "Europe/Samara"
        tz = ZoneInfo(name)
    TIMEZONE_NAME = name
    TIMEZONE = tz
    try:
        import os as _os, time as _time
        _os.environ["TZ"] = name
        if hasattr(_time, "tzset"):
            _time.tzset()
    except Exception:
        pass
    return tz

SLOT_STEP_MINUTES = 30


# ============================================================
# БИБЛИОТЕКА ФОРМУЛ
# ============================================================

from formula_library import FORMULA_LIBRARY
from reference_library import PHYSICS_REFERENCE, CHEMISTRY_REFERENCE
from ege_formula_library import EGE_FORMULA_LIBRARY


# ============================================================
# СОСТОЯНИЯ РЕГИСТРАЦИИ
# ============================================================

(
    REG_ROLE,
    REG_NAME,
    REG_GRADE,
    REG_GOAL,
    REG_SUBJECT,
    REG_MORE,
    REG_PHONE,
    PARENT_NAME,
    PARENT_PHONE,
    PARENT_LINK_CODE,
) = range(10)


# ============================================================
# СОСТОЯНИЯ БОЛЬНИЧНОГО
# ============================================================

SICKNESS_COMMENT = 100

# Комментарий / материал к предстоящему занятию
LESSON_NOTE = 110
LESSON_REQUEST_CONTENT = 111
LESSON_REQUEST_LESSON = 112


# ============================================================
# НАЗВАНИЯ
# ============================================================

GOAL_NAMES = {
    "SCHOOL":
        "Повышение успеваемости",

    "OGE":
        "Подготовка к ОГЭ",

    "EGE":
        "Подготовка к ЕГЭ",

    "OLYMPIAD":
        "Олимпиадная подготовка",
}


SUBJECT_NAMES = {
    "PHYSICS":
        "Физика",

    "CHEMISTRY":
        "Химия",
}


LESSON_STATUS_NAMES = {
    "PENDING": "⏳ Ожидает подтверждения",
    "CONFIRMED": "✅ Подтверждено",
    "IN_PROGRESS": "▶️ Занятие идёт",
    "COMPLETED": "✅ Проведено",
    "CANCELLED": "❌ Отменено",
    "REJECTED": "🚫 Отклонено",
    "NO_SHOW": "👻 Неявка",
    "LATE_CANCELLED": "⚠️ Поздняя отмена",
    "SICKNESS": "🤒 Больничный",
}


PAYMENT_STATUS_NAMES = {
    "UNPAID": "❌ Не оплачено",
    "AWAITING_PAYMENT": "💳 Ожидает оплаты",
    "RESERVED_BALANCE": "🎟 Зарезервировано",
    "PAID": "✅ Оплачено",
    "FREE": "🎁 Бесплатно",
    "REFUNDED": "↩️ Возвращено",
    "UNPAID_CANCELLED": "❌ Отменено из-за неоплаты",
    "TRANSFERRED": "🔁 Перенесено",
}


# ============================================================
# GOOGLE CALENDAR
# ============================================================

def get_calendar_service():

    if not os.path.exists(
        TOKEN_FILE
    ):

        raise FileNotFoundError(
            "Не найден token.json"
        )

    creds = (
        Credentials
        .from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )
    )

    if (
        creds.expired
        and creds.refresh_token
    ):

        creds.refresh(
            Request()
        )

    return build(
        "calendar",
        "v3",
        credentials=creds
    )


# ============================================================
# GOOGLE BUSY
# ============================================================

def get_busy_periods(
    day
):

    service = (
        get_calendar_service()
    )

    start_of_day = datetime(
        day.year,
        day.month,
        day.day,
        0,
        0,
        tzinfo=TIMEZONE
    )

    end_of_day = (
        start_of_day
        + timedelta(days=1)
    )

    result = (
        service
        .freebusy()
        .query(
            body={
                "timeMin":
                    start_of_day.isoformat(),

                "timeMax":
                    end_of_day.isoformat(),

                "timeZone":
                    TIMEZONE_NAME,

                "items": [
                    {
                        "id":
                            CALENDAR_ID
                    }
                ]
            }
        )
        .execute()
    )

    busy = (
        result[
            "calendars"
        ][
            CALENDAR_ID
        ][
            "busy"
        ]
    )

    periods = []

    for item in busy:

        start = (
            datetime
            .fromisoformat(
                item[
                    "start"
                ].replace(
                    "Z",
                    "+00:00"
                )
            )
            .astimezone(
                TIMEZONE
            )
        )

        end = (
            datetime
            .fromisoformat(
                item[
                    "end"
                ].replace(
                    "Z",
                    "+00:00"
                )
            )
            .astimezone(
                TIMEZONE
            )
        )

        periods.append(
            (
                start,
                end
            )
        )

    return periods


# ============================================================
# СОЗДАТЬ GOOGLE EVENT
# ============================================================

def create_google_event(
    user,
    lesson
):

    if database.in_test_mode():
        return f"TEST_EVENT_{lesson.get('id','X')}" if hasattr(lesson,'get') else "TEST_EVENT"

    service = (
        get_calendar_service()
    )

    start_dt = (
        datetime.fromisoformat(
            lesson[
                "start_time"
            ]
        )
    )

    end_dt = (
        datetime.fromisoformat(
            lesson[
                "end_time"
            ]
        )
    )

    if start_dt.tzinfo is None:

        start_dt = (
            start_dt.replace(
                tzinfo=TIMEZONE
            )
        )

    if end_dt.tzinfo is None:

        end_dt = (
            end_dt.replace(
                tzinfo=TIMEZONE
            )
        )

    subject = (
        SUBJECT_NAMES.get(
            lesson[
                "subject"
            ],
            lesson[
                "subject"
            ]
        )
    )

    if lesson[
        "is_trial"
    ]:

        title = (
            f"🎁 Пробное — "
            f"{user['name']}"
        )

    else:

        title = (
            f"{subject} — "
            f"{user['name']}"
        )

    body = {

        "summary":
            title,

        "description":
            (
                f"Ученик: "
                f"{user['name']}\n"

                f"Класс: "
                f"{user['grade']}\n"

                f"Предмет: "
                f"{subject}\n"

                f"Занятие "
                f"#{lesson['id']}"
            ),

        "start": {

            "dateTime":
                start_dt.isoformat(),

            "timeZone":
                TIMEZONE_NAME,
        },

        "end": {

            "dateTime":
                end_dt.isoformat(),

            "timeZone":
                TIMEZONE_NAME,
        },
    }

    result = (
        service.events()
        .insert(
            calendarId=(
                CALENDAR_ID
            ),
            body=body
        )
        .execute()
    )

    return result[
        "id"
    ]


# ============================================================
# UPDATE GOOGLE EVENT
# ============================================================

def update_google_event(
    event_id,
    user,
    lesson,
):

    if database.in_test_mode():
        return event_id or "TEST_EVENT"

    if not event_id:
        return None

    service = (
        get_calendar_service()
    )

    start_dt = datetime.fromisoformat(
        lesson["start_time"]
    )

    end_dt = datetime.fromisoformat(
        lesson["end_time"]
    )

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(
            tzinfo=TIMEZONE
        )
    else:
        start_dt = start_dt.astimezone(
            TIMEZONE
        )

    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(
            tzinfo=TIMEZONE
        )
    else:
        end_dt = end_dt.astimezone(
            TIMEZONE
        )

    subject = SUBJECT_NAMES.get(
        lesson["subject"],
        lesson["subject"],
    )

    if lesson["is_trial"]:
        title = (
            f"🎁 Пробное — "
            f"{user['name']}"
        )
    else:
        title = (
            f"{subject} — "
            f"{user['name']}"
        )

    body = {
        "summary": title,

        "description": (
            f"Ученик: {user['name']}\n"
            f"Класс: {user['grade']}\n"
            f"Предмет: {subject}\n"
            f"Занятие #{lesson['id']}"
        ),

        "start": {
            "dateTime":
                start_dt.isoformat(),
            "timeZone":
                TIMEZONE_NAME,
        },

        "end": {
            "dateTime":
                end_dt.isoformat(),
            "timeZone":
                TIMEZONE_NAME,
        },
    }

    result = (
        service.events()
        .update(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body=body,
        )
        .execute()
    )

    return result["id"]


async def ensure_google_event(
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:
        return None

    if lesson["lesson_status"] != "CONFIRMED":
        return None

    if (
        lesson["payment_status"]
        == "AWAITING_PAYMENT"
    ):
        return None

    user = database.get_user(
        lesson["user_id"]
    )

    if user is None:
        return None

    if lesson["google_event_id"]:
        return lesson["google_event_id"]

    try:

        event_id = await asyncio.to_thread(
            create_google_event,
            user,
            lesson,
        )

        save_google_event_id(
            lesson_id,
            event_id,
        )

        print(
            "GOOGLE CALENDAR CREATED:",
            lesson_id,
            event_id,
        )

        return event_id

    except Exception as error:

        print(
            "GOOGLE CALENDAR CREATE ERROR:",
            lesson_id,
            repr(error),
        )

        return None


async def sync_google_calendar(
    application=None,
):

    now_iso = datetime.now(
        TIMEZONE
    ).isoformat()

    conn = database.connect()

    # ========================================================
    # 1. УДАЛЯЕМ СОБЫТИЯ, КОТОРЫХ БОЛЬШЕ НЕ ДОЛЖНО БЫТЬ
    #
    # - занятие отменено / завершено / больше не CONFIRMED;
    # - занятие стоит в ожидании переноса;
    # - занятие подтверждено, но снова ждёт оплату.
    # ========================================================

    stale_rows = conn.execute("""
        SELECT DISTINCT
            l.id,
            l.google_event_id

        FROM lessons l

        LEFT JOIN pending_reschedules pr
            ON pr.lesson_id = l.id
            AND pr.status = 'PENDING'

        WHERE
            l.google_event_id IS NOT NULL
            AND l.google_event_id != ''

            AND (
                l.lesson_status != 'CONFIRMED'
                OR l.payment_status = 'AWAITING_PAYMENT'
                OR pr.id IS NOT NULL
            )
    """).fetchall()

    # ========================================================
    # 2. СОЗДАЁМ СОБЫТИЯ ДЛЯ АКТУАЛЬНЫХ ЗАНЯТИЙ
    # ========================================================

    missing_rows = conn.execute("""
        SELECT l.id

        FROM lessons l

        LEFT JOIN pending_reschedules pr
            ON pr.lesson_id = l.id
            AND pr.status = 'PENDING'

        WHERE
            l.lesson_status = 'CONFIRMED'
            AND l.start_time > ?
            AND l.payment_status != 'AWAITING_PAYMENT'
            AND pr.id IS NULL

            AND (
                l.google_event_id IS NULL
                OR l.google_event_id = ''
            )

        ORDER BY l.start_time
    """, (
        now_iso,
    )).fetchall()

    conn.close()

    deleted = 0
    created = 0

    for row in stale_rows:

        ok = await asyncio.to_thread(
            delete_google_event,
            row["google_event_id"],
        )

        if ok:

            save_google_event_id(
                row["id"],
                None,
            )

            deleted += 1

            print(
                "GOOGLE CALENDAR CLEANUP:",
                row["id"],
            )

    for row in missing_rows:

        event_id = await ensure_google_event(
            row["id"]
        )

        if event_id:
            created += 1

    if created or deleted:

        print(
            "GOOGLE CALENDAR SYNC:",
            f"created={created}",
            f"deleted={deleted}",
        )

    return {
        "created": created,
        "deleted": deleted,
    }


async def google_calendar_sync_job(
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        await sync_google_calendar(
            context.application
        )

    except Exception as error:

        print(
            "GOOGLE CALENDAR SYNC ERROR:",
            repr(error),
        )


# ============================================================
# DELETE GOOGLE EVENT
# ============================================================

def delete_google_event(
    event_id
):

    if database.in_test_mode():
        return True

    if not event_id:
        return True

    try:

        service = (
            get_calendar_service()
        )

        service.events().delete(
            calendarId=(
                CALENDAR_ID
            ),
            eventId=(
                event_id
            )
        ).execute()

        print(
            "GOOGLE CALENDAR DELETED:",
            event_id,
        )

        return True

    except HttpError as error:

        # Если Google уже не видит событие,
        # для нашей синхронизации оно считается удалённым.
        if getattr(
            error.resp,
            "status",
            None,
        ) in {404, 410}:

            print(
                "GOOGLE CALENDAR ALREADY DELETED:",
                event_id,
            )

            return True

        print(
            "GOOGLE DELETE ERROR:",
            repr(error)
        )

        return False

    except Exception as error:

        print(
            "GOOGLE DELETE ERROR:",
            repr(error)
        )

        return False


# ============================================================
# ОБНОВИТЬ GOOGLE ID
# ============================================================

def save_google_event_id(
    lesson_id,
    event_id
):

    conn = (
        database.connect()
    )

    conn.execute("""
        UPDATE lessons

        SET
            google_event_id = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        event_id,
        database.now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# ВРЕМЯ
# ============================================================

def time_to_datetime(
    day,
    value
):

    parsed = (
        datetime.strptime(
            value,
            "%H:%M"
        )
        .time()
    )

    return datetime.combine(
        day,
        parsed,
        tzinfo=TIMEZONE
    )


def format_datetime(
    value
):

    if not value:

        return "—"

    dt = (
        datetime.fromisoformat(
            value
        )
    )

    if dt.tzinfo is None:

        dt = dt.replace(
            tzinfo=TIMEZONE
        )

    else:

        dt = dt.astimezone(
            TIMEZONE
        )

    return dt.strftime(
        "%d.%m.%Y %H:%M"
    )


# ============================================================
# РАБОЧИЕ ИНТЕРВАЛЫ
# ============================================================

def get_work_intervals(
    day
):

    rows = (
        database
        .get_effective_working_hours(day)
    )

    intervals = []

    for row in rows:

        intervals.append(
            (
                time_to_datetime(
                    day,
                    row[
                        "start_time"
                    ]
                ),

                time_to_datetime(
                    day,
                    row[
                        "end_time"
                    ]
                )
            )
        )

    exceptions = (
        database
        .get_schedule_exceptions(
            day.isoformat()
        )
    )


    # ========================================================
    # OPEN
    # ========================================================

    for item in exceptions:

        if (
            item[
                "exception_type"
            ]
            != "OPEN"
        ):

            continue

        if (
            not item[
                "start_time"
            ]
            or
            not item[
                "end_time"
            ]
        ):

            continue

        intervals.append(
            (
                time_to_datetime(
                    day,
                    item[
                        "start_time"
                    ]
                ),

                time_to_datetime(
                    day,
                    item[
                        "end_time"
                    ]
                )
            )
        )


    # ========================================================
    # CLOSED
    # ========================================================

    for item in exceptions:

        if (
            item[
                "exception_type"
            ]
            != "CLOSED"
        ):

            continue

        if (
            item[
                "start_time"
            ] is None
            and
            item[
                "end_time"
            ] is None
        ):

            intervals = []
            continue

        closed_start = (
            time_to_datetime(
                day,
                item[
                    "start_time"
                ]
            )
        )

        closed_end = (
            time_to_datetime(
                day,
                item[
                    "end_time"
                ]
            )
        )

        result = []

        for (
            start,
            end
        ) in intervals:

            if (
                closed_end <= start
                or
                closed_start >= end
            ):

                result.append(
                    (
                        start,
                        end
                    )
                )

                continue

            if (
                closed_start > start
            ):

                result.append(
                    (
                        start,
                        closed_start
                    )
                )

            if (
                closed_end < end
            ):

                result.append(
                    (
                        closed_end,
                        end
                    )
                )

        intervals = result

    intervals.sort(
        key=lambda item:
            item[0]
    )

    return intervals


# ============================================================
# СВОБОДНЫЕ СЛОТЫ
# ============================================================

def get_free_slots(
    day,
    duration_minutes,
    exclude_lesson_id=None
):

    work_intervals = (
        get_work_intervals(
            day
        )
    )

    if not work_intervals:

        return []

    google_busy = (
        get_busy_periods(
            day
        )
    )

    duration = timedelta(
        minutes=(
            duration_minutes
        )
    )

    step = timedelta(
        minutes=(
            SLOT_STEP_MINUTES
        )
    )

    now = (
        datetime.now(
            TIMEZONE
        )
    )

    result = []

    for (
        work_start,
        work_end
    ) in work_intervals:

        current = work_start

        while (
            current + duration
            <= work_end
        ):

            slot_end = (
                current
                + duration
            )

            if current <= now:

                current += step
                continue

            conflict = False

            # Google
            for (
                busy_start,
                busy_end
            ) in google_busy:

                if (
                    current < busy_end
                    and
                    slot_end > busy_start
                ):

                    conflict = True
                    break

            if conflict:

                current += step
                continue

            # Наша БД:
            # включая PENDING заявки
            if (
                database
                .is_slot_reserved(
                    current.isoformat(),
                    slot_end.isoformat(),
                    exclude_lesson_id=(
                        exclude_lesson_id
                    )
                )
            ):

                current += step
                continue

            result.append(
                current
            )

            current += step

    return result


# ============================================================
# ПОСТОЯННОЕ РАСПИСАНИЕ — HELPERS
# ============================================================

def regular_slot_is_reserved(
    weekday,
    start_time,
    duration_minutes,
):

    return database.regular_schedule_slot_conflict(
        weekday=weekday,
        start_time=start_time,
        duration_minutes=duration_minutes,
    )


def get_regular_free_slots(
    weekday,
    duration_minutes,
):

    """Slots suitable for a weekly permanent lesson.

    With parity schedules enabled a weekly permanent lesson must fit both the
    odd and even working week. Therefore the result is the intersection of the
    next odd/even occurrences. If one parity week is disabled, a weekly series
    is not offered from this screen; one-off lessons remain available normally.
    """
    duration = timedelta(minutes=int(duration_minutes))
    step = timedelta(minutes=SLOT_STEP_MINUTES)

    def slots_for_day(day_obj):
        values = set()
        for row in database.get_effective_working_hours(day_obj):
            start_dt = time_to_datetime(day_obj, row["start_time"])
            end_dt = time_to_datetime(day_obj, row["end_time"])
            current = start_dt
            while current + duration <= end_dt:
                value = current.strftime("%H:%M")
                if not regular_slot_is_reserved(weekday, value, duration_minutes):
                    values.add(value)
                current += step
        return values

    anchor = datetime.now(TIMEZONE).date()
    while anchor.weekday() != weekday:
        anchor += timedelta(days=1)

    mode = str(database.get_setting("teacher_week_mode", "SAME") or "SAME").upper()
    if mode == "SAME":
        return sorted(slots_for_day(anchor))

    if not database.teacher_week_enabled("ODD") or not database.teacher_week_enabled("EVEN"):
        return []

    odd_day = None
    even_day = None
    day_obj = anchor
    for _ in range(4):
        kind = database.teacher_week_kind(day_obj)
        if kind == "ODD" and odd_day is None:
            odd_day = day_obj
        if kind == "EVEN" and even_day is None:
            even_day = day_obj
        day_obj += timedelta(days=7)
    if odd_day is None or even_day is None:
        return []
    return sorted(slots_for_day(odd_day) & slots_for_day(even_day))

def regular_period_options():

    """Сроки серии: конец ближайших месяцев, максимум 31 декабря."""

    today = datetime.now(TIMEZONE).date()
    year = today.year

    result = []

    # Последний день каждого месяца от текущего до декабря.
    for month in range(today.month, 13):

        if month == 12:
            last_day = date(year, 12, 31)
        else:
            first_next = date(year, month + 1, 1)
            last_day = first_next - timedelta(days=1)

        # Слишком короткую серию не предлагаем.
        if last_day <= today:
            continue

        if (last_day - today).days < 14 and month != 12:
            continue

        result.append(last_day)

    # Убираем дубли (декабрь уже = 31.12).
    unique = []
    seen = set()

    for item in result:
        if item.isoformat() not in seen:
            unique.append(item)
            seen.add(item.isoformat())

    return unique


async def show_booking_type(
    query,
    user,
):

    pending = database.get_pending_booking(
        user["id"]
    )

    pending_regular = database.student_has_pending_regular_schedule(
        user["id"]
    )

    lines = [
        "📅 Давай выберем формат занятия",
        "",
        "Как хочешь записаться? Я покажу доступные варианты 👇",
    ]

    if pending:
        lines.extend([
            "",
            "⏳ У тебя уже есть разовая заявка на подтверждении:",
            format_datetime(pending["start_time"]),
        ])

    if pending_regular:
        lines.extend([
            "",
            "🔁 Заявка на постоянное расписание уже ждёт подтверждения преподавателя.",
        ])

    keyboard = []

    if not pending:
        keyboard.append([
            InlineKeyboardButton(
                "1️⃣ Разовое занятие",
                callback_data="booking_single",
            )
        ])

    if not pending_regular:
        keyboard.append([
            InlineKeyboardButton(
                "🔁 На постоянной основе",
                callback_data="booking_regular",
            )
        ])

    if pending:
        keyboard.append([
            InlineKeyboardButton(
                "❌ Отменить разовую заявку",
                callback_data=f"pending_cancel|{pending['id']}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Главное меню",
            callback_data="main",
        )
    ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_regular_weekdays(
    query,
    context,
    user,
):

    program = selected_program(context, user)

    if program is None:
        await show_program_picker(query, user)
        return

    duration = program_duration(program)
    keyboard = []

    names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

    for weekday in range(7):
        slots = get_regular_free_slots(weekday, duration)
        if not slots:
            continue
        keyboard.append([
            InlineKeyboardButton(
                f"📅 {names[weekday]}",
                callback_data=f"regular_day|{weekday}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="booking")
    ])

    await query.edit_message_text(
        "🔁 Постоянное расписание\n\n"
        f"⏱ Длительность занятия: {duration} минут\n\n"
        "Выбери удобный день недели — я покажу свободное время 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_regular_times(
    query,
    context,
    user,
    weekday,
):

    program = selected_program(context, user)

    if program is None:
        await show_program_picker(query, user)
        return

    duration = program_duration(program)
    slots = get_regular_free_slots(weekday, duration)

    if not slots:
        await query.edit_message_text(
            "😔 На этот день свободного постоянного времени пока нет. Выбери другой день — я посмотрю варианты.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="booking_regular")]
            ]),
        )
        return

    keyboard = []
    row = []

    actor_tid = int(query.from_user.id)
    teacher_anchor = datetime.now(TIMEZONE).date()
    while teacher_anchor.weekday() != weekday:
        teacher_anchor += timedelta(days=1)

    weekday_short = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    for value in slots:
        teacher_dt = time_to_datetime(teacher_anchor, value)
        local_dt = teacher_dt.astimezone(user_timezone.user_tz(actor_tid, TIMEZONE_NAME))
        display_value = local_dt.strftime("%H:%M")
        if local_dt.date() != teacher_dt.date():
            display_value = f"{weekday_short[local_dt.weekday()]} {local_dt.strftime('%H:%M')}"
        row.append(
            InlineKeyboardButton(
                display_value,
                callback_data=f"regular_time|{weekday}|{value}",
            )
        )
        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="booking_regular")
    ])

    await query.edit_message_text(
        "🔁 Постоянное расписание\n\n"
        "Вот свободное время. Выбери удобный слот 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_regular_periods(
    query,
    context,
    user,
    weekday,
    start_time,
):

    context.user_data["regular_weekday"] = weekday
    context.user_data["regular_time"] = start_time

    keyboard = []

    month_names = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }

    for end_date in regular_period_options():
        if end_date.month == 12 and end_date.day == 31:
            title = "🎄 До 31 декабря"
        else:
            title = f"📆 До {end_date.day} {month_names[end_date.month]}"

        keyboard.append([
            InlineKeyboardButton(
                title,
                callback_data=f"regular_until|{end_date.isoformat()}",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Выбрать другое время",
            callback_data=f"regular_day|{weekday}",
        )
    ])

    await query.edit_message_text(
        "🔁 ПОСТОЯННОЕ РАСПИСАНИЕ\n\n"
        f"📅 День недели: {weekday + 1}\n"
        f"🕐 Время: {start_time}\n\n"
        "До какой даты закрепить это время?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_regular_confirmation(
    query,
    context,
    user,
    end_date,
):

    weekday = context.user_data.get("regular_weekday")
    start_time = context.user_data.get("regular_time")

    if weekday is None or not start_time:
        await query.edit_message_text(
            "❌ Кажется, я потеряла данные записи. Пожалуйста, выбери слот заново.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔁 Выбрать", callback_data="booking_regular")]
            ]),
        )
        return

    program = selected_program(context, user)

    if program is None:
        await show_program_picker(query, user)
        return

    duration = program_duration(program)
    names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

    context.user_data["regular_end_date"] = end_date

    await query.edit_message_text(
        "🔁 Проверь постоянное расписание\n\n"
        f"📅 Каждый {names[weekday].lower()}\n"
        f"🕐 {start_time}\n"
        f"⏱ {duration} минут\n"
        f"📆 До {datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}\n\n"
        "После подтверждения преподавателем я закреплю это время за тобой. "
        "Дни, когда преподаватель недоступен, я автоматически пропущу.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Отправить заявку", callback_data="regular_confirm")],
            [InlineKeyboardButton("❌ Отмена", callback_data="booking")],
        ]),
    )


async def create_regular_request(
    query,
    context,
    user,
):

    weekday = context.user_data.get("regular_weekday")
    start_time = context.user_data.get("regular_time")
    end_date = context.user_data.get("regular_end_date")

    if weekday is None or not start_time or not end_date:
        await query.edit_message_text("❌ Я не смогла восстановить выбранный слот. Пожалуйста, выберите его заново.")
        return

    program = selected_program(context, user)

    if program is None:
        await show_program_picker(query, user)
        return

    duration = program_duration(program)
    today = datetime.now(TIMEZONE).date()

    try:
        schedule_id = database.create_regular_schedule_request(
            user_id=user["id"],
            study_goal=program["study_goal"],
            subject=program["subject"],
            weekday=weekday,
            start_time=start_time,
            duration_minutes=duration,
            start_date=today.isoformat(),
            end_date=end_date,
        )
    except Exception as error:
        await query.edit_message_text(
            f"❌ Я не смогла создать заявку.\n\n{error}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К записи", callback_data="booking")]
            ]),
        )
        return

    names = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

    await notify_student_if_parent_action(
        query, context, user,
        "🔁 Готово, я отправила заявку на постоянное расписание.\n"
        f"Каждый {names[weekday].lower()} в {start_time} до "
        f"{datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}."
    )
    await notify_parents_schedule(
        context,
        user,
        (
            "🔁 Готово, я отправила заявку на постоянное расписание.\n"
            f"Каждый {names[weekday].lower()} в {start_time} до "
            f"{datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}."
        ),
    )

    try:
        await context.bot.send_message(
            chat_id=admin.ADMIN_ID,
            text=(
                "🔁 НОВАЯ ЗАЯВКА НА ПОСТОЯННОЕ РАСПИСАНИЕ\n\n"
                f"👤 {user['name']}\n"
                f"📅 Каждый {names[weekday].lower()}\n"
                f"🕐 {start_time}\n"
                f"⏱ {duration} минут\n"
                f"📆 До {datetime.strptime(end_date, '%Y-%m-%d').strftime('%d.%m.%Y')}"
            ),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔁 Открыть заявку",
                    callback_data=f"schedule_regular_request|{schedule_id}",
                )]
            ]),
        )
    except Exception as error:
        print("REGULAR ADMIN NOTIFY:", repr(error))

    for key in ("regular_weekday", "regular_time", "regular_end_date"):
        context.user_data.pop(key, None)

    await query.edit_message_text(
        "✅ Готово 💜\n\n"
        "Я передала заявку преподавателю. Как только постоянное время подтвердят, я всё сохраню. "
        "Разовые занятия на другие даты при этом останутся доступны.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")]
        ]),
    )


async def sync_regular_schedules(application):

    """Поддерживает занятия постоянных серий примерно на 28 дней вперёд."""

    horizon = datetime.now(TIMEZONE).date() + timedelta(days=28)

    try:
        schedules = database.get_active_regular_schedules()
    except Exception as error:
        print("REGULAR SYNC LIST:", repr(error))
        return

    for schedule in schedules:

        if schedule["status"] != "APPROVED":
            continue

        try:
            result = database.generate_regular_lessons(
                schedule["id"],
                until_date=horizon,
            )
        except Exception as error:
            print("REGULAR SYNC GENERATE:", schedule["id"], repr(error))
            continue

        for lesson_id in result.get("created", []):

            lesson = database.get_lesson(lesson_id)
            user = database.get_user(lesson["user_id"])

            # Stage 3: пауза ученика или недоступность преподавателя
            if automation_schedule_tools.is_paused(user["id"], str(lesson["start_time"])[:10]):
                try:
                    database.cancel_lesson_by_admin(lesson_id, reason="STUDENT_PAUSE", refund=True)
                except Exception:
                    pass
                continue

            try:
                conn = database.connect()
                absent = conn.execute(
                    "SELECT 1 FROM teacher_absences WHERE active=1 AND date_from<=? AND date_to>=? LIMIT 1",
                    (str(lesson["start_time"])[:10], str(lesson["start_time"])[:10]),
                ).fetchone()
                conn.close()
            except Exception:
                absent = None
            if absent:
                try:
                    database.cancel_lesson_by_admin(lesson_id, reason="TEACHER_ABSENCE", refund=True)
                except Exception:
                    pass
                continue

            # Calendar
            if not lesson["google_event_id"]:
                try:
                    event_id = await asyncio.to_thread(
                        create_google_event,
                        user,
                        lesson,
                    )
                    save_google_event_id(lesson_id, event_id)
                except Exception as error:
                    print("REGULAR GOOGLE:", lesson_id, repr(error))

            # Напоминания ученику + преподавателю
            try:
                schedule_lesson_reminders(
                    application,
                    lesson_id,
                )
            except Exception as error:
                print("REGULAR REMINDERS:", lesson_id, repr(error))


async def regular_sync_job(context):
    await sync_regular_schedules(context.application)


def program_title(study_goal, subject):
    return (
        f"{GOAL_NAMES.get(study_goal, study_goal)} • "
        f"{SUBJECT_NAMES.get(subject, subject)}"
    )


def get_active_programs(user_id):
    return database.get_student_programs(
        user_id,
        active_only=True,
        approved_only=True,
    )


def selected_program(context, user):
    program_id = context.user_data.get("selected_program_id")

    if program_id:
        program = database.get_student_program(program_id)

        if (
            program is not None
            and program["user_id"] == user["id"]
            and program["active"]
            and program["approval_status"] == "APPROVED"
        ):
            return program

    programs = get_active_programs(user["id"])

    if len(programs) == 1:
        context.user_data["selected_program_id"] = programs[0]["id"]
        return programs[0]

    return None


def program_duration(program):
    try:
        return minute_balance.get_program_duration(program["id"])
    except Exception:
        return minute_balance.default_duration_for_goal(program["study_goal"])


def program_price_info(program):
    rate = database.get_program_rate_info(program["id"])
    duration = program_duration(program)
    price = round(rate["effective_rate"] * duration / 60)

    return {
        "hourly_rate": int(rate["effective_rate"]),
        "duration": int(duration),
        "price": int(price),
    }


async def show_program_picker(query, user):
    programs = get_active_programs(user["id"])

    if not programs:
        await query.edit_message_text(
            "Пока у тебя нет активных направлений. Напиши преподавателю — я помогу передать вопрос 💜",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")]
            ]),
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                program_title(p["study_goal"], p["subject"]),
                callback_data=f"booking_program|{p['id']}",
            )
        ]
        for p in programs
    ]

    keyboard.append([
        InlineKeyboardButton("⬅️ Главное меню", callback_data="main")
    ])

    await query.edit_message_text(
        "📚 Выбери направление\n\nНа что хочешь записаться? Я покажу подходящие варианты 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_booking_duration_picker(query, program):
    base = program_duration(program)
    rate = int(database.get_program_rate_info(program["id"])["effective_rate"])
    balance = minute_balance.get_balance(program["user_id"], hourly_rate=rate)
    available = int(balance["total"])

    # Для разового занятия сначала выбираем конкретные
    # дату и время, а способ оплаты решаем после этого.
    max_duration = 240
    options = []
    value = base
    while value <= max_duration:
        options.append(value)
        value += 30
    if base not in options:
        options.insert(0, base)

    rows = []
    row = []
    for minutes in options:
        row.append(InlineKeyboardButton(
            f"⏱ {minutes} мин", callback_data=f"booking_duration|{minutes}"
        ))
        if len(row) == 2:
            rows.append(row); row=[]
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="booking")])

    await query.edit_message_text(
        "⏱ Выбери длительность занятия\n\n"
        f"Твоё основное время: {base} минут.\n"
        "Можно выбрать занятие подольше, если хватает минут на балансе.\n\n"
        f"Сейчас доступно: {available} минут.",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ============================================================
# МЕНЮ УЧЕНИКА
# ============================================================

def student_home_text(user=None):
    name = (user["name"] if user else "") or ""
    hello = f"Привет, {name}!" if name else "Привет!"
    tid = int(user["telegram_id"]) if user and user["telegram_id"] else 0
    configured = bool(tid and database.timezone_configured(tid))
    time_line = f"🌍 Ваше время: {user_timezone.user_label(tid, TIMEZONE_NAME)}" if configured else "🌍 Ваше время ещё не настроено"
    return (
        "💜 АДЕЛИЯ • УЧЕНИК\n\n"
        f"{hello} Всё для занятий теперь на одном экране.\n\n"
        f"{time_line}\n\n"
        "📅 Ближайшее занятие, домашнее задание и баланс всегда доступны ниже."
    )


def student_menu(user_id=None):
    """
    Canonical TutorBot student home menu V3.

    This is the single source of truth for the student's
    Telegram main menu. Do not create competing home menus
    in feature modules.
    """

    rows = []

    user = None
    tz_configured = False

    if user_id is not None:

        try:

            user = database.get_user(
                int(user_id)
            )

        except Exception:

            user = None


        try:

            tz_configured = bool(
                user
                and user["telegram_id"]
                and database.timezone_configured(
                    int(user["telegram_id"])
                )
            )

        except Exception:

            tz_configured = False


        # ====================================================
        # TRIAL
        # ====================================================

        try:

            from handlers import trial_ux_runtime

            trial_ok = (
                trial_ux_runtime
                .trial_available(
                    int(user_id)
                )
            )

        except Exception:

            try:

                trial_ok = (
                    not database.has_used_trial(
                        int(user_id)
                    )
                )

            except Exception:

                trial_ok = False


        if trial_ok:

            rows.append([
                InlineKeyboardButton(
                    "🎁 Бесплатное пробное занятие",
                    callback_data="trial",
                )
            ])


        # ====================================================
        # ACTIVE HOMEWORK
        # ====================================================

        try:

            active_hw = (
                database
                .get_student_homework(
                    int(user_id),
                    active_only=True,
                )
            )

        except Exception:

            active_hw = []


        if active_hw:

            rows.append([
                InlineKeyboardButton(
                    (
                        "▶️ Продолжить ДЗ"
                        f" • {len(active_hw)}"
                    ),
                    callback_data="homework",
                )
            ])


    # ========================================================
    # MAIN ACTIONS
    # ========================================================

    rows.extend([

        [
            InlineKeyboardButton(
                "📅 Мои занятия",
                callback_data="lessons",
            ),

            InlineKeyboardButton(
                "➕ Записаться",
                callback_data="booking",
            ),
        ],

        [
            InlineKeyboardButton(
                "📝 Домашнее задание",
                callback_data="homework",
            ),

            InlineKeyboardButton(
                "📚 Моя учёба",
                callback_data="uxs3_study",
            ),
        ],

        [
            InlineKeyboardButton(
                "🧮 Формулы",
                callback_data="fh_home",
            ),

            InlineKeyboardButton(
                "🖥 Доска",
                callback_data="student_board",
            ),
        ],

        [
            InlineKeyboardButton(
                "💬 Преподаватель",
                callback_data="student_chat",
            ),

            InlineKeyboardButton(
                "🎓 Мой профиль",
                callback_data="student_profile",
            ),
        ],

        [
            InlineKeyboardButton(
                "••• Ещё",
                callback_data="student_more_menu",
            )
        ],
    ])


    # ========================================================
    # VK
    # ========================================================

    rows.append([
        InlineKeyboardButton(
            "💙 Подключить / проверить VK",
            callback_data="vk_link_start",
        )
    ])


    # ========================================================
    # TIMEZONE
    # ========================================================

    rows.append([
        InlineKeyboardButton(
            (
                "🌍 Сменить часовой пояс"
                if tz_configured
                else "🌍 Выбрать часовой пояс"
            ),
            callback_data="tz_menu",
        )
    ])


    return InlineKeyboardMarkup(
        rows
    )


async def show_formula_grades(query, user):
    grade_value = None
    try:
        grade_value = int(str(user["grade"]).split()[0])
    except Exception:
        pass
    grades = sorted(FORMULA_LIBRARY.keys())
    keyboard = []
    if grade_value in FORMULA_LIBRARY:
        keyboard.append([InlineKeyboardButton(f"🎓 {grade_value} класс", callback_data=f"formula_grade|{grade_value}")])
    for grade in grades:
        if grade != grade_value:
            keyboard.append([InlineKeyboardButton(f"{grade} класс", callback_data=f"formula_grade|{grade}")])
    keyboard.append([InlineKeyboardButton("🎓 Формулы ЕГЭ", callback_data="ege_formulas")])
    keyboard.append([InlineKeyboardButton("🧲 Физические константы", callback_data="reference_physics")])
    keyboard.append([InlineKeyboardButton("🧪 Химические таблицы", callback_data="reference_chemistry")])
    keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main")])
    await query.edit_message_text(
        "📚 Формулы и справочники\n\nВыбери класс — я собрала материалы по темам в одном месте. Твой класс покажу первым, если для него уже всё добавлено.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_formula_subjects(query, grade):
    subjects = FORMULA_LIBRARY.get(grade, {})
    keyboard = []
    for subject in subjects:
        keyboard.append([InlineKeyboardButton(SUBJECT_NAMES.get(subject, subject), callback_data=f"formula_subject|{grade}|{subject}")])
    keyboard.append([InlineKeyboardButton("⬅️ К классам", callback_data="formulas")])
    await query.edit_message_text(
        f"📚 Формулы · {grade} класс\n\nВыбери предмет — я покажу темы 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_formula_topics(query, grade, subject):
    topics = FORMULA_LIBRARY.get(grade, {}).get(subject, {})
    keyboard = [
        [InlineKeyboardButton(item["title"], callback_data=f"formula_topic|{grade}|{subject}|{key}")]
        for key, item in topics.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ К предметам", callback_data=f"formula_grade|{grade}")])
    await query.edit_message_text(
        f"📚 {SUBJECT_NAMES.get(subject, subject)} · {grade} класс\n\nВыбери тему 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_ege_sections(query):
    keyboard = [
        [InlineKeyboardButton(section["title"], callback_data=f"ege_section|{key}")]
        for key, section in EGE_FORMULA_LIBRARY.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ К формулам", callback_data="formulas")])
    await query.edit_message_text(
        "🎓 Формулы ЕГЭ\n\nВыбери раздел физики — я открою нужные формулы 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_ege_topics(query, section_key):
    section = EGE_FORMULA_LIBRARY.get(section_key)
    if not section:
        await query.answer("Этот раздел пока недоступен. Я добавлю его, как только материалы будут готовы 💜", show_alert=True)
        return
    keyboard = [
        [InlineKeyboardButton(item["title"], callback_data=f"ege_topic|{section_key}|{key}")]
        for key, item in section["topics"].items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ К разделам ЕГЭ", callback_data="ege_formulas")])
    await query.edit_message_text(
        f"{section['title']}\n\nВыбери тему 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def show_reference_topics(query, kind):
    library = PHYSICS_REFERENCE if kind == "physics" else CHEMISTRY_REFERENCE
    title = "🧲 ФИЗИКА · СПРАВОЧНИК" if kind == "physics" else "🧪 ХИМИЯ · СПРАВОЧНИК"
    keyboard = [
        [InlineKeyboardButton(item["title"], callback_data=f"reference_topic|{kind}|{key}")]
        for key, item in library.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ К формулам", callback_data="formulas")])
    await query.edit_message_text(
        f"{title}\n\nВыбери справочный раздел 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# TEACHER CONTACT CARD
# ============================================================

CONTACT_DAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
CONTACT_DAY_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def teacher_contact_status():
    now = datetime.now(TIMEZONE)
    value = (database.get_setting(f"teacher_contact_day_{now.weekday()}", "выходной") or "выходной").strip()
    if value.lower() == "выходной" or "-" not in value:
        return "⚪ Сейчас вне времени связи"
    try:
        start_s, end_s = value.split("-", 1)
        sh, sm = map(int, start_s.split(":"))
        eh, em = map(int, end_s.split(":"))
        minute = now.hour * 60 + now.minute
        if sh * 60 + sm <= minute <= eh * 60 + em:
            return "🟢 Сейчас можно связаться"
    except Exception:
        pass
    return "🌙 Сейчас вне времени связи"


def teacher_contact_text():
    name = database.get_setting("teacher_name", "Николай") or "Николай"
    description = database.get_setting("teacher_description", "Преподаватель физики и химии") or ""
    telegram = database.get_setting("teacher_telegram", "") or ""
    phone = database.get_setting("teacher_phone", "") or ""
    note = database.get_setting("teacher_contact_note", "") or ""
    lines = ["👨‍🏫 ПРЕПОДАВАТЕЛЬ", "", f"{name}"]
    if description: lines.append(description)
    lines.extend(["", teacher_contact_status(), "", "🕐 Время для связи:"])
    for day in range(7):
        value = database.get_setting(f"teacher_contact_day_{day}", "выходной") or "выходной"
        lines.append(f"• {CONTACT_DAY_SHORT[day]}: {value}")
    if telegram:
        lines.extend(["", f"💬 Telegram: {telegram}"])
    if phone:
        lines.append(f"📞 Телефон: {phone}")
    if note:
        lines.extend(["", f"ℹ️ {note}"])
    lines.extend(["", "Сообщение можно отправить в любое время; ответ преподавателя — в указанные часы."])
    return "\n".join(lines), telegram


async def show_teacher_contact(query, back_callback="main"):
    text, telegram = teacher_contact_text()
    kb = []
    student = database.get_user_by_telegram_id(query.from_user.id)
    username = telegram.strip().lstrip("@") if telegram else ""
    if student:
        kb.append([InlineKeyboardButton("💬 Написать Аделии", callback_data="student_message_start")])
        if username and all(c.isalnum() or c == "_" for c in username):
            kb.append([InlineKeyboardButton("✈️ Перейти в личный Telegram", url=f"https://t.me/{username}")])
    elif username and all(c.isalnum() or c == "_" for c in username):
        kb.append([InlineKeyboardButton("✈️ Написать преподавателю", url=f"https://t.me/{username}")])
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_callback), InlineKeyboardButton("🏠 Главное меню", callback_data="global_home")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


# ============================================================
# PROFILE
# ============================================================

async def show_profile(query, user):

    programs = database.get_student_programs(
        user["id"],
        active_only=True,
        approved_only=True,
    )

    lines = [
        "👤 Твой профиль",
        "",
        f"Имя: {user['name']}",
        f"Класс: {user['grade']}",
        "",
        "📚 Твои направления",
    ]

    for program in programs:
        rate = database.get_program_rate_info(program["id"])
        duration = minute_balance.get_program_duration(program["id"])
        balance = minute_balance.get_balance(user["id"], hourly_rate=int(rate["effective_rate"]))
        icon = "⭐️" if program["is_primary"] else "📚"

        lines.extend([
            "",
            f"{icon} {program_title(program['study_goal'], program['subject'])}",
            f"💰 {rate['effective_rate']} ₽ / 60 мин",
            f"⏱ Основное занятие: {duration} мин",
            f"🎟 Баланс: {balance['total']} мин (оплачено {balance['paid']}, бонус {balance['bonus']})",
        ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
            [InlineKeyboardButton("👨‍👩‍👧 Родители", callback_data="student_parents")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")],
        ]),
    )


async def show_learning_stats(query, user, parent_view=False):

    stats = database.get_learning_statistics(user["id"])
    total = stats["total"]

    lines = [
        "👨‍👩‍👧 Статистика ученика" if parent_view else "📊 Твоя статистика",
        "",
        f"👤 {user['name']}",
        f"🎓 {user['grade']} класс",
        "",
        f"✅ Проведено занятий: {total['completed_lessons']}",
        f"🎟 Оплачено времени: {total['paid_minutes']} мин",
        f"⏱ Фактически: {total['actual_minutes']} мин",
        f"➕ Переработка: {total['extra_minutes']} мин",
        "",
        f"🤒 Больничных: {total['sickness']}",
        f"👻 Неявок: {total['no_show']}",
        f"⚠️ Поздних отмен: {total['late_cancelled']}",
        "",
        f"📝 Проверено ДЗ: {total['homework_checked']}",
    ]

    if total["homework_accuracy_percent"] is not None:
        lines.extend([
            f"✅ Правильно: {total['homework_correct_tasks']} из {total['homework_total_tasks']}",
            f"📈 Средний результат: {total['homework_accuracy_percent']}%",
        ])

    if stats["programs"]:
        lines.extend(["", "📚 ПО НАПРАВЛЕНИЯМ"])

        for item in stats["programs"]:
            p = item["program"]
            hw = item["homework"]

            lines.extend([
                "",
                f"• {program_title(p['study_goal'], p['subject'])}",
                f"  ✅ {item['completed_lessons']} занятий",
                f"  🎟 {item['paid_minutes']} мин оплачено",
                f"  ⏱ {item['actual_minutes']} мин фактически",
                f"  🧮 Недоработано в копилке: "
                f"{item.get('underworked_minutes_balance', 0)} мин",
            ])

            if hw["accuracy_percent"] is not None:
                lines.append(
                    f"  📝 {hw['correct_tasks']} / {hw['total_tasks']} ({hw['accuracy_percent']}%)"
                )

                if hw["trend"] == "IMPROVING":
                    lines.append("  📈 Результат улучшается")
                elif hw["trend"] == "STABLE":
                    lines.append("  ➡️ Результат стабилен")
                elif hw["trend"] == "DECLINING":
                    lines.append("  📉 Результат снизился")

    keyboard = [[
        InlineKeyboardButton(
            "📊 Моя статистика" if parent_view else "👨‍👩‍👧 Версия для родителей",
            callback_data="my_stats" if parent_view else "parent_stats",
        )
    ], [
        InlineKeyboardButton("⬅️ Главное меню", callback_data="main")
    ]]

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# РЕГИСТРАЦИЯ
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    telegram_id = (
        update.effective_user.id
    )


    # ========================================================
    # АДМИН
    # ========================================================

    test_role = None

    if (
        core_test_lab.active(telegram_id)
        and (
            core_test_lab._is_tester_prod(telegram_id)
            or admin_roles.is_owner(telegram_id)
        )
    ):
        database.set_test_mode(True)
        core_test_lab.ensure_test_db()
        test_role = core_test_lab.get_test_role(telegram_id)

    # В Test Lab выбранная роль имеет приоритет над
    # реальной production-ролью Telegram-пользователя.
    if admin.is_admin(update) and test_role not in ("STUDENT", "PARENT"):

        await update.message.reply_text(
            admin.admin_home_text(),
            reply_markup=admin.admin_menu(),
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # РОДИТЕЛЬ
    # ========================================================

    parent = database.get_parent_by_telegram_id(telegram_id)

    if parent and parent["active"]:
        await update.message.reply_text(
            parent_home_text(parent),
            reply_markup=parent_menu(),
        )
        return ConversationHandler.END


    # ========================================================
    # УЧЕНИК
    # ========================================================

    user = (
        database
        .get_user_by_telegram_id(
            telegram_id
        )
    )

    if user:

        if not user[
            "active"
        ]:

            await update.message.reply_text(
                "Сейчас профиль неактивен. Если это неожиданно, напишите преподавателю — я помогу передать вопрос 💜"
            )

            return (
                ConversationHandler.END
            )

        await update.message.reply_text(
            student_home_text(user),

            reply_markup=(
                student_menu(user["id"])
            )
        )

        return (
            ConversationHandler.END
        )

    context.user_data.clear()

    await update.message.reply_text(
        "👋 Привет! Я Аделия 💜\n\nЯ помогу с занятиями, расписанием, домашними заданиями, оплатой и важными напоминаниями.\n\nДавай познакомимся! Кто будет пользоваться ботом?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎓 Я ученик", callback_data="regrole|student")],
            [InlineKeyboardButton("👨‍👩‍👧 Я родитель", callback_data="regrole|parent")],
        ]),
    )

    return REG_ROLE


async def registration_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    role = query.data.split("|", 1)[1]
    context.user_data["reg_role"] = role

    if role == "parent":
        await query.edit_message_text(
            "👨‍👩‍👧 Давайте познакомимся 💜\n\nКак вас зовут?"
        )
        return PARENT_NAME

    await query.edit_message_text(
        "🎓 Давай познакомимся 💜\n\nКак тебя зовут?"
    )
    return REG_NAME


async def registration_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    name = (
        update.message.text
        .strip()
    )

    if len(name) < 2:

        await update.message.reply_text(
            "Кажется, имя получилось слишком коротким. Напишите его ещё раз, пожалуйста 💜"
        )

        return REG_NAME

    context.user_data[
        "reg_name"
    ] = name

    await update.message.reply_text(
        "А теперь скажи, в каком ты классе? 📚\n\nВведи число от 5 до 11."
    )

    return REG_GRADE


async def registration_grade(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        grade = int(
            update.message.text
            .strip()
        )

    except ValueError:

        await update.message.reply_text(
            "Напиши класс числом — например, 8 💜"
        )

        return REG_GRADE

    if not 5 <= grade <= 11:

        await update.message.reply_text(
            "Я работаю с 5–11 классами. Выбери число в этом диапазоне 💜"
        )

        return REG_GRADE

    context.user_data[
        "reg_grade"
    ] = grade

    keyboard = [
        [
            InlineKeyboardButton(
                "📚 Повышение успеваемости",
                callback_data=(
                    "reggoal|SCHOOL"
                )
            )
        ]
    ]

    if grade == 9:

        keyboard.append([
            InlineKeyboardButton(
                "🎯 Подготовка к ОГЭ",
                callback_data=(
                    "reggoal|OGE"
                )
            )
        ])

    if grade >= 10:

        keyboard.append([
            InlineKeyboardButton(
                "🎯 Подготовка к ЕГЭ",
                callback_data=(
                    "reggoal|EGE"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🏆 Олимпиадная подготовка",
            callback_data=(
                "reggoal|OLYMPIAD"
            )
        )
    ])

    await update.message.reply_text(
        "Отлично! Теперь выбери цель занятий 👇",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )

    return REG_GOAL


async def registration_goal(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    goal = (
        query.data.split("|")[1]
    )

    grade = int(
        context.user_data[
            "reg_grade"
        ]
    )

    context.user_data[
        "reg_goal"
    ] = goal

    # ========================================================
    # ДОСТУПНЫЕ ПРЕДМЕТЫ
    #
    # SCHOOL:
    #   физика + химия до 11 класса включительно
    #
    # OGE:
    #   физика + химия, только 9 класс
    #
    # EGE:
    #   только физика
    #
    # OLYMPIAD:
    #   только физика
    # ========================================================

    keyboard = []

    if goal == "SCHOOL":

        if grade <= 11:

            keyboard = [
                [
                    InlineKeyboardButton(
                        "⚛️ Физика",
                        callback_data=(
                            "regsubject|PHYSICS"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧪 Химия",
                        callback_data=(
                            "regsubject|CHEMISTRY"
                        )
                    )
                ],
            ]

    elif goal == "OGE":

        if grade == 9:

            keyboard = [
                [
                    InlineKeyboardButton(
                        "⚛️ Физика",
                        callback_data=(
                            "regsubject|PHYSICS"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🧪 Химия",
                        callback_data=(
                            "regsubject|CHEMISTRY"
                        )
                    )
                ],
            ]

    elif goal in {
        "EGE",
        "OLYMPIAD",
    }:

        keyboard = [
            [
                InlineKeyboardButton(
                    "⚛️ Физика",
                    callback_data=(
                        "regsubject|PHYSICS"
                    )
                )
            ]
        ]

    if not keyboard:

        await query.edit_message_text(
            "❌ Для выбранного класса это "
            "направление сейчас недоступно."
        )

        return ConversationHandler.END

    await query.edit_message_text(
        "Выбери предмет 👇",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )

    return REG_SUBJECT


async def registration_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    subject = query.data.split("|")[1]
    goal = context.user_data["reg_goal"]
    grade = int(
        context.user_data["reg_grade"]
    )

    valid = (
        (
            goal == "SCHOOL"
            and grade <= 11
            and subject in {
                "PHYSICS",
                "CHEMISTRY",
            }
        )
        or (
            goal == "OGE"
            and grade == 9
            and subject in {
                "PHYSICS",
                "CHEMISTRY",
            }
        )
        or (
            goal in {
                "EGE",
                "OLYMPIAD",
            }
            and subject == "PHYSICS"
        )
    )

    if not valid:

        await query.edit_message_text(
            "❌ Такое сочетание направления "
            "и предмета недоступно."
        )

        return ConversationHandler.END

    programs = context.user_data.setdefault("reg_programs", [])

    if not any(
        x["study_goal"] == goal and x["subject"] == subject
        for x in programs
    ):
        programs.append({
            "study_goal": goal,
            "subject": subject,
        })

    lines = ["📚 ВЫБРАННЫЕ НАПРАВЛЕНИЯ", ""]

    for i, item in enumerate(programs, start=1):
        lines.append(
            f"{i}. {program_title(item['study_goal'], item['subject'])}"
        )

    lines.extend(["", "Хочешь добавить ещё одно направление?"])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ещё", callback_data="regmore|yes")],
            [InlineKeyboardButton("✅ Готово", callback_data="regmore|no")],
        ]),
    )

    return REG_MORE


async def registration_more(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data.split("|")[1] == "yes":
        grade = context.user_data["reg_grade"]

        keyboard = [[
            InlineKeyboardButton("📚 Повышение успеваемости", callback_data="reggoal|SCHOOL")
        ]]

        if grade == 9:
            keyboard.append([
                InlineKeyboardButton("🎯 Подготовка к ОГЭ", callback_data="reggoal|OGE")
            ])

        if grade >= 10:
            keyboard.append([
                InlineKeyboardButton("🎯 Подготовка к ЕГЭ", callback_data="reggoal|EGE")
            ])

        keyboard.append([
            InlineKeyboardButton("🏆 Олимпиадная подготовка", callback_data="reggoal|OLYMPIAD")
        ])

        await query.edit_message_text(
            "Выберите ещё одно направление:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return REG_GOAL

    await query.message.reply_text(
        "Отправьте номер телефона или нажмите «Пропустить».",
        reply_markup=ReplyKeyboardMarkup(
            [
                [KeyboardButton("📱 Отправить телефон", request_contact=True)],
                [KeyboardButton("Пропустить")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )

    return REG_PHONE


async def registration_phone(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    phone = None

    if update.message.contact:

        phone = (
            update.message
            .contact
            .phone_number
        )

    elif update.message.text:

        value = (
            update.message.text
            .strip()
        )

        if (
            value.lower()
            != "пропустить"
        ):

            phone = value

    telegram_user = (
        update.effective_user
    )

    try:

        user_id = (
            database
            .add_telegram_user(

                telegram_id=(
                    telegram_user.id
                ),

                telegram_username=(
                    telegram_user.username
                ),

                name=(
                    context.user_data[
                        "reg_name"
                    ]
                ),

                grade=(
                    context.user_data[
                        "reg_grade"
                    ]
                ),

                phone=phone,

                study_goal=context.user_data["reg_programs"][0]["study_goal"],
                main_subject=context.user_data["reg_programs"][0]["subject"]
            )
        )

    except Exception as error:

        print(
            "REG ERROR:",
            repr(error)
        )

        await update.message.reply_text(
            "❌ Я не смогла создать профиль. Попробуй ещё раз чуть позже или напиши преподавателю 💜",

            reply_markup=(
                ReplyKeyboardRemove()
            )
        )

        return (
            ConversationHandler.END
        )

    try:

        database.ensure_student_programs_for_user(
            user_id,
            [
                {
                    "study_goal": item["study_goal"],
                    "subject": item["subject"],
                    "is_primary": index == 0,
                    "approval_status": "APPROVED",
                    "created_by": "REGISTRATION",
                }
                for index, item in enumerate(
                    context.user_data["reg_programs"]
                )
            ],
        )

    except Exception as error:
        print("REG PROGRAMS ERROR:", repr(error))

    user = database.get_user(user_id)

    await update.message.reply_text(
        "✅ Регистрация завершена!",

        reply_markup=(
            ReplyKeyboardRemove()
        )
    )

    await update.message.reply_text(
        f"👤 {user['name']}\n"
        f"🎓 {user['grade']} класс\n\n"

        "🎁 Первое пробное занятие "
        "доступно бесплатно.",

        reply_markup=(
            student_menu(user["id"])
        )
    )

    try:
        database.mark_timezone_notified(int(telegram_user.id))
        await update.message.reply_text(
            "💜 И ещё один важный шаг — выбери своё время. Тогда расписание и свободные окна я буду показывать именно по твоему часовому поясу.",
            reply_markup=timezone_handlers.timezone_markup(int(telegram_user.id), include_back=False),
        )
    except Exception as error:
        print("REG TIMEZONE PROMPT ERROR:", repr(error))

    program_lines = [
        f"Направление: {program_title(item['study_goal'], item['subject'])}"
        for item in context.user_data.get("reg_programs", [])
    ]
    await notify_admin_registration(
        context,
        "Ученик",
        user["name"],
        telegram_user,
        phone,
        [f"Класс: {user['grade']}"] + program_lines,
    )

    context.user_data.clear()

    return (
        ConversationHandler.END
    )


# ============================================================
# РЕГИСТРАЦИЯ РОДИТЕЛЯ
# ============================================================

async def notify_admin_registration(context, role, name, telegram_user, phone=None, extra_lines=None):
    if database.in_test_mode():
        try:
            core_test_lab.log(telegram_user.id, 'REGISTRATION', f"{role}: {name}")
        except Exception:
            pass
        return
    lines = [
        "🆕 НОВАЯ РЕГИСТРАЦИЯ",
        "",
        f"Роль: {role}",
        f"Имя: {name}",
        f"Telegram ID: {telegram_user.id}",
    ]
    if telegram_user.username:
        lines.append(f"Username: @{telegram_user.username}")
    if phone:
        lines.append(f"Телефон: {phone}")
    if extra_lines:
        lines.extend(extra_lines)
    try:
        await context.bot.send_message(chat_id=admin.ADMIN_ID, text="\n".join(lines))
    except Exception as error:
        print("REGISTRATION ADMIN NOTIFY ERROR:", repr(error))


async def show_parent_child_card(query, parent, student):
    allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
    if student["id"] not in allowed:
        await query.answer("Ученик не привязан к вашему профилю.", show_alert=True)
        return

    lessons = database.get_upcoming_lessons(student["id"])
    lines = [
        f"🎓 {student['name']}",
        f"Класс: {student['grade']}",
        "",
        "📅 Ближайшие занятия:",
    ]
    if lessons:
        for lesson in lessons[:8]:
            lines.append(
                f"• {user_timezone.format_day_time_for_user(lesson['start_time'], int(parent['telegram_id']), TIMEZONE_NAME, with_zone=True)} — "
                f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}"
            )
    else:
        lines.append("Пока предстоящих занятий нет. Когда они появятся, я покажу их здесь 💜")

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📅 Назначить занятие", callback_data=f"parent_booking|{student['id']}")]]
            + [[
                InlineKeyboardButton("🎟 Баланс", callback_data=f"parent_balance|{student['id']}"),
                InlineKeyboardButton("💳 Оплаты", callback_data=f"parent_payments|{student['id']}"),
            ]]
            + [
                [InlineKeyboardButton(
                    f"🗓 {format_datetime(lesson['start_time'])} — открыть",
                    callback_data=f"parent_lesson|{student['id']}|{lesson['id']}"
                )]
                for lesson in lessons[:6]
                if lesson["lesson_status"] in {"PENDING", "CONFIRMED"}
            ]
            + [[InlineKeyboardButton("🔗 Отвязаться от ученика", callback_data=f"parent_unlink|{student['id']}")]]
            + [[InlineKeyboardButton("⬅️ К ученикам", callback_data="parent_children")]]
        ),
    )


def parent_home_text(parent=None):
    name = (parent["name"] if parent else "") or ""
    hello = f"Здравствуйте, {name}!" if name else "Здравствуйте!"
    tid = int(parent["telegram_id"]) if parent and parent["telegram_id"] else 0
    configured = bool(tid and database.timezone_configured(tid))
    time_line = f"🌍 Ваше время: {user_timezone.user_label(tid, TIMEZONE_NAME)}" if configured else "🌍 Ваше время ещё не настроено"
    return (
        "💜 АДЕЛИЯ • ГЛАВНАЯ\n\n"
        f"{hello} Я рядом. Здесь можно быстро посмотреть главное по ученику и связаться с преподавателем.\n\n"
        f"{time_line}"
    )


def parent_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍👩‍👧 Мои ученики", callback_data="parent_children"), InlineKeyboardButton("📅 Расписание", callback_data="parent_children")],
        [InlineKeyboardButton("📊 Прогресс", callback_data="uxp3_summary"), InlineKeyboardButton("💳 Оплата", callback_data="parent_children")],
        [InlineKeyboardButton("📝 Домашние задания", callback_data="uxp3_homework"), InlineKeyboardButton("📄 Отчёт", callback_data="uxp3_report")],
        [InlineKeyboardButton("🔔 Что требует внимания", callback_data="uxp3_attention")],
        [InlineKeyboardButton("💬 Написать преподавателю", callback_data="parent_teacher_contact")],
        [InlineKeyboardButton("➕ Привязать ученика", callback_data="parent_add_child"), InlineKeyboardButton("••• Ещё", callback_data="parent_children")],
        [InlineKeyboardButton("🌍 Сменить часовой пояс", callback_data="tz_menu")],
        [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ])


async def registration_parent_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if len(name) < 2:
        await update.message.reply_text("Кажется, имя получилось слишком коротким. Напишите его ещё раз, пожалуйста 💜")
        return PARENT_NAME
    context.user_data["parent_name"] = name
    await update.message.reply_text(
        "Отправьте номер телефона или нажмите «Пропустить».",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📱 Отправить телефон", request_contact=True)],
            [KeyboardButton("Пропустить")],
        ], resize_keyboard=True, one_time_keyboard=True),
    )
    return PARENT_PHONE


async def registration_parent_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = None
    if update.message.contact:
        phone = update.message.contact.phone_number
    elif update.message.text and update.message.text.strip().lower() != "пропустить":
        phone = update.message.text.strip()

    tg = update.effective_user
    try:
        parent_id = database.add_parent_account(
            tg.id, tg.username, context.user_data["parent_name"], phone
        )
    except Exception as error:
        print("PARENT REG ERROR:", repr(error))
        await update.message.reply_text("❌ Я не смогла создать родительский профиль. Попробуйте ещё раз чуть позже или напишите преподавателю.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    context.user_data["parent_id"] = parent_id
    await update.message.reply_text(
        "✅ Готово, я создала ваш родительский профиль. 💜\n\n"
        "Если у вас уже есть код привязки от ученика — отправьте его сейчас. "
        "Если нет, нажмите «Пропустить»: ученика можно привязать позднее.",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Пропустить")]], resize_keyboard=True, one_time_keyboard=True),
    )
    return PARENT_LINK_CODE


async def registration_parent_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = (update.message.text or "").strip()
    parent_id = context.user_data.get("parent_id")
    linked = None
    status = None
    if value.lower() != "пропустить":
        result = database.link_parent_to_student_by_code(parent_id, value)
        status, linked = result["status"], result["student"]
        if status == "invalid_code":
            await update.message.reply_text("❌ Я не нашла ученика по этому коду. Проверьте код или нажмите «Пропустить».")
            return PARENT_LINK_CODE
        if status == "limit_reached":
            await update.message.reply_text("❌ К этому ученику уже привязаны два родительских аккаунта — это максимум.")
            return PARENT_LINK_CODE
    text = "✅ Готово! Я завершила регистрацию. 💜"
    if linked:
        text += f"\n\n👧 {'Уже был привязан' if status == 'already_linked' else 'Привязан ученик'}: {linked['name']}"
    await update.message.reply_text(text, reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("💜 Я всё подготовила. Чем могу помочь? Выберите нужный раздел 👇", reply_markup=parent_menu())
    try:
        database.mark_timezone_notified(int(update.effective_user.id))
        await update.message.reply_text(
            "💜 Настроим ваше время — тогда расписание ребёнка я буду показывать в удобном для вас часовом поясе.",
            reply_markup=timezone_handlers.timezone_markup(int(update.effective_user.id), include_back=False),
        )
    except Exception as error:
        print("PARENT REG TIMEZONE PROMPT ERROR:", repr(error))
    parent = database.get_parent(parent_id)
    extra = [f"Привязан ученик: {linked['name']}"] if linked else []
    await notify_admin_registration(context, "Родитель", parent["name"], update.effective_user, parent["phone"], extra)
    context.user_data.clear()
    return ConversationHandler.END


async def notify_parents_schedule(context, user, text):
    """Организационные уведомления. Учебные материалы сюда не попадают."""
    for parent in database.get_student_parents(user["id"], schedule_only=True):
        try:
            await context.bot.send_message(
                chat_id=parent["telegram_id"],
                text=f"👨‍👩‍👧 {user['name']}\n\n{text}",
            )
        except Exception as error:
            print("PARENT NOTIFY ERROR:", repr(error))


async def notify_student_if_parent_action(query, context, user, text):
    parent = database.get_parent_by_telegram_id(query.from_user.id)
    if not parent or not parent["active"] or context.user_data.get("parent_acting_student_id") != user["id"]:
        return
    try:
        await context.bot.send_message(chat_id=user["telegram_id"], text=f"👨‍👩‍👧 Родитель {parent['name']}\n\n{text}")
    except Exception as error:
        print("PARENT ACTION STUDENT NOTIFY ERROR:", repr(error))


async def parent_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parent = database.get_parent_by_telegram_id(update.effective_user.id)
    if not parent or not parent["active"]:
        return

    data = query.data
    if data == "parent_main":
        await query.edit_message_text(parent_home_text(parent), reply_markup=parent_menu())
        return

    if data == "parent_teacher_contact":
        await show_teacher_contact(query, back_callback="parent_main")
        return

    if data == "parent_children":
        children = database.get_parent_students(parent["id"])
        if not children:
            await query.edit_message_text(
                "Пока к вашему профилю не привязан ни один ученик. Когда появится код — я помогу добавить его здесь 💜",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ Привязать ученика", callback_data="parent_add_child")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="parent_main")],
                ]),
            )
            return
        keyboard = [
            [InlineKeyboardButton(f"🎓 {child['name']}", callback_data=f"parent_child|{child['id']}")]
            for child in children
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="parent_main")])
        await query.edit_message_text("👨‍👩‍👧 Ваши ученики", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("parent_child|"):
        student_id = int(data.split("|")[1])
        student = database.get_user(student_id)
        if not student:
            return
        await show_parent_child_card(query, parent, student)
        return

    if data.startswith("parent_lesson|"):
        _, student_raw, lesson_raw = data.split("|", 2)
        student_id = int(student_raw)
        lesson_id = int(lesson_raw)
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        lesson = database.get_lesson(lesson_id)
        if student_id not in allowed or not lesson or int(lesson["user_id"]) != student_id:
            await query.answer("Это занятие уже недоступно. Я обновлю список, когда вы вернётесь назад.", show_alert=True)
            return
        student = database.get_user(student_id)
        context.user_data["parent_acting_student_id"] = student_id
        text = (
            f"🎓 {student['name']}\n\n"
            f"📅 {user_timezone.format_day_time_for_user(lesson['start_time'], int(parent['telegram_id']), TIMEZONE_NAME, with_zone=True)}\n"
            f"📖 {SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n"
            f"Статус: {LESSON_STATUS_NAMES.get(lesson['lesson_status'], lesson['lesson_status'])}"
        )
        keyboard = []
        if lesson["lesson_status"] == "PENDING":
            keyboard.append([InlineKeyboardButton("❌ Отменить заявку", callback_data=f"pending_cancel|{lesson_id}")])
        elif lesson["lesson_status"] == "CONFIRMED":
            keyboard.append([
                InlineKeyboardButton("🔁 Перенести", callback_data=f"reschedule_start|{lesson_id}"),
                InlineKeyboardButton("❌ Отменить", callback_data=f"parent_cancel|{student_id}|{lesson_id}"),
            ])
        keyboard.append([InlineKeyboardButton("⬅️ К ученику", callback_data=f"parent_child|{student_id}")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("parent_cancel|"):
        _, student_raw, lesson_raw = data.split("|", 2)
        student_id = int(student_raw)
        lesson_id = int(lesson_raw)
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        lesson = database.get_lesson(lesson_id)
        if student_id not in allowed or not lesson or int(lesson["user_id"]) != student_id or lesson["lesson_status"] != "CONFIRMED":
            await query.answer("Это занятие уже нельзя отменить через бот.", show_alert=True)
            return
        hours_left = database.get_hours_until_lesson(lesson)
        late = hours_left < 2
        warning = (
            "До занятия меньше 2 часов. Оно будет считаться использованным."
            if late else
            "До занятия больше 2 часов. Если занятие было списано из абонемента, оно вернётся на баланс."
        )
        await query.edit_message_text(
            "❌ Отмена занятия\n\n"
            f"📅 {format_datetime(lesson['start_time'])}\n\n"
            f"{warning}\n\nПодтвердить отмену?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, отменить", callback_data=f"parent_cancel_confirm|{student_id}|{lesson_id}|{1 if late else 0}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"parent_lesson|{student_id}|{lesson_id}")],
            ]),
        )
        return

    if data.startswith("parent_cancel_confirm|"):
        _, student_raw, lesson_raw, late_raw = data.split("|", 3)
        student_id = int(student_raw)
        lesson_id = int(lesson_raw)
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        lesson = database.get_lesson(lesson_id)
        if student_id not in allowed or not lesson or int(lesson["user_id"]) != student_id or lesson["lesson_status"] != "CONFIRMED":
            await query.answer("Это занятие уже нельзя отменить через бот.", show_alert=True)
            return
        # Recalculate at confirmation time instead of trusting callback payload.
        late = database.get_hours_until_lesson(lesson) < 2
        student = database.get_user(student_id)
        try:
            database.cancel_lesson_by_student(
                lesson_id, student_id, late=late, reason="PARENT_CANCEL"
            )
        except Exception as error:
            await query.edit_message_text(f"❌ {error}")
            return
        if lesson["google_event_id"]:
            try:
                await asyncio.to_thread(delete_google_event, lesson["google_event_id"])
            except Exception as error:
                print("PARENT CANCEL CALENDAR ERROR:", repr(error))
        try:
            await context.bot.send_message(
                chat_id=student["telegram_id"],
                text=(
                    "👨‍👩‍👧 Родитель отменил занятие.\n\n"
                    f"📅 {format_datetime(lesson['start_time'])}\n"
                    + ("⚠️ Поздняя отмена: занятие считается использованным." if late else "✅ Готово, я отменила занятие и вернула зарезервированные минуты на баланс.")
                ),
            )
        except Exception as error:
            print("PARENT CANCEL STUDENT NOTIFY ERROR:", repr(error))
        await notify_parents_schedule(
            context, student,
            f"❌ Родитель {parent['name']} отменил занятие.\n"
            f"📅 {format_datetime(lesson['start_time'])}\n"
            + ("⚠️ Поздняя отмена: занятие считается использованным." if late else "✅ Отмена с возвратом минут на баланс.")
        )
        try:
            await context.bot.send_message(
                chat_id=admin.ADMIN_ID,
                text=(
                    "👨‍👩‍👧 Родитель отменил занятие\n\n"
                    f"Ученик: {student['name']}\n"
                    f"📅 {format_datetime(lesson['start_time'])}\n"
                    + ("Тип: поздняя отмена, без возврата" if late else "Тип: обычная отмена, с возвратом")
                ),
            )
        except Exception as error:
            print("PARENT CANCEL ADMIN NOTIFY ERROR:", repr(error))
        await query.edit_message_text(
            "✅ Готово, я отменила занятие." + ("\nЗанятие считается использованным из-за поздней отмены." if late else "\nЗарезервированные минуты возвращены на баланс."),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К ученику", callback_data=f"parent_child|{student_id}")]]),
        )
        return

    if data.startswith("parent_balance|"):
        student_id = int(data.split("|")[1])
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        if student_id not in allowed:
            await query.answer("Ученик не привязан к вашему профилю.", show_alert=True)
            return
        student = database.get_user(student_id)
        balances = minute_balance.get_balance_by_rate(student_id)
        lines = [f"🎟 БАЛАНС — {student['name']}", ""]
        if not balances:
            lines.append("На балансе пока нет минут. Когда баланс пополнится, я сразу покажу их здесь.")
        else:
            total = 0
            for rate, item in sorted(balances.items()):
                total += item["total"]
                if rate == 0:
                    lines.append(f"🎁 Бонусная копилка: {item['bonus']} мин")
                else:
                    lines.append(f"• {rate:,} ₽ / 60 мин: {item['paid']} оплаченных минут".replace(",", " "))
            lines.extend(["", f"Всего доступно: {total} минут"])
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К ученику", callback_data=f"parent_child|{student_id}")]]),
        )
        return

    if data.startswith("parent_payments|"):
        student_id = int(data.split("|")[1])
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        if student_id not in allowed:
            await query.answer("Ученик не привязан к вашему профилю.", show_alert=True)
            return
        student = database.get_user(student_id)
        rows = database.get_user_payments(student_id, limit=10)
        lines = [f"💳 ОПЛАТЫ — {student['name']}", ""]
        if not rows:
            lines.append("История оплат пока пуста. Я покажу здесь все новые платежи после их появления.")
        else:
            for payment in rows:
                status = payments.PAYMENT_STATUS_NAMES.get(payment["status"], payment["status"])
                amount = f"{int(payment['total_amount'] or 0):,}".replace(",", " ")
                keys = payment.keys()
                minutes = int((payment["minutes_total"] if "minutes_total" in keys else 0) or 0)
                base = int((payment["base_duration_minutes"] if "base_duration_minutes" in keys else 0) or 0)
                count = int(payment["lessons_count"] or 0)
                if minutes <= 0 and count > 0:
                    base = base or 60
                    minutes = count * base
                equivalent = f" ≈ {count} × {base} мин" if count and base else ""
                created = (payment["created_at"] or "")[:10]
                lines.extend([
                    f"{status}",
                    f"• {created} · {minutes} мин{equivalent} · {amount} ₽",
                ])
                if payment["promo_code"]:
                    lines.append(f"  Промокод: {payment['promo_code']}")
                lines.append("")
        await query.edit_message_text(
            "\n".join(lines).rstrip(),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К ученику", callback_data=f"parent_child|{student_id}")]]),
        )
        return

    if data.startswith("parent_booking|"):
        student_id = int(data.split("|")[1])
        allowed = {row["id"] for row in database.get_parent_students(parent["id"])}
        if student_id not in allowed:
            await query.answer("Ученик не привязан к вашему профилю.", show_alert=True)
            return
        student = database.get_user(student_id)
        if not student or not student["active"]:
            await query.answer("Профиль ученика сейчас недоступен.", show_alert=True)
            return
        context.user_data["parent_acting_student_id"] = student_id
        context.user_data.pop("selected_program_id", None)
        programs = get_active_programs(student_id)
        if len(programs) > 1:
            await show_program_picker(query, student)
        elif len(programs) == 1:
            context.user_data["selected_program_id"] = programs[0]["id"]
            await show_booking_type(query, student)
        else:
            await query.edit_message_text(
                "❌ У ученика нет активных направлений.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ К ученику", callback_data=f"parent_child|{student_id}")
                ]]),
            )
        return

    if data.startswith("parent_unlink|"):
        student_id = int(data.split("|", 1)[1])
        if student_id not in {row["id"] for row in database.get_parent_students(parent["id"])}:
            await query.answer("Привязка уже отсутствует.", show_alert=True); return
        student = database.get_user(student_id)
        database.unlink_parent_from_student(parent["id"], student_id)
        context.user_data.pop("parent_acting_student_id", None)
        if student:
            try: await context.bot.send_message(chat_id=student["telegram_id"], text=f"ℹ️ Родитель {parent['name']} отменил привязку к вашему профилю.")
            except Exception as error: print("UNLINK STUDENT NOTIFY ERROR:", repr(error))
        await query.edit_message_text("✅ Готово, я удалила привязку.", reply_markup=parent_menu()); return

    if data == "parent_add_child":
        context.user_data["parent_link_mode"] = True
        await query.edit_message_text(
            "Отправьте код привязки ученика обычным сообщением.\n\n"
            "Ученик может получить код в «Мой профиль» → «Привязать родителя»."
        )
        return


async def parent_link_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (context.user_data or {}).get("parent_link_mode"):
        return
    parent = database.get_parent_by_telegram_id(update.effective_user.id)
    if not parent:
        return
    result = database.link_parent_to_student_by_code(parent["id"], update.message.text)
    status, student = result["status"], result["student"]
    if status == "invalid_code":
        await update.message.reply_text("❌ Я не нашла ученика по этому коду. Отправьте код ещё раз или откройте /start.")
        return
    context.user_data.pop("parent_link_mode", None)
    if status == "limit_reached":
        await update.message.reply_text("❌ К этому ученику уже привязаны два родительских аккаунта — это максимум.", reply_markup=parent_menu())
        return
    text = f"ℹ️ Ученик {student['name']} уже привязан." if status == "already_linked" else f"✅ Ученик {student['name']} привязан.\nТеперь вам будут приходить уведомления об изменениях расписания."
    await update.message.reply_text(text, reply_markup=parent_menu())


# ============================================================
# ДАТЫ
# ============================================================

async def show_dates(
    query,
    user,
    mode="normal",
    old_lesson_id=None
):

    if mode == "trial":

        duration = 45

    elif mode == "reschedule":

        old_lesson = (
            database.get_lesson(
                old_lesson_id
            )
        )

        duration = int(
            old_lesson[
                "duration_minutes"
            ]
        )

    else:

        duration = (
            payments
            .get_lesson_duration(
                user
            )
        )

    today = (
        datetime.now(
            TIMEZONE
        ).date()
    )

    weekdays = [
        "Пн",
        "Вт",
        "Ср",
        "Чт",
        "Пт",
        "Сб",
        "Вс",
    ]

    keyboard = []

    for i in range(14):

        day = (
            today
            + timedelta(days=i)
        )

        if not get_work_intervals(
            day
        ):

            continue

        callback = (
            f"date|"
            f"{mode}|"
            f"{day.isoformat()}"
        )

        if old_lesson_id:

            callback += (
                f"|{old_lesson_id}"
            )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"📅 "
                    f"{weekdays[day.weekday()]} "
                    f"{day.strftime('%d.%m')}"
                ),

                callback_data=callback
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Главное меню",
            callback_data=(
                "main"
            )
        )
    ])

    if mode == "trial":

        title = (
            "🎁 Бесплатное пробное занятие\n\n"
            "⏱ 45 минут\n\n"
            "Выбери удобную дату — на следующем шаге я покажу свободное время уже по твоему часовому поясу 👇"
        )

    elif mode == "reschedule":

        title = (
            "🔁 Перенос занятия\n\n"
            "Выбери новую дату — на следующем шаге я пересчитаю свободные варианты по твоему времени 👇"
        )

    else:

        title = (
            "📅 Запись на занятие\n\n"
            "Выбери удобную дату — на следующем шаге я покажу свободное время уже по твоему часовому поясу 👇"
        )

    await query.edit_message_text(
        title,

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# СВОБОДНОЕ ВРЕМЯ
# ============================================================

async def show_free_times(
    query,
    user,
    selected_date,
    mode="normal",
    old_lesson_id=None,
    duration_override=None
):

    if mode == "trial":

        duration = 45

    elif mode == "reschedule":

        old_lesson = (
            database.get_lesson(
                old_lesson_id
            )
        )

        duration = (
            old_lesson[
                "duration_minutes"
            ]
        )

    else:
        duration = int(duration_override or payments.get_lesson_duration(user))

    await query.edit_message_text(
        "⏳ Проверяю свободное время..."
    )

    try:

        slots = (
            await asyncio.to_thread(
                get_free_slots,
                selected_date,
                duration,
                old_lesson_id
            )
        )

    except Exception as error:

        print(
            "SLOTS ERROR:",
            repr(error)
        )

        await query.edit_message_text(
            "❌ Я не смогла загрузить расписание. Попробуй ещё раз через минуту 💜"
        )

        return

    if not slots:

        no_slots_keyboard = []
        if mode == "reschedule" and old_lesson_id:
            no_slots_keyboard.append([
                InlineKeyboardButton(
                    "✍️ Предложить своё время",
                    callback_data=f"ff_custom_reschedule|{old_lesson_id}",
                )
            ])
        no_slots_keyboard.append([
            InlineKeyboardButton(
                "⬅️ Назад",
                callback_data=(
                    f"reschedule_start|{old_lesson_id}"
                    if mode == "reschedule" and old_lesson_id
                    else ("trial" if mode == "trial" else "booking_single")
                ),
            )
        ])

        await query.edit_message_text(
            "😔 На эту дату свободного времени пока нет.\n\n"
            + ("Можно предложить своё время — даже вне стандартных рабочих часов. Преподаватель решит, сможет ли провести занятие." if mode == "reschedule" else ""),
            reply_markup=InlineKeyboardMarkup(no_slots_keyboard),
        )

        return

    keyboard = []

    row = []

    for slot in slots:

        value = slot.strftime("%H:%M")  # teacher/canonical callback value
        display_tid = int(query.from_user.id)
        local_slot = slot.astimezone(user_timezone.user_tz(display_tid, TIMEZONE_NAME))
        if local_slot.date() == slot.date():
            display_value = local_slot.strftime("%H:%M")
        else:
            display_value = local_slot.strftime("%d.%m %H:%M")

        callback = (
            f"time|"
            f"{mode}|"
            f"{selected_date.isoformat()}|"
            f"{value}"
        )

        if old_lesson_id:

            callback += (
                f"|{old_lesson_id}"
            )

        row.append(
            InlineKeyboardButton(
                display_value,
                callback_data=(
                    callback
                )
            )
        )

        if len(row) == 3:

            keyboard.append(
                row
            )

            row = []

    if row:

        keyboard.append(
            row
        )

    if mode == "reschedule" and old_lesson_id:
        keyboard.append([
            InlineKeyboardButton(
                "✍️ Ничего не подходит — предложить своё время",
                callback_data=f"ff_custom_reschedule|{old_lesson_id}",
            )
        ])

    await query.edit_message_text(
        f"📅 "
        f"{selected_date.strftime('%d.%m.%Y')}\n\n"
        f"🌍 Показываю окна по вашему времени: {user_timezone.user_label(int(query.from_user.id), TIMEZONE_NAME)}\n\n"
        "Выбери удобное время 👇",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# ЧЕРНОВИК РАЗОВОГО ЗАНЯТИЯ
# ============================================================

# ============================================================
# ЧЕРНОВИК РАЗОВОГО ЗАНЯТИЯ
# ============================================================

async def show_single_booking_draft(query, context, user, start_datetime):
    program = selected_program(context, user)

    if program is None:
        await show_program_picker(query, user)
        return

    price_info = program_price_info(program)
    base_duration = int(price_info["duration"])
    duration = int(
        context.user_data.get("booking_duration")
        or base_duration
    )

    if duration < base_duration:
        duration = base_duration

    hourly_rate = int(price_info["hourly_rate"])
    price = int(round(hourly_rate * duration / 60))

    balance = minute_balance.get_balance(
        user["id"],
        hourly_rate=hourly_rate,
    )
    available = int(balance["total"])

    end_datetime = (
        start_datetime
        + timedelta(minutes=duration)
    )

    draft_id = database.save_booking_draft(
        user_id=user["id"],
        program_id=program["id"],
        study_goal=program["study_goal"],
        subject=program["subject"],
        start_time=start_datetime.isoformat(),
        end_time=end_datetime.isoformat(),
        duration_minutes=duration,
        hourly_rate=hourly_rate,
        price=price,
    )

    context.user_data["single_booking_draft_id"] = draft_id

    subject = SUBJECT_NAMES.get(
        program["subject"],
        program["subject"],
    )

    local_start = start_datetime.astimezone(
        user_timezone.user_tz(
            int(query.from_user.id),
            TIMEZONE_NAME,
        )
    )

    rows = []

    if available >= duration:
        rows.append([
            InlineKeyboardButton(
                f"🎟 Использовать {duration} минут",
                callback_data="single_draft_balance",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                "💳 Оплатить это занятие",
                callback_data="single_draft_pay",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                "🎟 Купить абонемент",
                callback_data="single_draft_subscription",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "🕐 Выбрать другое время",
            callback_data="single_draft_change_time",
        )
    ])

    rows.append([
        InlineKeyboardButton(
            "❌ Отменить",
            callback_data="single_draft_cancel",
        )
    ])

    payment_line = (
        f"🎟 Доступно: {available} мин"
        if available >= duration
        else f"💳 Нужно оплатить • на балансе {available} мин"
    )

    await query.edit_message_text(
        "📋 ПРОВЕРЬ ЗАНЯТИЕ\n\n"
        f"📚 {subject}\n"
        f"📅 {local_start.strftime('%d.%m.%Y')}\n"
        f"🕐 {local_start.strftime('%H:%M')}\n"
        f"⏱ {duration} минут\n"
        f"💰 {price:,} ₽\n\n"
        f"{payment_line}\n\n"
        "Выбери, как оформить занятие 👇",
        reply_markup=InlineKeyboardMarkup(rows),
    )


# ============================================================
# НОВАЯ ЗАЯВКА
# ============================================================

async def create_student_request(
    query,
    context,
    user,
    start_datetime,
    trial=False
):

    if trial:

        duration = 45
        hourly_rate = 0
        price = 0

    else:

        program = selected_program(context, user)

        if program is None:
            await show_program_picker(query, user)
            return

        price_info = program_price_info(program)
        base_duration = int(price_info["duration"])
        duration = int(context.user_data.get("booking_duration") or base_duration)
        if duration < base_duration:
            duration = base_duration
        hourly_rate = price_info["hourly_rate"]
        price = int(round(hourly_rate * duration / 60))

    end_datetime = (
        start_datetime
        + timedelta(
            minutes=duration
        )
    )

    try:

        lesson_id = (
            database
            .create_lesson_request(

                user_id=(
                    user["id"]
                ),

                study_goal=user["study_goal"] if trial else program["study_goal"],
                subject=user["main_subject"] if trial else program["subject"],

                start_time=(
                    start_datetime
                    .isoformat()
                ),

                end_time=(
                    end_datetime
                    .isoformat()
                ),

                duration_minutes=(
                    duration
                ),

                hourly_rate=(
                    hourly_rate
                ),

                price=(
                    price
                ),

                is_trial=trial,
                program_id=None if trial else program["id"]
            )
        )

    except Exception as error:

        await query.edit_message_text(
            f"❌ Я не смогла создать заявку.\n\n"
            f"{error}",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Главное меню",
                            callback_data=(
                                "main"
                            )
                        )
                    ]
                ])
            )
        )

        return

    await notify_student_if_parent_action(
        query, context, user,
        "📅 Готово, я отправила заявку на занятие.\n"
        f"Дата и время: {start_datetime.strftime('%d.%m.%Y %H:%M')}.\n"
        "Теперь я жду подтверждения преподавателя и сообщу, когда всё будет готово. 💜"
    )
    await notify_parents_schedule(
        context,
        user,
        (
            "📅 Готово, я отправила заявку на занятие.\n"
            f"Дата и время: {start_datetime.strftime('%d.%m.%Y %H:%M')}.\n"
            "Теперь я жду подтверждения преподавателя и сообщу, когда всё будет готово. 💜"
        ),
    )

    # ========================================================
    # ТЕБЕ
    # ========================================================

    await context.bot.send_message(

        chat_id=(
            admin.ADMIN_ID
        ),

        text=(
            "🔔 НОВАЯ ЗАЯВКА НА ЗАНЯТИЕ\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"🎓 "
            f"{user['grade']} класс\n"

            f"📖 "
            f"{SUBJECT_NAMES.get(user['main_subject'], user['main_subject'])}\n\n"

            f"📅 "
            f"{start_datetime.strftime('%d.%m.%Y')}\n"

            f"🕐 "
            f"{start_datetime.strftime('%H:%M')}\n"

            f"⏱ "
            f"{duration} минут\n\n"

            f"Заявка #{lesson_id}"
        ),

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=(
                            f"admin_request_approve|"
                            f"{lesson_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=(
                            f"admin_request_reject|"
                            f"{lesson_id}"
                        )
                    )
                ]
            ])
        )
    )

    await query.edit_message_text(
        "⏳ Заявка отправлена 💜\n\n"

        f"📅 "
        f"{start_datetime.strftime('%d.%m.%Y')}\n"

        f"🕐 "
        f"{start_datetime.strftime('%H:%M')}\n"

        f"⏱ "
        f"{duration} минут\n\n"

        "Я передала заявку преподавателю и сообщу, как только он её подтвердит.\n\n"

        "Пока эта заявка рассматривается, новую создать нельзя.",

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "📚 Мои занятия",
                        callback_data=(
                            "lessons"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ Главное меню",
                        callback_data=(
                            "main"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# НАПОМИНАНИЕ О ЗАНЯТИИ
# ============================================================

async def send_message_with_retry(
    bot,
    *,
    chat_id,
    text,
    reply_markup=None,
    attempts=3,
):

    last_error = None

    for attempt in range(
        1,
        attempts + 1,
    ):

        try:

            return await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )

        except (
            NetworkError,
            TimedOut,
        ) as error:

            last_error = error

            print(
                "REMINDER SEND RETRY:",
                f"attempt={attempt}",
                repr(error),
            )

            if attempt < attempts:

                await asyncio.sleep(
                    3 * attempt
                )

    if last_error is not None:

        raise last_error


async def lesson_reminder_job(
    context: ContextTypes.DEFAULT_TYPE
):

    data = (
        context.job.data
    )

    lesson_id = (
        data[
            "lesson_id"
        ]
    )

    reminder_type = (
        data[
            "reminder_type"
        ]
    )

    if (
        database
        .reminder_was_sent(
            lesson_id,
            reminder_type
        )
    ):

        return

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if not lesson:

        return

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
    ):

        return

    # Не шлём обычные напоминания,
    # пока ручное занятие не оплачено

    if (
        lesson[
            "payment_status"
        ]
        == "AWAITING_PAYMENT"
    ):

        return

    user = (
        database
        .get_user(
            lesson[
                "user_id"
            ]
        )
    )

    start_dt = (
        datetime.fromisoformat(
            lesson[
                "start_time"
            ]
        )
    )

    if start_dt.tzinfo is None:

        start_dt = (
            start_dt.replace(
                tzinfo=TIMEZONE
            )
        )

    period_names = {
        "LESSON_24H": "через сутки",
        "LESSON_2H": "через 2 часа",
        "LESSON_30M": "через 30 минут",
        "LESSON_LINK_10M": "через 10 минут",
    }

    period = period_names.get(reminder_type, "")

    subject_name = SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])
    student_reminder_intro = {
        "LESSON_24H": (
            "💜 Небольшое напоминание от меня\n\n"
            f"Завтра у тебя занятие по предмету «{subject_name}»."
        ),
        "LESSON_2H": (
            "⏰ До занятия осталось 2 часа\n\n"
            f"Сегодня занимаемся: {subject_name}. "
            "Можно потихоньку готовиться 📚✨"
        ),
        "LESSON_30M": (
            "👀 Уже совсем скоро!\n\n"
            f"Через 30 минут начинается занятие: {subject_name}. "
            "Проверь, всё ли готово 💜"
        ),
    }.get(reminder_type, "⏰ Напоминаю о занятии 💜")

    # ========================================================
    # УЧЕНИКУ
    # ========================================================

    if (
        reminder_type != "LESSON_LINK_10M"
        and user["telegram_id"]
    ):

        await context.bot.send_message(

            chat_id=(
                user[
                    "telegram_id"
                ]
            ),

            text=(
                f"{student_reminder_intro}\n\n"
                f"📖 {subject_name}\n"
                f"📅 {user_timezone.format_for_user(start_dt, int(user['telegram_id']), TIMEZONE_NAME, '%d.%m.%Y')}\n"
                f"🕐 {user_timezone.format_time_for_user(start_dt, int(user['telegram_id']), TIMEZONE_NAME)} · {user_timezone.user_label(int(user['telegram_id']), TIMEZONE_NAME)}\n"
                f"⏱ {lesson['duration_minutes']} минут\n\n"
                + (
                    "Время ещё есть, но решила напомнить заранее ✨"
                    if reminder_type == "LESSON_24H" else
                    "Я оставила все детали в твоём расписании 💜"
                )
            ),

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📚 Мои занятия",
                            callback_data=(
                                "lessons"
                            )
                        )
                    ]
                ])
            )
        )


    # ========================================================
    # РОДИТЕЛЯМ (настраиваемо, Stage 3)
    # ========================================================

    parent_setting_key = {
        "LESSON_24H": "remind_24h",
        "LESSON_2H": "remind_2h",
        "LESSON_30M": "remind_30m",
        "LESSON_LINK_10M": "remind_10m",
    }.get(reminder_type)

    if parent_setting_key:
        for parent in database.get_student_parents(user["id"]):
            try:
                prefs = automation_notifications.get(parent["id"], user["id"])
                if not prefs.get(parent_setting_key, 0):
                    continue
                parent_tid = parent["telegram_id"]
                if not parent_tid:
                    continue
                await context.bot.send_message(
                    chat_id=parent_tid,
                    text=(
                        "🔔 Небольшое напоминание о занятии 💜\n\n"
                        f"У {user['name']} {period} занятие.\n\n"
                        f"📖 {subject_name}\n"
                        f"📅 {user_timezone.format_for_user(start_dt, int(parent_tid), TIMEZONE_NAME, '%d.%m.%Y')}\n"
                        f"🕐 {user_timezone.format_time_for_user(start_dt, int(parent_tid), TIMEZONE_NAME)} · {user_timezone.user_label(int(parent_tid), TIMEZONE_NAME)}\n\n"
                        "Актуальная информация уже в расписании."
                    ),
                )
            except Exception as error:
                print("PARENT LESSON REMINDER:", repr(error))


    # ========================================================
    # ТЕБЕ
    # ========================================================

    if reminder_type == "LESSON_LINK_10M":

        active_lesson = (
            database.get_active_lesson(
                exclude_lesson_id=lesson_id
            )
        )

        admin_text = (
            "🔗 СКОРО НАЧАЛО ЗАНЯТИЯ\n\n"

            f"👤 {user['name']}\n"
            f"📖 "
            f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n"
            f"📅 {start_dt.strftime('%d.%m.%Y')}\n"
            f"🕐 {start_dt.strftime('%H:%M')}\n"
            f"⏱ {lesson['duration_minutes']} минут\n\n"

            "Отправьте ссылку на занятие. "
            "После успешной отправки ученику "
            "запустится фактический таймер."
        )

        if active_lesson is not None:

            admin_text += (
                "\n\n⚠️ ПРЕДЫДУЩЕЕ ЗАНЯТИЕ "
                "ЕЩЁ ИДЁТ\n"

                f"👤 {active_lesson['name']}\n"
                f"▶️ Начато: "
                f"{format_datetime(active_lesson['started_at'])}\n\n"

                "Следующее занятие не начнётся "
                "автоматически. Его таймер запустится "
                "только после отправки ссылки."
            )

        if not user["board_url"]:

            admin_text += (
                "\n\n⚠️ Ссылка на постоянную доску "
                "у ученика пока не сохранена."
            )

        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⏱ Опаздываю",
                    callback_data=(
                        f"admin_lesson_delay_menu|{lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Отправить ссылку на занятие",
                    callback_data=(
                        f"admin_send_lesson_link|{lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Открыть занятие",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ],
        ])

    else:

        admin_text = (
            "⏰ НАПОМИНАНИЕ О ЗАНЯТИИ\n\n"

            f"👤 {user['name']}\n"
            f"📖 "
            f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n"
            f"📅 {start_dt.strftime('%d.%m.%Y')}\n"
            f"🕐 {start_dt.strftime('%H:%M')}\n"
            f"⏱ {lesson['duration_minutes']} минут\n\n"

            f"Занятие {period}. Я всё сохранила в расписании."
        )

        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть занятие",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ]
        ])

    await send_message_with_retry(
        context.bot,
        chat_id=admin.ADMIN_ID,
        text=admin_text,
        reply_markup=admin_keyboard,
    )

    database.mark_reminder_sent(
        lesson_id,
        reminder_type
    )


# ============================================================
# ПОСТАВИТЬ НАПОМИНАНИЯ ЗАНЯТИЯ
# ============================================================

def schedule_lesson_reminders(
    application,
    lesson_id
):

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if not lesson:

        return

    start_dt = (
        datetime.fromisoformat(
            lesson[
                "start_time"
            ]
        )
    )

    if start_dt.tzinfo is None:

        start_dt = (
            start_dt.replace(
                tzinfo=TIMEZONE
            )
        )

    reminder_settings = {
        "LESSON_24H": "notify_lesson_24h",
        "LESSON_2H": "notify_lesson_2h",
        "LESSON_30M": "notify_lesson_30m",
        "LESSON_LINK_10M": "notify_lesson_10m",
    }
    reminders = {
        "LESSON_24H": timedelta(hours=24),
        "LESSON_2H": timedelta(hours=2),
        "LESSON_30M": timedelta(minutes=30),
        "LESSON_LINK_10M": timedelta(minutes=10),
    }
    reminders = {k:v for k,v in reminders.items() if str(database.get_setting(reminder_settings[k], '1')).lower() not in ('0','false','off','no')}

    now = (
        datetime.now(
            TIMEZONE
        )
    )

    for (
        reminder_type,
        offset
    ) in reminders.items():

        if (
            database
            .reminder_was_sent(
                lesson_id,
                reminder_type
            )
        ):

            continue

        run_at = (
            start_dt
            - offset
        )

        if run_at <= now:

            continue

        name = (
            f"lesson_"
            f"{lesson_id}_"
            f"{reminder_type}"
        )

        for job in (
            application
            .job_queue
            .get_jobs_by_name(
                name
            )
        ):

            job.schedule_removal()

        application.job_queue.run_once(

            lesson_reminder_job,

            when=run_at,

            data={
                "lesson_id":
                    lesson_id,

                "reminder_type":
                    reminder_type,
            },

            name=name
        )


# ============================================================
# WATCHDOG НАПОМИНАНИЙ
# ============================================================

def reminder_due(
    start_dt,
    reminder_type,
    now,
):

    offsets = {
        "LESSON_24H":
            timedelta(hours=24),

        "LESSON_2H":
            timedelta(hours=2),

        "LESSON_30M":
            timedelta(minutes=30),

        "LESSON_LINK_10M":
            timedelta(minutes=10),
    }

    offset = offsets.get(
        reminder_type
    )

    if offset is None:

        return False

    due_at = (
        start_dt
        - offset
    )

    # Не досылаем сильно устаревшие напоминания.
    # Окно 15 минут достаточно, чтобы пережить сетевой сбой,
    # рестарт процесса или потерянный run_once.
    grace = timedelta(
        minutes=15
    )

    return (
        due_at <= now
        and now <= due_at + grace
    )


async def lesson_reminder_watchdog_job(
    context: ContextTypes.DEFAULT_TYPE
):

    conn = database.connect()

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            lesson_status = 'CONFIRMED'
            AND start_time > ?
    """, (
        (
            datetime.now(
                TIMEZONE
            )
            - timedelta(
                minutes=20
            )
        ).isoformat(),
    )).fetchall()

    conn.close()

    now = datetime.now(
        TIMEZONE
    )

    reminder_types = (
        "LESSON_24H",
        "LESSON_2H",
        "LESSON_30M",
        "LESSON_LINK_10M",
    )

    for lesson in rows:

        try:

            start_dt = datetime.fromisoformat(
                lesson["start_time"]
            )

            if start_dt.tzinfo is None:

                start_dt = start_dt.replace(
                    tzinfo=TIMEZONE
                )

            else:

                start_dt = start_dt.astimezone(
                    TIMEZONE
                )

        except Exception as error:

            print(
                "REMINDER WATCHDOG DATE ERROR:",
                lesson["id"],
                repr(error),
            )

            continue

        for reminder_type in reminder_types:

            if database.reminder_was_sent(
                lesson["id"],
                reminder_type,
            ):

                continue

            if not reminder_due(
                start_dt,
                reminder_type,
                now,
            ):

                continue

            print(
                "REMINDER WATCHDOG FIRE:",
                lesson["id"],
                reminder_type,
            )

            class WatchdogJob:

                data = {
                    "lesson_id":
                        lesson["id"],

                    "reminder_type":
                        reminder_type,
                }

            class WatchdogContext:

                job = WatchdogJob()
                bot = context.bot

            try:

                await lesson_reminder_job(
                    WatchdogContext()
                )

            except Exception as error:

                print(
                    "REMINDER WATCHDOG ERROR:",
                    lesson["id"],
                    reminder_type,
                    repr(error),
                )


# ============================================================
# НАПОМИНАНИЕ ОБ ОПЛАТЕ
# ============================================================

async def payment_reminder_job(
    context: ContextTypes.DEFAULT_TYPE
):

    if str(database.get_setting("notify_payment", "1")).lower() in ("0","false","off","no"):
        return

    data = (
        context.job.data
    )

    lesson_id = (
        data[
            "lesson_id"
        ]
    )

    reminder_type = (
        data[
            "reminder_type"
        ]
    )

    if (
        database
        .reminder_was_sent(
            lesson_id,
            reminder_type
        )
    ):

        return

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if not lesson:

        return

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
        or
        lesson[
            "payment_status"
        ] != "AWAITING_PAYMENT"
    ):

        return

    user = (
        database
        .get_user(
            lesson[
                "user_id"
            ]
        )
    )

    names = {

        "PAYMENT_24H":
            "До занятия осталось меньше суток.",

        "PAYMENT_8H":
            "До занятия осталось около 8 часов.",
    }

    if user[
        "telegram_id"
    ]:

        await context.bot.send_message(

            chat_id=(
                user[
                    "telegram_id"
                ]
            ),

            text=(
                "💳 Небольшое напоминание об оплате 💜\n\n"

                f"📅 "
                f"{user_timezone.format_day_time_for_user(lesson['start_time'], int(user['telegram_id']), TIMEZONE_NAME, with_zone=True)}\n"

                f"💰 "
                f"{payments.money(lesson['price'])}\n\n"

                f"{names.get(reminder_type, '')}\n\n"

                "Пожалуйста, успей подтвердить оплату не позднее чем за 2 часа до занятия. Иначе мне придётся автоматически освободить этот слот."
            ),

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "💳 Оплатить занятие",
                            callback_data=(
                                f"payment_lesson|{lesson_id}"
                            )
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🎟 Купить абонемент",
                            callback_data="payment_subscription"
                        )
                    ]
                ])
            )
        )

    database.mark_reminder_sent(
        lesson_id,
        reminder_type
    )


# ============================================================
# АВТООТМЕНА НЕОПЛАЧЕННОГО
# ============================================================

async def payment_deadline_job(
    context: ContextTypes.DEFAULT_TYPE
):

    if str(database.get_setting("payment_auto_cancel_enabled", "1")).lower() in ("0","false","off","no"):
        return

    lesson_id = (
        context.job.data[
            "lesson_id"
        ]
    )

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if not lesson:

        return

    if (
        lesson[
            "payment_status"
        ]
        != "AWAITING_PAYMENT"
    ):

        return

    cancelled = (
        database
        .auto_cancel_unpaid_lesson(
            lesson_id
        )
    )

    if not cancelled:

        return

    if lesson[
        "google_event_id"
    ]:

        deleted = await asyncio.to_thread(
            delete_google_event,
            lesson[
                "google_event_id"
            ]
        )

        if deleted:
            save_google_event_id(
                lesson_id,
                None,
            )

    user = (
        database
        .get_user(
            lesson[
                "user_id"
            ]
        )
    )

    if user[
        "telegram_id"
    ]:

        await context.bot.send_message(

            chat_id=(
                user[
                    "telegram_id"
                ]
            ),

            text=(
                "❌ Я отменила запись\n\n"

                f"📅 "
                f"{format_datetime(lesson['start_time'])}\n\n"

                "Оплата не была подтверждена за 2 часа до занятия, поэтому я освободила слот.\n\nЕсли занятие всё ещё нужно — выбери новое время, я помогу 💜"
            )
        )

    await context.bot.send_message(

        chat_id=(
            admin.ADMIN_ID
        ),

        text=(
            "⚠️ АВТООТМЕНА ЗАНЯТИЯ\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"📅 "
            f"{format_datetime(lesson['start_time'])}\n\n"

            "Причина: оплата не подтверждена "
            "за 2 часа до занятия."
        )
    )


# ============================================================
# PAYMENT JOBS
# ============================================================

def schedule_payment_reminders(
    application,
    lesson_id
):

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if not lesson:

        return

    if (
        lesson[
            "payment_status"
        ] != "AWAITING_PAYMENT"
    ):

        return

    start_dt = (
        datetime.fromisoformat(
            lesson[
                "start_time"
            ]
        )
    )

    if start_dt.tzinfo is None:

        start_dt = (
            start_dt.replace(
                tzinfo=TIMEZONE
            )
        )

    now = (
        datetime.now(
            TIMEZONE
        )
    )

    reminders = {

        "PAYMENT_24H":
            timedelta(hours=24),

        "PAYMENT_8H":
            timedelta(hours=8),
    }

    for (
        reminder_type,
        offset
    ) in reminders.items():

        run_at = (
            start_dt
            - offset
        )

        if run_at <= now:

            continue

        application.job_queue.run_once(

            payment_reminder_job,

            when=run_at,

            data={
                "lesson_id":
                    lesson_id,

                "reminder_type":
                    reminder_type,
            },

            name=(
                f"payment_"
                f"{lesson_id}_"
                f"{reminder_type}"
            )
        )

    deadline = (
        start_dt
        - timedelta(hours=2)
    )

    if deadline > now:

        application.job_queue.run_once(

            payment_deadline_job,

            when=deadline,

            data={
                "lesson_id":
                    lesson_id
            },

            name=(
                f"payment_deadline_"
                f"{lesson_id}"
            )
        )


# ============================================================
# HOMEWORK REMINDER
# ============================================================

async def homework_reminder_job(
    context: ContextTypes.DEFAULT_TYPE
):

    if str(database.get_setting("notify_homework", "1")).lower() in ("0","false","off","no"):
        return

    lesson_id = (
        context.job.data[
            "lesson_id"
        ]
    )

    if not (
        database
        .lesson_needs_homework_reminder(
            lesson_id
        )
    ):

        return

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    user = (
        database
        .get_user(
            lesson[
                "user_id"
            ]
        )
    )

    await context.bot.send_message(

        chat_id=(
            admin.ADMIN_ID
        ),

        text=(
            "⚠️ ДЗ НЕ ЗАДАНО\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"📖 "
            f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n\n"

            "После окончания занятия "
            "прошло 30 минут, "
            "но домашнее задание "
            "не было задано."
        ),

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "📝 Задать ДЗ",
                        callback_data=(
                            f"admin_homework_create|"
                            f"{lesson_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⏭ Сегодня без ДЗ",
                        callback_data=(
                            f"admin_homework_skip|"
                            f"{lesson_id}"
                        )
                    )
                ]
            ])
        )
    )

    database.mark_homework_reminder_sent(
        lesson_id
    )


def schedule_homework_reminder(
    application,
    lesson_id
):

    application.job_queue.run_once(

        homework_reminder_job,

        when=timedelta(
            minutes=30
        ),

        data={
            "lesson_id":
                lesson_id
        },

        name=(
            f"homework_"
            f"{lesson_id}"
        )
    )


# ============================================================
# RESTORE JOBS
# ============================================================

async def restore_jobs(
    application
):

    conn = (
        database.connect()
    )

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            lesson_status = 'CONFIRMED'

            AND start_time > ?
    """, (
        datetime.now(
            TIMEZONE
        ).isoformat(),
    )).fetchall()

    conn.close()

    for lesson in rows:

        if (
            lesson[
                "payment_status"
            ] == "AWAITING_PAYMENT"
        ):

            schedule_payment_reminders(
                application,
                lesson["id"]
            )

        else:

            schedule_lesson_reminders(
                application,
                lesson["id"]
            )


# ============================================================
# МОИ ЗАНЯТИЯ
# ============================================================

async def show_student_lessons(
    query,
    user
):

    conn = (
        database.connect()
    )

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            user_id = ?

            AND lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS'
            )

        ORDER BY start_time
    """, (
        user["id"],
    )).fetchall()

    conn.close()

    # Незавершённая разовая заявка живёт отдельно от lessons.
    # Показываем её ученику, чтобы запись не казалась пропавшей.
    draft = database.get_active_booking_draft(user["id"])

    draft_text = ""

    if draft:
        try:
            draft_dt = user_timezone.convert_for_user(
                draft["start_time"],
                int(query.from_user.id),
                TIMEZONE_NAME,
            )

            if draft_dt is None:
                draft_dt = datetime.fromisoformat(
                    draft["start_time"]
                )

            draft_when = draft_dt.strftime("%d.%m %H:%M")

        except Exception:
            draft_when = str(draft["start_time"])

        draft_statuses = {
            "DRAFT":
                "📝 оформление не завершено",

            "PAYMENT_PENDING":
                "💳 ожидает оплаты",

            "PAYMENT_ATTACHED":
                "🧾 чек прикреплён",

            "SUBMITTED":
                "⏳ отправлена преподавателю",

            "NEEDS_NEW_TIME":
                "🕐 нужно выбрать другое время",

            "NEEDS_PAYMENT_FIX":
                "⚠️ нужно исправить оплату",
        }

        draft_status = draft_statuses.get(
            draft["status"],
            str(draft["status"]),
        )

        draft_text = (
            "📋 Заявка на занятие\n"
            f"📅 {draft_when}\n"
            f"⏱ {draft['duration_minutes']} минут\n"
            f"💰 {draft['price']:,} ₽\n"
            f"Статус: {draft_status}\n\n"
        )

    if not rows:

        if draft:
            await query.edit_message_text(
                "📚 Твои занятия\n\n"
                + draft_text
                + "После подтверждения преподавателем занятие "
                  "появится здесь как обычное занятие 💜",

                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Главное меню",
                            callback_data="main",
                        )
                    ]
                ]),
            )

        else:
            await query.edit_message_text(
                "📚 Твои занятия\n\n"
                "Пока предстоящих занятий нет. Хочешь записаться? Я покажу свободное время 💜",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📅 Записаться",
                                callback_data=(
                                    "booking"
                                )
                            )
                        ],

                        [
                            InlineKeyboardButton(
                                "⬅️ Главное меню",
                                callback_data=(
                                    "main"
                                )
                            )
                        ]
                    ])
                )
            )

        return

    keyboard = []

    for lesson in rows:

        dt = user_timezone.convert_for_user(lesson["start_time"], int(query.from_user.id), TIMEZONE_NAME)
        if dt is None:
            dt = datetime.fromisoformat(lesson["start_time"])

        if (
            lesson[
                "lesson_status"
            ] == "PENDING"
        ):

            icon = "⏳"

        elif (
            lesson[
                "payment_status"
            ] == "AWAITING_PAYMENT"
        ):

            icon = "💳"

        elif (
            lesson[
                "lesson_status"
            ] == "IN_PROGRESS"
        ):

            icon = "▶️"

        else:

            icon = "✅"

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{icon} "
                    f"{dt.strftime('%d.%m %H:%M')}"
                ),

                callback_data=(
                    f"lesson_view|"
                    f"{lesson['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Главное меню",
            callback_data=(
                "main"
            )
        )
    ])

    text = (
        "📚 Твои занятия\n\n"
        + draft_text
        + "Выбери занятие, чтобы посмотреть подробности 👇"
    )

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# КАРТОЧКА ЗАНЯТИЯ УЧЕНИКА
# ============================================================

async def show_student_lesson(
    query,
    user,
    lesson_id
):

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if (
        not lesson
        or
        lesson[
            "user_id"
        ] != user["id"]
    ):

        await query.edit_message_text(
            "Я не нашла это занятие. Возможно, оно уже изменилось — вернись к списку и выбери актуальное."
        )

        return

    text = (
        "📚 Занятие\n\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n"

        f"📖 "
        f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n"

        f"⏱ "
        f"{lesson['duration_minutes']} минут\n\n"

        f"Статус: "
        f"{LESSON_STATUS_NAMES.get(lesson['lesson_status'], 'Неизвестный статус')}\n"

        f"Оплата: "
        f"{PAYMENT_STATUS_NAMES.get(lesson['payment_status'], 'Неизвестный статус')}"
    )

    notes = database.get_lesson_notes(
        lesson_id
    )

    if notes:

        text += (
            "\n\n💬 ЧТО НУЖНО РАЗОБРАТЬ"
        )

        for index, note in enumerate(
            notes[-3:],
            start=1,
        ):

            text += "\n"

            if note["text"]:

                preview = note["text"]

                if len(preview) > 120:
                    preview = (
                        preview[:117]
                        + "..."
                    )

                text += (
                    f"{index}. {preview}"
                )

            elif note["photo_file_id"]:

                text += (
                    f"{index}. 📷 Фото/материал"
                )

        if len(notes) > 3:

            text += (
                f"\n… ещё {len(notes) - 3}"
            )

    keyboard = []

    if (
        lesson[
            "lesson_status"
        ] == "PENDING"
    ):

        keyboard.append([
            InlineKeyboardButton(
                "❌ Отменить заявку",
                callback_data=(
                    f"pending_cancel|"
                    f"{lesson_id}"
                )
            )
        ])

    elif (
        lesson[
            "lesson_status"
        ] == "CONFIRMED"
    ):

        keyboard.append([
            InlineKeyboardButton(
                "🔁 Перенести",
                callback_data=(
                    f"reschedule_start|"
                    f"{lesson_id}"
                )
            ),

            InlineKeyboardButton(
                "🤒 Больничный",
                callback_data=(
                    f"sickness_start|"
                    f"{lesson_id}"
                )
            )
        ])

        if (
            lesson[
                "payment_status"
            ] == "AWAITING_PAYMENT"
        ):

            keyboard.append([
                InlineKeyboardButton(
                    "💳 Оплатить занятие",
                    callback_data=(
                        f"payment_lesson|{lesson_id}"
                    )
                )
            ])

    if lesson[
        "lesson_status"
    ] in {
        "PENDING",
        "CONFIRMED",
    }:

        keyboard.append([
            InlineKeyboardButton(
                "💬 Что разобрать на занятии",
                callback_data=(
                    f"lesson_note_start|{lesson_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Мои занятия",
            callback_data=(
                "lessons"
            )
        )
    ])

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# БЫСТРЫЙ ЗАПРОС К ЗАНЯТИЮ ИЗ ГЛАВНОГО МЕНЮ
# ============================================================

def lesson_request_controls():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Выбрать занятие", callback_data="lesson_request_choose")],
        [InlineKeyboardButton("❌ Отменить", callback_data="lesson_request_cancel")],
    ])


async def lesson_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = database.get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        await query.edit_message_text("Сначала нажми /start, чтобы я могла открыть твой профиль 💜")
        return ConversationHandler.END

    lessons = [
        lesson for lesson in database.get_upcoming_lessons(user["id"])
        if lesson["lesson_status"] in {"PENDING", "CONFIRMED"}
    ]
    if not lessons:
        await query.edit_message_text(
            "💬 Запрос к занятию\n\n"
            "Сейчас нет предстоящих занятий, к которым можно прикрепить запрос. Как только занятие появится, я дам выбрать его здесь 💜",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Записаться", callback_data="booking")],
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")],
            ]),
        )
        return ConversationHandler.END

    context.user_data["lesson_request_items"] = []
    await query.edit_message_text(
        "💬 Запрос к занятию\n\n"
        "Напишите, что хотите разобрать с преподавателем. "
        "Можно отправить несколько сообщений и фотографий; к фото можно добавить подпись.\n\n"
        "Когда всё добавите, нажмите «📅 Выбрать занятие».",
        reply_markup=lesson_request_controls(),
    )
    return LESSON_REQUEST_CONTENT


async def lesson_request_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = context.user_data.setdefault("lesson_request_items", [])

    text = None
    photo_file_id = None
    photo_unique_id = None

    if update.message.photo:
        photo = update.message.photo[-1]
        photo_file_id = photo.file_id
        photo_unique_id = photo.file_unique_id
        if update.message.caption:
            text = update.message.caption.strip() or None
    elif update.message.text:
        text = update.message.text.strip() or None

    if not text and not photo_file_id:
        await update.message.reply_text("Добавь текст или фотографию — я аккуратно соберу всё в одно сообщение для преподавателя 💜")
        return LESSON_REQUEST_CONTENT

    items.append({
        "text": text,
        "photo_file_id": photo_file_id,
        "photo_file_unique_id": photo_unique_id,
    })

    await update.message.reply_text(
        f"✅ Добавлено материалов: {len(items)}.\n\n"
        "Можно отправить ещё или выбрать занятие.",
        reply_markup=lesson_request_controls(),
    )
    return LESSON_REQUEST_CONTENT


async def lesson_request_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    items = context.user_data.get("lesson_request_items", [])
    if not items:
        await query.answer("Сначала добавь текст или фотографию 💜", show_alert=True)
        return LESSON_REQUEST_CONTENT

    user = database.get_user_by_telegram_id(update.effective_user.id)
    if user is None:
        return ConversationHandler.END

    lessons = [
        lesson for lesson in database.get_upcoming_lessons(user["id"])
        if lesson["lesson_status"] in {"PENDING", "CONFIRMED"}
    ]
    if not lessons:
        await query.edit_message_text(
            "Предстоящих занятий больше нет.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")]
            ]),
        )
        context.user_data.pop("lesson_request_items", None)
        return ConversationHandler.END

    keyboard = []
    for lesson in lessons[:12]:
        keyboard.append([
            InlineKeyboardButton(
                f"📅 {format_datetime(lesson['start_time'])} · "
                f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}",
                callback_data=f"lesson_request_lesson|{lesson['id']}",
            )
        ])
    keyboard.append([InlineKeyboardButton("⬅️ Добавить ещё", callback_data="lesson_request_back")])
    keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="lesson_request_cancel")])

    await query.edit_message_text(
        "📅 Выбери занятие для запроса\n\n"
        f"Материалов в запросе: {len(items)}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return LESSON_REQUEST_LESSON


async def lesson_request_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    items = context.user_data.get("lesson_request_items", [])
    await query.edit_message_text(
        "💬 Запрос к занятию\n\n"
        f"Сейчас добавлено материалов: {len(items)}.\n"
        "Можешь добавить ещё текст или фото, а затем выбрать занятие 👇",
        reply_markup=lesson_request_controls(),
    )
    return LESSON_REQUEST_CONTENT


async def lesson_request_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = database.get_user_by_telegram_id(update.effective_user.id)
    lesson_id = int(query.data.split("|")[1])
    lesson = database.get_lesson(lesson_id)
    items = context.user_data.get("lesson_request_items", [])

    if (
        user is None or lesson is None or lesson["user_id"] != user["id"]
        or lesson["lesson_status"] not in {"PENDING", "CONFIRMED"}
    ):
        await query.answer("Это занятие уже недоступно. Выбери другое — я покажу актуальные варианты.", show_alert=True)
        return LESSON_REQUEST_LESSON

    if not items:
        await query.answer("Запрос пока пуст. Добавь текст или фотографию — и я смогу его отправить.", show_alert=True)
        return LESSON_REQUEST_CONTENT

    for item in items:
        database.add_lesson_note(
            lesson_id=lesson_id,
            user_id=user["id"],
            text=item["text"],
            photo_file_id=item["photo_file_id"],
            photo_file_unique_id=item["photo_file_unique_id"],
        )

    admin_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📚 Открыть занятие", callback_data=f"admin_lesson_view|{lesson_id}")
    ]])
    header = (
        "💬 НОВЫЙ ЗАПРОС К ЗАНЯТИЮ\n\n"
        f"👤 {user['name']}\n"
        f"📅 {format_datetime(lesson['start_time'])}\n"
        f"📖 {SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n\n"
        f"Материалов: {len(items)}"
    )
    await context.bot.send_message(
        chat_id=admin.ADMIN_ID,
        text=header,
        reply_markup=admin_keyboard,
    )
    for item in items:
        if item["photo_file_id"]:
            await context.bot.send_photo(
                chat_id=admin.ADMIN_ID,
                photo=item["photo_file_id"],
                caption=item["text"] or None,
            )
        elif item["text"]:
            await context.bot.send_message(chat_id=admin.ADMIN_ID, text=item["text"])

    context.user_data.pop("lesson_request_items", None)
    await query.edit_message_text(
        "✅ Готово, я сохранила запрос и отправила его преподавателю.\n\n"
        f"📅 {format_datetime(lesson['start_time'])}\n"
        f"📖 {SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Оставить ещё запрос", callback_data="lesson_request_start")],
            [InlineKeyboardButton("📚 Открыть занятие", callback_data=f"lesson_view|{lesson_id}")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main")],
        ]),
    )
    return ConversationHandler.END


async def lesson_request_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("lesson_request_items", None)
    await query.edit_message_text("Хорошо, запрос отменён 💜", reply_markup=student_menu())
    return ConversationHandler.END


# ============================================================
# КОММЕНТАРИЙ К ПРЕДСТОЯЩЕМУ ЗАНЯТИЮ
# ============================================================

async def lesson_note_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = (
        database
        .get_user_by_telegram_id(
            update.effective_user.id
        )
    )

    lesson_id = int(
        query.data.split("|")[1]
    )

    lesson = database.get_lesson(
        lesson_id
    )

    if (
        user is None
        or lesson is None
        or lesson["user_id"] != user["id"]
        or lesson["lesson_status"]
            not in {
                "PENDING",
                "CONFIRMED",
            }
    ):

        await query.answer(
            "Это занятие уже недоступно "
            "для комментария.",
            show_alert=True,
        )

        return (
            ConversationHandler.END
        )

    context.user_data[
        "lesson_note_id"
    ] = lesson_id

    await query.edit_message_text(
        "💬 ЧТО НУЖНО РАЗОБРАТЬ?\n\n"

        f"📅 {format_datetime(lesson['start_time'])}\n"
        f"📖 "
        f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n\n"

        "Напишите преподавателю, что хотите "
        "изучить или повторить на занятии.\n\n"

        "Можно также отправить фотографию "
        "задачи, страницы учебника или другого "
        "материала. К фотографии можно добавить "
        "подпись.\n\n"

        "Если материалов несколько — после "
        "сохранения можно нажать эту кнопку "
        "ещё раз."
    )

    return LESSON_NOTE


async def lesson_note_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = (
        database
        .get_user_by_telegram_id(
            update.effective_user.id
        )
    )

    lesson_id = context.user_data.get(
        "lesson_note_id"
    )

    if (
        user is None
        or not lesson_id
    ):

        return (
            ConversationHandler.END
        )

    lesson = database.get_lesson(
        lesson_id
    )

    if (
        lesson is None
        or lesson["user_id"] != user["id"]
    ):

        return (
            ConversationHandler.END
        )

    note_text = None
    photo_file_id = None
    photo_unique_id = None

    if update.message.photo:

        photo = (
            update.message.photo[-1]
        )

        photo_file_id = (
            photo.file_id
        )

        photo_unique_id = (
            photo.file_unique_id
        )

        note_text = (
            update.message.caption.strip()
            if update.message.caption
            else None
        )

    elif update.message.text:

        note_text = (
            update.message.text.strip()
        )

    try:

        database.add_lesson_note(
            lesson_id=lesson_id,
            user_id=user["id"],
            text=note_text,
            photo_file_id=photo_file_id,
            photo_file_unique_id=photo_unique_id,
        )

    except Exception as error:

        await update.message.reply_text(
            f"❌ {error}"
        )

        return LESSON_NOTE

    admin_caption = (
        "💬 УЧЕНИК ОСТАВИЛ МАТЕРИАЛ "
        "К ЗАНЯТИЮ\n\n"

        f"👤 {user['name']}\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n"

        f"📖 "
        f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}"
    )

    if note_text:

        admin_caption += (
            "\n\n💬 "
            + note_text
        )

    admin_keyboard = (
        InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть занятие",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ]
        ])
    )

    try:

        if photo_file_id:

            await context.bot.send_photo(
                chat_id=admin.ADMIN_ID,
                photo=photo_file_id,
                caption=admin_caption,
                reply_markup=admin_keyboard,
            )

        else:

            await context.bot.send_message(
                chat_id=admin.ADMIN_ID,
                text=admin_caption,
                reply_markup=admin_keyboard,
            )

    except Exception as error:

        print(
            "LESSON NOTE ADMIN NOTIFY:",
            repr(error),
        )

    context.user_data.pop(
        "lesson_note_id",
        None,
    )

    await update.message.reply_text(
        "✅ Готово, я отправила материал преподавателю. 💜\n\nОн увидит его заранее в карточке твоего занятия.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➕ Добавить ещё материал",
                    callback_data=(
                        f"lesson_note_start|{lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Вернуться к занятию",
                    callback_data=(
                        f"lesson_view|{lesson_id}"
                    ),
                )
            ],
        ]),
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# БОЛЬНИЧНЫЙ — НАЧАЛО
# ============================================================

async def sickness_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    await query.answer()

    lesson_id = int(
        query.data.split("|")[1]
    )

    user = (
        database
        .get_user_by_telegram_id(
            update.effective_user.id
        )
    )

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if (
        not user
        or
        not lesson
        or
        lesson[
            "user_id"
        ] != user["id"]
    ):

        return (
            ConversationHandler.END
        )

    context.user_data[
        "sickness_lesson_id"
    ] = lesson_id

    await query.edit_message_text(
        "🤒 БОЛЬНИЧНЫЙ\n\n"

        "Коротко напишите, что случилось.\n\n"

        "Например:\n"
        "«Температура 38»"
    )

    return SICKNESS_COMMENT


# ============================================================
# БОЛЬНИЧНЫЙ — КОММЕНТАРИЙ
# ============================================================

async def sickness_comment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    comment = (
        update.message.text
        .strip()
    )

    if len(comment) < 2:

        await update.message.reply_text(
            "Напиши короткий комментарий, чтобы я могла передать преподавателю детали."
        )

        return SICKNESS_COMMENT

    lesson_id = (
        context.user_data[
            "sickness_lesson_id"
        ]
    )

    context.user_data[
        "sickness_comment"
    ] = comment

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    hours_left = (
        database
        .get_hours_until_lesson(
            lesson
        )
    )

    if hours_left >= 2:

        warning = (
            "До занятия больше 2 часов."
        )

    else:

        warning = (
            "⚠️ До занятия меньше 2 часов.\n"
            "Решение о списании примет преподаватель."
        )

    await update.message.reply_text(
        "🤒 Подтверждение больничного\n\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n\n"

        f"💬 "
        f"{comment}\n\n"

        f"{warning}",

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=(
                            f"sickness_confirm|"
                            f"{lesson_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Отмена",
                        callback_data=(
                            f"lesson_view|"
                            f"{lesson_id}"
                        )
                    )
                ]
            ])
        )
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# ПОДТВЕРДИТЬ БОЛЬНИЧНЫЙ
# ============================================================

async def confirm_sickness(
    query,
    context,
    user,
    lesson_id
):

    comment = (
        context.user_data.get(
            "sickness_comment",
            "Без комментария"
        )
    )

    try:

        result = (
            database
            .request_sickness(
                lesson_id,
                user["id"],
                comment
            )
        )

    except Exception as error:

        await query.edit_message_text(
            f"❌ {error}"
        )

        return

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if lesson[
        "google_event_id"
    ]:

        deleted = await asyncio.to_thread(
            delete_google_event,
            lesson[
                "google_event_id"
            ]
        )

        if deleted:
            save_google_event_id(
                lesson_id,
                None,
            )

    if (
        result[
            "needs_admin_decision"
        ]
    ):

        student_text = (
            "🤒 БОЛЬНИЧНЫЙ ОТПРАВЛЕН\n\n"

            "Преподаватель получил "
            "ваш комментарий.\n\n"

            "Решение о списании занятия "
            "будет принято преподавателем."
        )

        admin_keyboard = (
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "💳 Списать занятие",
                        callback_data=(
                            f"sys_sick_charge|"
                            f"{lesson_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "🎟 Не списывать / вернуть",
                        callback_data=(
                            f"sys_sick_refund|"
                            f"{lesson_id}"
                        )
                    )
                ]
            ])
        )

    else:

        student_text = (
            "🤒 БОЛЬНИЧНЫЙ ОФОРМЛЕН\n\n"

            f"Это ваш больничный №"
            f"{result['sickness_number']} "
            "в этом месяце.\n\n"

            "Я вернула занятие на баланс."
        )

        admin_keyboard = None

    try:
        database.prepare_lesson_for_forced_reschedule(
            lesson_id,
            "STUDENT_SICKNESS_RESCHEDULE",
        )
    except Exception as error:
        print("SICKNESS RESCHEDULE PREP:", repr(error))

    await query.edit_message_text(
        student_text
        + "\n\n🔁 Это занятие нужно перенести. "
        "Можешь выбрать новое время сейчас или вернуться к этому позже.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📅 Выбрать новое время",
                    callback_data=f"reschedule_free|{lesson_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⏳ Выбрать позже",
                    callback_data="main"
                )
            ]
        ])
    )

    await context.bot.send_message(

        chat_id=(
            admin.ADMIN_ID
        ),

        text=(
            "🤒 БОЛЬНИЧНЫЙ\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"📅 "
            f"{format_datetime(lesson['start_time'])}\n"

            f"💬 "
            f"{comment}\n\n"

            f"Больничный №"
            f"{result['sickness_number']} "
            "за месяц."
        ),

        reply_markup=(
            admin_keyboard
        )
    )

    context.user_data.pop(
        "sickness_comment",
        None
    )

    context.user_data.pop(
        "sickness_lesson_id",
        None
    )


# ============================================================
# НАПОМИНАНИЕ О ПЕРЕНОСЕ
# ============================================================

async def pending_reschedule_reminder_job(
    context: ContextTypes.DEFAULT_TYPE
):

    rows = database.get_due_reschedule_reminders()

    for item in rows:

        if not item["telegram_id"]:
            database.mark_reschedule_reminded(
                item["lesson_id"]
            )
            continue

        try:

            await context.bot.send_message(
                chat_id=item["telegram_id"],
                text=(
                    "🔁 Напомню про перенос\n\n"
                    f"Исходное занятие: "
                    f"{format_datetime(item['start_time'])}\n\n"
                    "Новое время пока не выбрано. Я могу показать свободные варианты прямо сейчас.",
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📅 Выбрать новое время",
                            callback_data=(
                                f"reschedule_free|{item['lesson_id']}"
                            )
                        )
                    ]
                ]),
            )

            database.mark_reschedule_reminded(
                item["lesson_id"]
            )

        except Exception as error:
            print("RESCHEDULE REMINDER:", repr(error))


# ============================================================
# БОЛЬНИЧНЫЙ — РЕШЕНИЕ АДМИНА
# ============================================================

async def system_admin_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    if (
        not admin.is_admin(update)
    ):

        await query.answer(
            "Нет доступа.",
            show_alert=True
        )

        return

    await query.answer()

    data = (
        query.data
    )

    if data.startswith(
        "sys_sick_charge|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        result = (
            database
            .resolve_sickness(
                lesson_id,
                charge=True
            )
        )

        lesson = (
            database
            .get_lesson(
                lesson_id
            )
        )

        user = (
            database
            .get_user(
                lesson["user_id"]
            )
        )

        await query.edit_message_text(
            "💳 Больничный отмечен "
            "со списанием занятия."
        )

        if user[
            "telegram_id"
        ]:

            await context.bot.send_message(

                chat_id=(
                    user[
                        "telegram_id"
                    ]
                ),

                text=(
                    "🤒 Решение по больничному\n\n"
                    "Преподаватель подтвердил списание занятия. Если останутся вопросы, напиши ему — я передам сообщение.",
                )
            )

        return


    if data.startswith(
        "sys_sick_refund|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        result = (
            database
            .resolve_sickness(
                lesson_id,
                charge=False
            )
        )

        lesson = (
            database
            .get_lesson(
                lesson_id
            )
        )

        user = (
            database
            .get_user(
                lesson["user_id"]
            )
        )

        await query.edit_message_text(
            "🎟 Занятие не списано / возвращено."
        )

        if user[
            "telegram_id"
        ]:

            await context.bot.send_message(

                chat_id=(
                    user[
                        "telegram_id"
                    ]
                ),

                text=(
                    "🤒 Решение по больничному\n\n"
                    "Занятие не списано. Я вернула минуты на твой доступный баланс 💜",
                )
            )

        return


# ============================================================
# ОСНОВНЫЕ КНОПКИ УЧЕНИКА
# ============================================================

async def student_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    await query.answer()

    # Админские callback здесь не обрабатываем,
    # кроме активного Test Lab в роли ученика.
    test_student_mode = (
        core_test_lab.active(update.effective_user.id)
        and (
            core_test_lab._is_tester_prod(update.effective_user.id)
            or admin_roles.is_owner(update.effective_user.id)
        )
        and core_test_lab.get_test_role(update.effective_user.id) == "STUDENT"
    )

    if admin.is_admin(update) and not test_student_mode:
        return

    user = (
        database
        .get_user_by_telegram_id(
            update.effective_user.id
        )
    )

    data = (
        query.data
    )

    if str(data).startswith("single_draft"):
        print(
            "DEBUG STUDENT CALLBACK:",
            data,
            "tid=",
            update.effective_user.id,
            flush=True,
        )

    parent_mode = False
    parent = None
    if not user:
        parent = database.get_parent_by_telegram_id(update.effective_user.id)
        student_id = context.user_data.get("parent_acting_student_id")
        allowed_callbacks = (
            data == "main"
            or data == "booking"
            or data.startswith("booking_program|")
            or data == "booking_single"
            or data == "booking_regular"
            or data.startswith("regular_day|")
            or data.startswith("regular_time|")
            or data.startswith("regular_until|")
            or data == "regular_confirm"
            or data.startswith("date|normal|")
            or data.startswith("time|normal|")
            or data.startswith("pending_cancel|")
            or data.startswith("reschedule_start|")
            or data.startswith("reschedule_free|")
            or data.startswith("reschedule_late_warning|")
            or data.startswith("reschedule_late_confirm|")
            or data.startswith("date|reschedule|")
            or data.startswith("time|reschedule|")
            or data.startswith("lesson_view|")
        )
        if parent and parent["active"] and student_id and allowed_callbacks:
            allowed_ids = {row["id"] for row in database.get_parent_students(parent["id"])}
            if student_id in allowed_ids:
                user = database.get_user(student_id)
                parent_mode = bool(user and user["active"])

    if not user:
        await query.message.reply_text("Сначала нажми /start, чтобы я могла открыть твой профиль 💜")
        return

    if parent_mode and data == "main":
        await show_parent_child_card(query, parent, user)
        return


    # ========================================================
    # MAIN
    # ========================================================

    if data == "main":

        await query.edit_message_text(
            "💜 Я рядом. Что сделаем дальше? Выбери нужный раздел 👇",

            reply_markup=(
                student_menu(user["id"])
            )
        )

        return

    if data == "teacher_contact":
        await show_teacher_contact(query, back_callback="main")
        return


    # ========================================================
    # ФОРМУЛЫ
    # ========================================================

    if data == "formulas":
        await formula_study.show_home(query, user)
        return

    if data == "ege_formulas":
        await show_ege_sections(query)
        return

    if data.startswith("ege_section|"):
        section_key = data.split("|", 1)[1]
        await show_ege_topics(query, section_key)
        return

    if data.startswith("ege_topic|"):
        _, section_key, topic_key = data.split("|", 2)
        section = EGE_FORMULA_LIBRARY.get(section_key)
        item = section.get("topics", {}).get(topic_key) if section else None
        if not item:
            await query.answer("Эта тема пока недоступна. Я добавлю её, как только материалы будут готовы 💜", show_alert=True)
            return
        await query.edit_message_text(
            item["text"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К темам", callback_data=f"ege_section|{section_key}")],
                [InlineKeyboardButton("🏠 Формулы", callback_data="formulas")],
            ]),
        )
        return

    if data == "reference_physics":
        await show_reference_topics(query, "physics")
        return

    if data == "reference_chemistry":
        await show_reference_topics(query, "chemistry")
        return

    if data.startswith("reference_topic|"):
        _, kind, topic = data.split("|", 2)
        library = PHYSICS_REFERENCE if kind == "physics" else CHEMISTRY_REFERENCE
        item = library.get(topic)
        if not item:
            await query.answer("Этот раздел пока недоступен. Я добавлю его, как только материалы будут готовы 💜", show_alert=True)
            return
        await query.edit_message_text(
            item["text"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К справочнику", callback_data=f"reference_{kind}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main")],
            ]),
        )
        return

    if data.startswith("formula_grade|"):
        grade = int(data.split("|")[1])
        if grade not in FORMULA_LIBRARY:
            await query.answer("Для этого класса материалы ещё не добавлены.", show_alert=True)
            return
        await show_formula_subjects(query, grade)
        return

    if data.startswith("formula_subject|"):
        _, grade_raw, subject = data.split("|", 2)
        grade = int(grade_raw)
        if subject not in FORMULA_LIBRARY.get(grade, {}):
            await query.answer("Материалы пока не добавлены. Я покажу их здесь, как только они появятся 💜", show_alert=True)
            return
        await show_formula_topics(query, grade, subject)
        return

    if data.startswith("formula_topic|"):
        _, grade_raw, subject, topic = data.split("|", 3)
        grade = int(grade_raw)
        item = FORMULA_LIBRARY.get(grade, {}).get(subject, {}).get(topic)
        if not item:
            await query.answer("Эта тема пока недоступна. Я добавлю её, как только материалы будут готовы 💜", show_alert=True)
            return
        await query.edit_message_text(
            item["text"],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К темам", callback_data=f"formula_subject|{grade}|{subject}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main")],
            ]),
        )
        return

    # ========================================================
    # PROFILE
    # ========================================================

    if data == "profile":

        await show_profile(
            query,
            user
        )

        return

    if data == "student_parents":
        parents = database.get_student_parents(user["id"])
        lines = ["👨‍👩‍👧 РОДИТЕЛИ", ""]
        kb = []
        if parents:
            for i, parent_item in enumerate(parents[:2], 1):
                lines.append(f"{i}. {parent_item['name']}")
                kb.append([InlineKeyboardButton(f"❌ Отвязать: {parent_item['name']}", callback_data=f"student_parent_unlink|{parent_item['id']}")])
        else:
            lines.append("Пока никто не привязан.")
        lines += ["", f"Можно привязать до 2 родителей. Сейчас: {len(parents)}/2."]
        if len(parents) < 2: kb.append([InlineKeyboardButton("➕ Привязать родителя", callback_data="student_parent_link_code")])
        kb.append([InlineKeyboardButton("⬅️ Профиль", callback_data="profile")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb)); return

    if data.startswith("student_parent_unlink|"):
        parent_id = int(data.split("|", 1)[1])
        linked = {p["id"]: p for p in database.get_student_parents(user["id"])}
        if parent_id not in linked:
            await query.answer("Привязка уже отсутствует.", show_alert=True); return
        parent_item = linked[parent_id]
        database.unlink_parent_from_student(parent_id, user["id"])
        try: await context.bot.send_message(chat_id=parent_item["telegram_id"], text=f"ℹ️ {user['name']} отменил(а) привязку вашего родительского аккаунта.")
        except Exception as error: print("UNLINK PARENT NOTIFY ERROR:", repr(error))
        await query.answer("Родитель отвязан.")
        await show_profile(query, user); return

    if data == "student_parent_link_code":
        parents = database.get_student_parents(user["id"])
        if len(parents) >= 2:
            await query.answer("Уже привязаны 2 родителя — это максимум.", show_alert=True); return
        code = database.get_or_create_student_link_code(user["id"])
        lines = [
            "👨‍👩‍👧 ПРИВЯЗКА РОДИТЕЛЯ",
            "",
            "Передайте родителю этот код:",
            f"🔑 {code}",
            "",
            "Родитель вводит его при регистрации или через «Привязать ученика».",
            "Ваши права и возможности в боте при этом не меняются.",
        ]
        if parents:
            lines.extend(["", f"Сейчас привязано родителей: {len(parents)}"])
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Профиль", callback_data="profile")]]),
        )
        return

    if data == "my_stats":
        await show_learning_stats(query, user, parent_view=False)
        return

    if data == "parent_stats":
        await show_learning_stats(query, user, parent_view=True)
        return


    # ========================================================
    # BOOKING
    # ========================================================

    if data == "booking":

        programs = get_active_programs(user["id"])

        if len(programs) > 1:
            await show_program_picker(query, user)

        elif len(programs) == 1:
            context.user_data["selected_program_id"] = programs[0]["id"]
            await show_booking_type(query, user)

        else:
            await query.edit_message_text(
                "Пока у тебя нет активных направлений. Напиши преподавателю — я помогу передать вопрос 💜",
                reply_markup=student_menu(),
            )

        return

    if data.startswith("booking_program|"):

        program_id = int(data.split("|")[1])
        program = database.get_student_program(program_id)

        if (
            program is None
            or program["user_id"] != user["id"]
            or not program["active"]
        ):
            await query.answer("Это направление сейчас недоступно. Выбери другое — я покажу актуальные варианты.", show_alert=True)
            return

        context.user_data["selected_program_id"] = program_id
        await show_booking_type(query, user)
        return


    # ========================================================
    # SINGLE BOOKING
    # ========================================================

    if data == "booking_single":

        pending = database.get_pending_booking(
            user["id"]
        )

        if pending:
            await show_booking_type(query, user)
            return

        program = selected_program(context, user)

        if program is None:
            await show_program_picker(query, user)
            return

        rate = int(database.get_program_rate_info(program["id"])["effective_rate"])
        balance = minute_balance.get_balance(user["id"], hourly_rate=rate)

        # Разовую запись не блокируем по балансу.
        # Оплату выбираем после конкретных даты и времени.
        await show_booking_duration_picker(query, program)
        return

    if data.startswith("booking_duration|"):
        program = selected_program(context, user)
        if program is None:
            await show_program_picker(query, user)
            return
        base = program_duration(program)
        try:
            duration = int(data.split("|", 1)[1])
        except Exception:
            duration = base
        if duration < base:
            await query.answer("Нельзя выбрать меньше основного времени.", show_alert=True)
            return
        rate = int(database.get_program_rate_info(program["id"])["effective_rate"])
        # Баланс проверим после выбора конкретного слота.
        context.user_data["booking_duration"] = duration
        await show_dates(query, user, mode="normal")
        return


    # ========================================================
    # SINGLE BOOKING DRAFT
    # ========================================================

    if data == "single_draft_change_time":
        draft_id = context.user_data.get("single_booking_draft_id")
        draft = (
            database.get_booking_draft(draft_id, user["id"])
            if draft_id
            else database.get_active_booking_draft(user["id"])
        )

        if not draft:
            await query.edit_message_text(
                "Черновик записи уже не найден. Давай выберем занятие заново 💜",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "➕ Записаться",
                            callback_data="booking",
                        )
                    ]
                ]),
            )
            return

        await show_dates(
            query,
            user,
            mode="normal",
        )
        return

    if data == "single_draft_cancel":
        draft_id = context.user_data.get("single_booking_draft_id")

        if draft_id:
            database.cancel_booking_draft(
                draft_id,
                user["id"],
            )
        else:
            draft = database.get_active_booking_draft(user["id"])
            if draft:
                database.cancel_booking_draft(
                    draft["id"],
                    user["id"],
                )

        context.user_data.pop(
            "single_booking_draft_id",
            None,
        )
        context.user_data.pop(
            "booking_duration",
            None,
        )
        context.user_data.pop(
            "booking_start",
            None,
        )
        context.user_data.pop(
            "booking_mode",
            None,
        )

        await query.edit_message_text(
            "Хорошо, разовую запись отменила 💜\n\n"
            "Если захочешь выбрать другое время — просто начни запись снова.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Записаться",
                        callback_data="booking",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 Главная",
                        callback_data="main",
                    )
                ],
            ]),
        )
        return

    if data == "single_draft_pay":
        draft_id = context.user_data.get("single_booking_draft_id")
        draft = (
            database.get_booking_draft(draft_id, user["id"])
            if draft_id
            else database.get_active_booking_draft(user["id"])
        )

        if not draft:
            await query.answer(
                "Я не нашла черновик занятия. Давай выберем время ещё раз.",
                show_alert=True,
            )
            return

        # Повторное нажатие не должно создавать второй платёж.
        payment_id = draft["payment_id"]

        if payment_id:
            payment = database.get_payment(payment_id)
            if (
                payment is None
                or int(payment["user_id"]) != int(user["id"])
                or payment["status"] in ("REJECTED", "CANCELLED")
            ):
                payment_id = None

        if not payment_id:
            payment_id = database.create_payment(
                user_id=user["id"],
                study_goal=draft["study_goal"],
                subject=draft["subject"],
                lessons_count=1,
                price_per_lesson=draft["price"],
                lesson_id=None,
                minutes_total=draft["duration_minutes"],
                base_duration_minutes=draft["duration_minutes"],
                hourly_rate=draft["hourly_rate"],
                program_id=draft["program_id"],
            )

            database.update_booking_draft(
                draft["id"],
                status="PAYMENT_PENDING",
                payment_choice="SINGLE",
                payment_id=payment_id,
            )

        context.user_data["single_booking_draft_id"] = draft["id"]
        context.user_data["single_booking_payment_id"] = payment_id

        payment = database.get_payment(payment_id)

        await query.edit_message_text(
            "💳 ОПЛАТА ЗАНЯТИЯ\n\n"
            f"💰 К оплате: {payments.money(payment['total_amount'])}\n\n"
            + payments.payment_method_text()
            + "\n\n"
            "После перевода прикрепи чек к этой заявке.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📎 Прикрепить чек",
                        callback_data=f"single_draft_receipt|{payment_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Вернуться к заявке",
                        callback_data="single_draft_back",
                    )
                ],
            ]),
        )
        return

    if data == "single_draft_subscription":
        # Не теряем выбранную разовую запись.
        draft_id = context.user_data.get(
            "single_booking_draft_id"
        )

        if draft_id:
            context.user_data[
                "pending_single_draft_after_subscription"
            ] = int(draft_id)

        await query.edit_message_text(
            "🎟 Абонемент\n\n"
            "Выбери тариф и количество занятий. "
            "После подтверждения оплаты минуты появятся на балансе, "
            "и их можно будет использовать для записи.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🎟 Выбрать абонемент",
                        callback_data="payment_subscription",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ К заявке",
                        callback_data="single_draft_back",
                    )
                ],
            ]),
        )
        return

    if data == "single_draft_balance":
        draft_id = context.user_data.get(
            "single_booking_draft_id"
        )

        draft = (
            database.get_booking_draft(
                draft_id,
                user["id"],
            )
            if draft_id
            else database.get_active_booking_draft(
                user["id"]
            )
        )

        if not draft:
            await query.answer(
                "Я не нашла эту заявку. Выбери время ещё раз.",
                show_alert=True,
            )
            return

        duration = int(
            draft["duration_minutes"]
        )
        hourly_rate = int(
            draft["hourly_rate"]
        )

        balance = minute_balance.get_balance(
            user["id"],
            hourly_rate=hourly_rate,
        )

        if int(balance["total"]) < duration:
            await query.answer(
                f"На балансе сейчас {balance['total']} мин, "
                f"а для занятия нужно {duration} мин.",
                show_alert=True,
            )
            return

        try:
            lesson_id = database.create_lesson_request(
                user_id=user["id"],
                program_id=draft["program_id"],
                study_goal=draft["study_goal"],
                subject=draft["subject"],
                start_time=draft["start_time"],
                end_time=draft["end_time"],
                duration_minutes=duration,
                hourly_rate=hourly_rate,
                price=int(draft["price"]),
                is_trial=False,
            )

            database.update_booking_draft(
                draft["id"],
                status="SUBMITTED",
                payment_choice="BALANCE",
            )

        except Exception as error:
            await query.answer(
                str(error),
                show_alert=True,
            )
            return

        local_start = user_timezone.convert_for_user(
            draft["start_time"],
            int(query.from_user.id),
            TIMEZONE_NAME,
        )

        if local_start is None:
            local_start = datetime.fromisoformat(
                draft["start_time"]
            )

        subject_name = SUBJECT_NAMES.get(
            draft["subject"],
            draft["subject"],
        )

        await query.edit_message_text(
            "✅ Заявка отправлена преподавателю 💜\n\n"
            f"📚 {subject_name}\n"
            f"📅 {local_start.strftime('%d.%m.%Y')}\n"
            f"🕐 {local_start.strftime('%H:%M')}\n"
            f"⏱ {duration} минут\n\n"
            "Минуты пока не списаны. "
            "Они будут зарезервированы после подтверждения занятия преподавателем.",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📚 Мои занятия",
                        callback_data="lessons",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🏠 Главная",
                        callback_data="main",
                    )
                ],
            ]),
        )

        # Используем тот же admin request flow, который уже
        # обрабатывает обычные ученические заявки.
        await context.bot.send_message(
            chat_id=admin.ADMIN_ID,
            text=(
                "📅 НОВАЯ ЗАЯВКА НА ЗАНЯТИЕ\n\n"
                f"👤 {user['name']}\n"
                f"📚 {subject_name}\n"
                f"📅 {local_start.strftime('%d.%m.%Y')}\n"
                f"🕐 {local_start.strftime('%H:%M')}\n"
                f"⏱ {duration} минут\n"
                f"🎟 Оплата: с баланса\n\n"
                f"Заявка #{lesson_id}"
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=(
                            f"admin_request_approve|{lesson_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=(
                            f"admin_request_reject|{lesson_id}"
                        ),
                    )
                ],
            ]),
        )

        return


    # ========================================================
    # REGULAR BOOKING
    # ========================================================

    if data == "booking_regular":

        if database.student_has_pending_regular_schedule(user["id"]):
            await show_booking_type(query, user)
            return

        await show_regular_weekdays(
            query,
            context,
            user,
        )
        return


    if data.startswith("regular_day|"):

        weekday = int(data.split("|")[1])
        await show_regular_times(
            query,
            context,
            user,
            weekday,
        )
        return


    if data.startswith("regular_time|"):

        parts = data.split("|")
        weekday = int(parts[1])
        start_time = parts[2]

        await show_regular_periods(
            query,
            context,
            user,
            weekday,
            start_time,
        )
        return


    if data.startswith("regular_until|"):

        end_date = data.split("|")[1]

        await show_regular_confirmation(
            query,
            context,
            user,
            end_date,
        )
        return


    if data == "regular_confirm":

        await create_regular_request(
            query,
            context,
            user,
        )
        return


    # ========================================================
    # TRIAL
    # ========================================================

    if data == "trial":

        if (
            database
            .has_used_trial(
                user["id"]
            )
        ):

            await query.edit_message_text(
                "🎁 Пробное занятие "
                "уже использовано.",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "⬅️ Главное меню",
                                callback_data=(
                                    "main"
                                )
                            )
                        ]
                    ])
                )
            )

            return

        await show_dates(
            query,
            user,
            mode="trial"
        )

        return


    # ========================================================
    # DATE
    # ========================================================

    if data.startswith(
        "date|"
    ):

        parts = (
            data.split("|")
        )

        mode = (
            parts[1]
        )

        selected_date = (
            datetime.strptime(
                parts[2],
                "%Y-%m-%d"
            ).date()
        )

        old_lesson_id = (
            int(parts[3])
            if len(parts) > 3
            else None
        )

        await show_free_times(
            query,
            user,
            selected_date,
            mode=mode,
            old_lesson_id=old_lesson_id,
            duration_override=(context.user_data.get("booking_duration") if mode == "normal" else None),
        )

        return


    # ========================================================
    # TIME
    # ========================================================

    if data.startswith(
        "time|"
    ):

        parts = (
            data.split("|")
        )

        mode = (
            parts[1]
        )

        selected_date = (
            datetime.strptime(
                parts[2],
                "%Y-%m-%d"
            ).date()
        )

        start_dt = (
            time_to_datetime(
                selected_date,
                parts[3]
            )
        )

        old_lesson_id = (
            int(parts[4])
            if len(parts) > 4
            else None
        )

        # ====================================================
        # FREE RESCHEDULE
        # ====================================================

        if mode == "reschedule":

            old_lesson = (
                database
                .get_lesson(
                    old_lesson_id
                )
            )

            duration = (
                old_lesson[
                    "duration_minutes"
                ]
            )

            end_dt = (
                start_dt
                + timedelta(
                    minutes=duration
                )
            )

            try:

                new_lesson_id = (
                    database
                    .free_reschedule_lesson(

                        old_lesson_id,

                        start_dt.isoformat(),

                        end_dt.isoformat()
                    )
                )

            except Exception as error:

                await query.edit_message_text(
                    f"❌ {error}"
                )

                return

            new_lesson = (
                database
                .get_lesson(
                    new_lesson_id
                )
            )

            await notify_student_if_parent_action(
                query, context, user,
                "🔁 Готово, я перенесла занятие.\n"
                f"Было: {format_datetime(old_lesson['start_time'])}.\n"
                f"Стало: {format_datetime(new_lesson['start_time'])}."
            )
            await notify_parents_schedule(
                context,
                user,
                (
                    "🔁 Готово, я перенесла занятие.\n"
                    f"Было: {format_datetime(old_lesson['start_time'])}.\n"
                    f"Стало: {format_datetime(new_lesson['start_time'])}."
                ),
            )

            # Google Calendar:
            # при переносе сохраняем то же событие,
            # просто меняем дату/время и переносим его ID
            # на новое занятие.
            try:

                old_event_id = (
                    old_lesson[
                        "google_event_id"
                    ]
                )

                if old_event_id:

                    event_id = (
                        await asyncio.to_thread(
                            update_google_event,
                            old_event_id,
                            user,
                            new_lesson,
                        )
                    )

                    save_google_event_id(
                        old_lesson_id,
                        None,
                    )

                    save_google_event_id(
                        new_lesson_id,
                        event_id,
                    )

                else:

                    event_id = (
                        await asyncio.to_thread(
                            create_google_event,
                            user,
                            new_lesson,
                        )
                    )

                    save_google_event_id(
                        new_lesson_id,
                        event_id,
                    )

            except Exception as error:

                print(
                    "RESCHEDULE GOOGLE:",
                    repr(error)
                )

            schedule_lesson_reminders(
                context.application,
                new_lesson_id
            )

            await query.edit_message_text(
                "✅ Готово, я перенесла занятие 💜\n\n"

                f"📅 "
                f"{start_dt.strftime('%d.%m.%Y')}\n"

                f"🕐 "
                f"{start_dt.strftime('%H:%M')}\n\n"

                "Перенос выполнен бесплатно. "
                "Дополнительное занятие "
                "с баланса не списывалось."
            )

            await context.bot.send_message(

                chat_id=(
                    admin.ADMIN_ID
                ),

                text=(
                    "🔁 УЧЕНИК ПЕРЕНЁС ЗАНЯТИЕ\n\n"

                    f"👤 "
                    f"{user['name']}\n"

                    f"📅 Новое время: "
                    f"{start_dt.strftime('%d.%m.%Y %H:%M')}\n\n"

                    "Перенос выполнен более чем "
                    "за 2 часа — бесплатно."
                )
            )

            return


        # ====================================================
        # НОВАЯ ЗАЯВКА
        # ====================================================

        context.user_data[
            "booking_start"
        ] = (
            start_dt.isoformat()
        )

        context.user_data[
            "booking_mode"
        ] = mode

        if mode == "trial":

            duration = 45

            text = (
                "🎁 Проверь пробное занятие\n\n"

                f"📅 "
                f"{start_dt.strftime('%d.%m.%Y')}\n"

                f"🕐 "
                f"{start_dt.strftime('%H:%M')}\n"

                "⏱ 45 минут\n"
                "💰 Бесплатно\n\n"

                "Всё верно? Тогда я отправлю заявку преподавателю."
            )

        else:

            price_info = (
                payments
                .get_price_per_lesson(
                    user
                )
            )

            text = (
                "📅 Проверь запись\n\n"

                f"📅 "
                f"{start_dt.strftime('%d.%m.%Y')}\n"

                f"🕐 "
                f"{start_dt.strftime('%H:%M')}\n"

                f"⏱ "
                f"{price_info['duration']} минут\n\n"

                "После подтверждения преподавателем я зарезервирую нужное количество минут с баланса."
            )

        await query.edit_message_text(
            text,

            reply_markup=(
                InlineKeyboardMarkup([

                    [
                        InlineKeyboardButton(
                            "✅ Отправить заявку",
                            callback_data=(
                                "request_confirm"
                            )
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "❌ Отмена",
                            callback_data=(
                                "main"
                            )
                        )
                    ]
                ])
            )
        )

        return


    # ========================================================
    # CONFIRM REQUEST
    # ========================================================

    if data == "request_confirm":

        value = (
            context.user_data.get(
                "booking_start"
            )
        )

        mode = (
            context.user_data.get(
                "booking_mode",
                "normal"
            )
        )

        if not value:

            await query.edit_message_text(
                "Кажется, выбранное время потерялось. Выбери его ещё раз — я сохраню новый вариант 💜"
            )

            return

        start_dt = (
            datetime.fromisoformat(
                value
            )
        )

        if mode == "normal":
            await show_single_booking_draft(
                query,
                context,
                user,
                start_dt,
            )
        else:
            await create_student_request(
                query,
                context,
                user,
                start_dt,
                trial=(
                    mode == "trial"
                ),
            )
        context.user_data.pop(
            "booking_start",
            None
        )

        context.user_data.pop(
            "booking_mode",
            None
        )

        return


    # ========================================================
    # LESSONS
    # ========================================================

    if data == "lessons":

        await show_student_lessons(
            query,
            user
        )

        return


    if data.startswith(
        "lesson_view|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_student_lesson(
            query,
            user,
            lesson_id
        )

        return


    # ========================================================
    # CANCEL PENDING
    # ========================================================

    if data.startswith(
        "pending_cancel|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        try:

            database.cancel_pending_request(
                lesson_id,
                user["id"]
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ {error}"
            )

            return

        await query.edit_message_text(
            "✅ Хорошо, я отменила заявку.\n\nТеперь можно спокойно выбрать другое время 💜",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📅 Записаться",
                            callback_data=(
                                "booking"
                            )
                        )
                    ]
                ])
            )
        )

        return


    # ========================================================
    # RESCHEDULE START
    # ========================================================

    if data.startswith(
        "reschedule_start|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        lesson = (
            database
            .get_lesson(
                lesson_id
            )
        )

        hours_left = (
            database
            .get_hours_until_lesson(
                lesson
            )
        )

        if hours_left >= 2:

            await query.edit_message_text(
                "🔁 Перенос занятия\n\n"

                "До занятия больше 2 часов, поэтому перенос будет бесплатным.\n\n"

                "Выбери новое время — я покажу доступные варианты 👇",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📅 Выбрать новое время",
                                callback_data=(
                                    f"reschedule_free|"
                                    f"{lesson_id}"
                                )
                            )
                        ],

                        [
                            InlineKeyboardButton(
                                "❌ Отмена",
                                callback_data=(
                                    f"lesson_view|"
                                    f"{lesson_id}"
                                )
                            )
                        ]
                    ])
                )
            )

        else:

            await query.edit_message_text(
                "⚠️ Поздний перенос\n\n"

                "До занятия осталось "
                "меньше 2 часов.\n\n"

                "По правилам текущее занятие "
                "будет считаться использованным.\n\n"

                "Для новой записи потребуется "
                "ещё одно занятие с баланса.",

                reply_markup=(
                    InlineKeyboardMarkup([

                        [
                            InlineKeyboardButton(
                                "Продолжить",
                                callback_data=(
                                    f"reschedule_late_warning|"
                                    f"{lesson_id}"
                                )
                            )
                        ],

                        [
                            InlineKeyboardButton(
                                "❌ Отмена",
                                callback_data=(
                                    f"lesson_view|"
                                    f"{lesson_id}"
                                )
                            )
                        ]
                    ])
                )
            )

        return


    # ========================================================
    # FREE RESCHEDULE
    # ========================================================

    if data.startswith(
        "reschedule_free|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_dates(
            query,
            user,
            mode="reschedule",
            old_lesson_id=(
                lesson_id
            )
        )

        return


    # ========================================================
    # LATE WARNING 2
    # ========================================================

    if data.startswith(
        "reschedule_late_warning|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        lesson = (
            database
            .get_lesson(
                lesson_id
            )
        )

        await query.edit_message_text(
            "❗ Последнее подтверждение\n\n"

            f"Текущее занятие:\n"
            f"📅 "
            f"{format_datetime(lesson['start_time'])}\n\n"

            "После подтверждения это занятие "
            "останется списанным.\n\n"

            "Вы уверены?",

            reply_markup=(
                InlineKeyboardMarkup([

                    [
                        InlineKeyboardButton(
                            "✅ Понимаю, перенести и списать",
                            callback_data=(
                                f"reschedule_late_confirm|"
                                f"{lesson_id}"
                            )
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "❌ Не переносить",
                            callback_data=(
                                f"lesson_view|"
                                f"{lesson_id}"
                            )
                        )
                    ]
                ])
            )
        )

        return


    # ========================================================
    # LATE CONFIRM
    # ========================================================

    if data.startswith(
        "reschedule_late_confirm|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        lesson = (
            database
            .get_lesson(
                lesson_id
            )
        )

        try:

            database.mark_late_reschedule(
                lesson_id
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ {error}"
            )

            return

        await notify_student_if_parent_action(
            query, context, user,
            "⚠️ Я оформила поздний перенос.\n"
            f"Занятие {format_datetime(lesson['start_time'])} считается использованным; "
            "ученик сможет выбрать новое время."
        )
        await notify_parents_schedule(
            context,
            user,
            (
                "⚠️ Я оформила поздний перенос.\n"
                f"Занятие {format_datetime(lesson['start_time'])} считается использованным; "
                "ученик сможет выбрать новое время."
            ),
        )

        if lesson[
            "google_event_id"
        ]:

            await asyncio.to_thread(
                delete_google_event,
                lesson[
                    "google_event_id"
                ]
            )

        await context.bot.send_message(

            chat_id=(
                admin.ADMIN_ID
            ),

            text=(
                "⚠️ Поздний перенос\n\n"

                f"👤 "
                f"{user['name']}\n"

                f"📅 "
                f"{format_datetime(lesson['start_time'])}\n\n"

                "Занятие считается использованным."
            )
        )

        await query.edit_message_text(
            "⚠️ Старое занятие учтено как использованное.\n\nТеперь выбери новое время — я помогу оформить запись.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📅 Новая запись",
                            callback_data=(
                                "booking"
                            )
                        )
                    ]
                ])
            )
        )

        return


    # ========================================================
    # SICKNESS CONFIRM
    # ========================================================

    if data.startswith(
        "sickness_confirm|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await confirm_sickness(
            query,
            context,
            user,
            lesson_id
        )

        return


    # ========================================================
    # HOMEWORK
    # ========================================================

    if data == "homework":

        rows = (
            database
            .get_student_homework(
                user["id"],
                active_only=True
            )
        )

        if not rows:

            await query.edit_message_text(
                "📝 Активных домашних "
                "заданий нет.",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "⬅️ Главное меню",
                                callback_data=(
                                    "main"
                                )
                            )
                        ]
                    ])
                )
            )

            return

        keyboard = []

        for item in rows[:20]:

            title = (
                item[
                    "title"
                ]
                or
                f"ДЗ #{item['id']}"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"📝 {title[:35]}",

                    callback_data=(
                        f"homework_view|"
                        f"{item['id']}"
                    )
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "⬅️ Главное меню",
                callback_data=(
                    "main"
                )
            )
        ])

        await query.edit_message_text(
            "📝 ДОМАШНИЕ ЗАДАНИЯ",

            reply_markup=(
                InlineKeyboardMarkup(
                    keyboard
                )
            )
        )

        return


    # ========================================================
    # HOMEWORK VIEW
    # ========================================================

    if data.startswith(
        "homework_view|"
    ):

        homework_id = int(
            data.split("|")[1]
        )

        homework = (
            database
            .get_homework(
                homework_id
            )
        )

        if (
            not homework
            or
            homework[
                "user_id"
            ] != user["id"]
        ):

            return

        text = (
            "📝 ДОМАШНЕЕ ЗАДАНИЕ\n\n"

            f"{homework['description'] or '—'}"
        )

        if homework[
            "deadline"
        ]:

            text += (
                "\n\n⏰ Срок: "
                f"{format_datetime(homework['deadline'])}"
            )

        await query.edit_message_text(
            text,

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ К ДЗ",
                            callback_data=(
                                "homework"
                            )
                        )
                    ]
                ])
            )
        )

        return


# ============================================================
# POST INIT
# ============================================================

async def post_init(
    application
):
    # Consolidated runtime patches must be active before startup sync.
    # This prevents the legacy Google Calendar policy from deleting
    # AWAITING_PAYMENT events before V2 restores them.
    musthave_jobs.runtime_patch_v2.install(application)


    # ========================================================
    # /start ДЛЯ ВСЕХ
    # ========================================================

    await application.bot.set_my_commands(

        [
            BotCommand(
                "start",
                "Открыть меню"
            )
        ],

        scope=(
            BotCommandScopeDefault()
        )
    )


    # ========================================================
    # /admin ТОЛЬКО ТЕБЕ
    # ========================================================

    await application.bot.set_my_commands(

        [
            BotCommand(
                "start",
                "Открыть меню"
            ),

            BotCommand(
                "admin",
                "Панель преподавателя"
            )
        ],

        scope=(
            BotCommandScopeChat(
                chat_id=(
                    admin.ADMIN_ID
                )
            )
        )
    )


    # ========================================================
    # CALLBACK ДЛЯ ADMIN.PY
    # ========================================================

    application.bot_data[
        "schedule_lesson_reminders"
    ] = schedule_lesson_reminders

    application.bot_data[
        "schedule_payment_reminders"
    ] = schedule_payment_reminders

    application.bot_data[
        "schedule_homework_reminder"
    ] = schedule_homework_reminder


    # ========================================================
    # CORE / STAGE 1
    # ========================================================

    await asyncio.to_thread(core_financial_ledger.backfill_existing)

    try:
        await asyncio.to_thread(core_backup_manager.create_backup, "startup", admin.ADMIN_ID)
        await asyncio.to_thread(core_backup_manager.prune, 14)
    except Exception as exc:
        core_event_center.push(
            "STARTUP_BACKUP_ERROR",
            "Не удалось создать backup при запуске",
            str(exc),
            priority="CRITICAL",
            dedupe_key="system:startup_backup_error",
        )

    # ========================================================
    # ВОССТАНОВЛЕНИЕ JOBS
    # ========================================================

    await restore_jobs(
        application
    )

    # ========================================================
    # ВОССТАНОВЛЕНИЕ GOOGLE CALENDAR
    # ========================================================

    await sync_google_calendar(
        application
    )


    # ========================================================
    # ПОСТОЯННЫЕ СЕРИИ
    # ========================================================

    await sync_regular_schedules(
        application
    )

    if application.job_queue:
        # Disabled: full financial ledger backfill must not run every 5 minutes.
        # Ledger remains immutable; incremental entries are written at source.

        application.job_queue.run_repeating(
            core_daily_backup_job,
            interval=24 * 60 * 60,
            first=60 * 60,
            name="core_daily_backup",
        )

        application.job_queue.run_repeating(
            regular_sync_job,
            interval=6 * 60 * 60,
            first=15 * 60,
            name="regular_schedule_sync",
        )

        application.job_queue.run_repeating(
            pending_reschedule_reminder_job,
            interval=60 * 60,
            first=5 * 60,
            name="pending_reschedule_reminders",
        )


        application.job_queue.run_repeating(
            lesson_reminder_watchdog_job,
            interval=60,
            first=20,
            name="lesson_reminder_watchdog",
        )


        application.job_queue.run_repeating(
            google_calendar_sync_job,
            interval=60,
            first=30,
            name="google_calendar_sync",
        )

        application.job_queue.run_repeating(
            automation_jobs.scheduled_messages_job,
            interval=60,
            first=45,
            name="stage3_scheduled_messages",
        )

        application.job_queue.run_repeating(
            automation_jobs.timeline_sync_job,
            interval=6 * 60 * 60,
            first=10 * 60,
            name="stage3_timeline_sync",
        )

        final_jobs.register(application)
        crm_jobs.register(application)
        channel_admin.register_jobs(application)
        musthave_jobs.register(application)


async def core_ledger_sync_job(context):
    try:
        await asyncio.to_thread(core_financial_ledger.backfill_existing)
    except Exception as exc:
        core_event_center.push(
            "LEDGER_SYNC_ERROR",
            "Ошибка синхронизации финансового журнала",
            str(exc),
            priority="CRITICAL",
            dedupe_key="system:ledger_sync_error",
        )


async def core_daily_backup_job(context):
    try:
        path = await asyncio.to_thread(core_backup_manager.create_backup, "daily", admin.ADMIN_ID)
        await asyncio.to_thread(core_backup_manager.prune, 14)
        core_audit_log.log("AUTO_BACKUP", admin.ADMIN_ID, "backup", path)
    except Exception as exc:
        core_event_center.push(
            "BACKUP_ERROR",
            "Не удалось создать автоматическую резервную копию",
            str(exc),
            priority="CRITICAL",
            dedupe_key="system:backup_error",
        )


# ============================================================
# BLOCKED STUDENT GUARD
# ============================================================

async def blocked_student_guard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None or admin_roles.is_admin_id(user.id):
        return
    student = database.get_user_by_telegram_id(user.id)
    if student is None or int(student["active"] or 0):
        return

    text = (
        "⛔️ Доступ к TutorBot временно ограничен.\n\n"
        "Я — Аделия. Преподаватель ограничил доступ к личному кабинету. "
        "Учебные данные сохранены. Если это неожиданно, свяжись с преподавателем напрямую."
    )
    if update.callback_query:
        try:
            await update.callback_query.answer("⛔️ Доступ к TutorBot временно ограничен.", show_alert=True)
        except Exception:
            pass
    elif update.effective_message:
        try:
            await update.effective_message.reply_text(text)
        except Exception:
            pass
    raise ApplicationHandlerStop


# ============================================================
# ERROR
# ============================================================

async def error_handler(
    update,
    context
):

    # Telegram returns this harmless error when a button tries to redraw
    # a message with exactly the same text and keyboard. It is not a bot failure.
    if isinstance(context.error, BadRequest) and "Message is not modified" in str(context.error):
        print("IGNORED TELEGRAM NO-OP: Message is not modified")
        return

    # Short Telegram/httpx connection interruptions are operational noise,
    # not application failures. They are logged to systemd only and must not
    # create a red "critical error" message or an Inbox event.
    if isinstance(context.error, (NetworkError, TimedOut)):
        print("TRANSIENT TELEGRAM NETWORK ERROR:", repr(context.error))
        return

    try:
        core_event_center.push(
            "BOT_ERROR",
            "Критическая ошибка бота",
            repr(context.error),
            priority="CRITICAL",
            dedupe_key=None,
        )
        await context.bot.send_message(
            chat_id=admin.ADMIN_ID,
            text=f"🚨 Критическая ошибка Аделия | TutorBot\n\n{repr(context.error)[:3000]}",
        )
    except Exception:
        pass

    print(
        "\n================================"
    )

    print(
        "❌ BOT ERROR:"
    )

    print(
        repr(
            context.error
        )
    )

    # Полный traceback нужен для поиска реальной строки падения.
    import traceback
    traceback.print_exception(
        type(context.error),
        context.error,
        context.error.__traceback__,
    )

    print(
        "================================\n"
    )


# ============================================================
# CANCEL
# ============================================================

async def cancel_registration(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    context.user_data.clear()

    await update.message.reply_text(
        "Отменено.",

        reply_markup=(
            ReplyKeyboardRemove()
        )
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN is not configured. Set it in the systemd EnvironmentFile before starting TutorBot.')

    database.create_tables()
    try:
        frozen = database.freeze_legacy_lesson_timezones()
        if frozen:
            print(f"🌍 Зафиксированы часовые пояса у старых занятий: {frozen}")
    except Exception as error:
        print("LEGACY LESSON TIMEZONE MIGRATION ERROR:", repr(error))
    apply_bot_timezone()
    payments.ensure_payment_methods()
    minute_balance.ensure_schema()
    admin_roles.initialize(admin.ADMIN_ID)
    core_test_lab.ensure_schema()
    learning_schema.initialize()
    formula_study.initialize()
    learning_curriculum.seed()
    automation_schema.initialize()
    final_schema.initialize()
    crm_schema.initialize()
    ux_schema.initialize()
    teacher_tasks.initialize()
    final_curriculum.seed()
    final_minute_ledger.backfill_current()

    app = (
        Application
        .builder()

        .token(
            BOT_TOKEN
        )

        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)

        .post_init(
            post_init
        )

        .build()
    )


    # ========================================================
    # TEST LAB ROUTING / GLOBAL HOME
    # ========================================================
    # Routing runs before maintenance so tester updates use the isolated DB.
    app.add_handler(MessageHandler(filters.ALL, core_test_lab.route_update), group=-200)
    app.add_handler(CallbackQueryHandler(core_test_lab.route_callback), group=-200)
    for _h in core_test_lab.management_handlers():
        app.add_handler(_h, group=-190)
    app.add_handler(TypeHandler(Update, blocked_student_guard), group=-185)
    for _h in global_home_handlers.handlers():
        app.add_handler(_h, group=-180)
    for _h in timezone_handlers.handlers():
        app.add_handler(_h, group=-175)
    for _h in formula_study.handlers():
        app.add_handler(_h, group=-174)
    for _h in homework_flow.handlers():
        app.add_handler(_h, group=-173)
    for _h in stage3_role_ux.handlers():
        app.add_handler(_h, group=-172)

    # VK linking callbacks must exist before broad student handlers.
    musthave_jobs.telegram_link.register(app)

    # ========================================================
    # АВАРИЙНЫЙ РЕЖИМ / ТЕХНИЧЕСКИЕ РАБОТЫ
    # ========================================================

    for handler in core_maintenance.handlers():
        app.add_handler(handler, group=-100)

    # ========================================================
    # ADELIA CONTENT ASSISTANT
    # ========================================================
    for _h in adelia_content.handlers():
        app.add_handler(_h)

    # ========================================================
    # РЕГИСТРАЦИЯ
    # ========================================================

    registration_handler = (
        ConversationHandler(

            entry_points=[

                CommandHandler(
                    "start",
                    start
                )
            ],

            states={

                REG_ROLE: [
                    CallbackQueryHandler(registration_role, pattern=r"^regrole\|")
                ],

                REG_NAME: [

                    MessageHandler(

                        filters.TEXT
                        & ~filters.COMMAND,

                        registration_name
                    )
                ],

                REG_GRADE: [

                    MessageHandler(

                        filters.TEXT
                        & ~filters.COMMAND,

                        registration_grade
                    )
                ],

                REG_GOAL: [

                    CallbackQueryHandler(

                        registration_goal,

                        pattern=(
                            r"^reggoal\|"
                        )
                    )
                ],

                REG_SUBJECT: [

                    CallbackQueryHandler(

                        registration_subject,

                        pattern=(
                            r"^regsubject\|"
                        )
                    )
                ],

                REG_MORE: [

                    CallbackQueryHandler(
                        registration_more,
                        pattern=r"^regmore\|"
                    )
                ],

                REG_PHONE: [

                    MessageHandler(

                        (
                            filters.CONTACT
                            | filters.TEXT
                        )
                        & ~filters.COMMAND,

                        registration_phone
                    )
                ],

                PARENT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, registration_parent_name)
                ],
                PARENT_PHONE: [
                    MessageHandler((filters.CONTACT | filters.TEXT) & ~filters.COMMAND, registration_parent_phone)
                ],
                PARENT_LINK_CODE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, registration_parent_link)
                ],
            },

            fallbacks=[

                CommandHandler(
                    "cancel",
                    cancel_registration
                )
            ],

            allow_reentry=True
        )
    )

    app.add_handler(
        registration_handler
    )


    # ========================================================
    # РОДИТЕЛЬСКОЕ МЕНЮ / ПРИВЯЗКА УЧЕНИКА
    # ========================================================

    app.add_handler(CallbackQueryHandler(parent_buttons, pattern=r"^parent_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, parent_link_message), group=2)


    # ========================================================
    # СООБЩЕНИЯ УЧЕНИКА ПРЕПОДАВАТЕЛЮ
    # ========================================================
    app.add_handler(student_message_handlers.handler())
    for _h in student_message_handlers.extra_handlers():
        app.add_handler(_h)

    # ========================================================
    # БЫСТРЫЙ ЗАПРОС К ЗАНЯТИЮ ИЗ ГЛАВНОГО МЕНЮ
    # ========================================================

    lesson_request_conversation = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(lesson_request_start, pattern=r"^lesson_request_start$")
        ],
        states={
            LESSON_REQUEST_CONTENT: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, lesson_request_collect),
                CallbackQueryHandler(lesson_request_choose, pattern=r"^lesson_request_choose$"),
                CallbackQueryHandler(lesson_request_cancel, pattern=r"^lesson_request_cancel$"),
            ],
            LESSON_REQUEST_LESSON: [
                CallbackQueryHandler(lesson_request_save, pattern=r"^lesson_request_lesson\|"),
                CallbackQueryHandler(lesson_request_back, pattern=r"^lesson_request_back$"),
                CallbackQueryHandler(lesson_request_cancel, pattern=r"^lesson_request_cancel$"),
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )

    app.add_handler(lesson_request_conversation)


    # ========================================================
    # КОММЕНТАРИЙ / ФОТО К ПРЕДСТОЯЩЕМУ ЗАНЯТИЮ
    # ========================================================

    lesson_note_conversation = (
        ConversationHandler(

            entry_points=[

                CallbackQueryHandler(
                    lesson_note_start,
                    pattern=(
                        r"^lesson_note_start\|"
                    ),
                )
            ],

            states={

                LESSON_NOTE: [

                    MessageHandler(
                        (
                            filters.TEXT
                            | filters.PHOTO
                        )
                        & ~filters.COMMAND,

                        lesson_note_handler,
                    )
                ]
            },

            fallbacks=[],

            allow_reentry=True,
        )
    )

    app.add_handler(
        lesson_note_conversation
    )


    # ========================================================
    # БОЛЬНИЧНЫЙ
    # СТАВИМ ДО ОБЩЕГО student_buttons
    # ========================================================

    sickness_handler = (
        ConversationHandler(

            entry_points=[

                CallbackQueryHandler(

                    sickness_start,

                    pattern=(
                        r"^sickness_start\|"
                    )
                )
            ],

            states={

                SICKNESS_COMMENT: [

                    MessageHandler(

                        filters.TEXT
                        & ~filters.COMMAND,

                        sickness_comment_handler
                    )
                ]
            },

            fallbacks=[],

            allow_reentry=True
        )
    )

    app.add_handler(
        sickness_handler
    )


    # ========================================================
    # ОПЛАТЫ
    # ========================================================

    app.add_handler(
        payments
        .get_payment_handler()
    )

    app.add_handler(
        payments
        .get_admin_payment_handler()
    )


    # ========================================================
    # SYSTEM ADMIN
    # больничные
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(

            system_admin_buttons,

            pattern=(
                r"^sys_"
            )
        )
    )


    # ========================================================
    # STUDENTS ADMIN
    # ========================================================

    # admin_students is intentionally handled by admin.py.
    # The legacy students_admin handler used to intercept this callback and
    # open the old student card, hiding the new Adelia actions.

    app.add_handler(
        students_admin
        .get_students_callback_handler()
    )


    # ========================================================
    # SCHEDULE ADMIN
    # Должен стоять ДО общих admin callback'ов.
    # ========================================================

    app.add_handler(
        schedule_admin.get_schedule_conversation_handler()
    )

    app.add_handler(
        schedule_admin.get_schedule_callback_handler()
    )


    # ========================================================
    # CHANNEL ADMIN
    # Ставим ДО общих admin callback'ов.
    # ========================================================

    app.add_handler(
        channel_admin.get_channel_conversation_handler()
    )

    app.add_handler(
        channel_admin.get_channel_callback_handler()
    )

    app.add_handler(
        channel_admin.get_channel_post_handler()
    )

    app.add_handler(
        channel_admin.get_channel_member_handler()
    )


    # ========================================================
    # CORE STAGE 1 ADMIN
    # ========================================================

    for handler in core_stage1_admin.handlers():
        app.add_handler(handler)

    # ========================================================
    # LEARNING STAGE 2
    # ========================================================

    for handler in learning_handlers.handlers():
        app.add_handler(handler)

    # ========================================================
    # AUTOMATION STAGE 3
    # ========================================================

    for handler in stage3_handlers.handlers():
        app.add_handler(handler)

    for handler in stage3_admin_extras.handlers():
        app.add_handler(handler)

    for handler in minute_admin_handlers.handlers():
        app.add_handler(handler)

    app.add_handler(message_center_handlers.handler())

    for handler in admin_inbox_handlers.handlers():
        app.add_handler(handler)

    for handler in musthave_admin.handlers():
        app.add_handler(handler)
    for handler in task_admin.handlers():
        app.add_handler(handler)
    for handler in ai_provider_admin.handlers():
        app.add_handler(handler)

    # ========================================================
    # FINAL FEATURE PACK
    # ========================================================

    app.add_handler(crm_handlers.handler())

    for handler in ux_handlers.handlers():
        app.add_handler(handler)

    for handler in final_handlers.handlers():
        app.add_handler(handler)

    # ========================================================
    # ADMIN COMMAND
    # ========================================================

    app.add_handler(
        admin.get_admin_command_handler()
    )


    # ========================================================
    # ADMIN CONVERSATION
    # ========================================================

    app.add_handler(
        admin.get_admin_conversation_handler()
    )


    # ========================================================
    # ADMIN CALLBACKS
    # ========================================================

    app.add_handler(
        admin.get_admin_callback_handler()
    )


    # ========================================================
    # STUDENT CALLBACKS
    # ========================================================

    app.add_handler(
        CallbackQueryHandler(
            student_buttons
        )
    )


    # ========================================================
    # ERROR
    # ========================================================

    app.add_error_handler(
        error_handler
    )


    print(
        "========================================"
    )

    print(
        "💜 Аделия | TutorBot запущена"
    )

    print(
        "✅ Заявки учеников: ON"
    )

    print(
        "✅ Подтверждение преподавателем: ON"
    )

    print(
        "🎟 Абонементы: ON"
    )

    print(
        "🔁 Переносы: ON"
    )

    print(
        "🔁 Постоянное расписание: ON"
    )

    print(
        "⚙️ Расписание преподавателя: ON"
    )

    print(
        "🤒 Больничные: ON"
    )

    print(
        "💳 Автоотмена неоплаченных: ON"
    )

    print(
        "⏰ 24ч / 2ч / 30мин / 10мин: ON"
    )

    print(
        "▶️ Фактическое время: ON"
    )

    print(
        "📝 Контроль ДЗ: ON"
    )

    print(
        "🔐 /admin только для администратора"
    )

    print(
        "========================================"
    )

    app.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":

    main()
