from datetime import (
    datetime,
    date,
    timedelta,
)
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database
import admin


# ============================================================
# STATES
# ============================================================

(
    WORK_START,
    WORK_END,

    CLOSED_DATE,
    CLOSED_COMMENT,

    OPEN_DATE,
    OPEN_START,
    OPEN_END,
) = range(2000, 2007)


# ============================================================
# WEEKDAYS
# ============================================================

WEEKDAYS = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


WEEKDAYS_SHORT = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


# ============================================================
# ACCESS
# ============================================================

def is_admin(
    update: Update
):

    return (
        update.effective_user
        and
        admin.is_admin(update)
    )


# ============================================================
# FORMAT
# ============================================================

def format_date(
    value
):

    try:

        return (
            datetime.strptime(
                value,
                "%Y-%m-%d"
            )
            .strftime(
                "%d.%m.%Y"
            )
        )

    except Exception:

        return str(
            value
        )


def format_datetime(
    value
):

    if not value:
        return "—"

    try:

        return (
            datetime.fromisoformat(
                value
            )
            .strftime(
                "%d.%m.%Y %H:%M"
            )
        )

    except Exception:

        return str(
            value
        )


# ============================================================
# WEEK MODE HELPERS
# ============================================================

def _week_name(kind):
    return "🔵 Нечётная" if str(kind).upper() == "ODD" else "🟣 Чётная"


def _week_enabled(kind):
    return database.teacher_week_enabled(kind)


def _week_mode():
    return str(database.get_setting("teacher_week_mode", "SAME") or "SAME").upper()


def _teacher_timezone_label():
    try:
        from core import user_timezone
        zone = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
        return user_timezone.zone_label(zone)
    except Exception:
        return "МСК"


def _current_week_text():
    try:
        zone = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
        today = datetime.now(ZoneInfo(zone)).date()
    except Exception:
        today = date.today()
    kind = database.teacher_week_kind(today)
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return f"{_week_name(kind)} неделя · {start.strftime('%d.%m')}–{end.strftime('%d.%m')}"


def _rows_text(rows):
    if not rows:
        return "Выходной"
    return ", ".join(f"{r['start_time']}–{r['end_time']}" for r in rows)

# ============================================================
# MAIN MENU
# ============================================================

def schedule_menu():
    pending = database.get_pending_regular_schedule_requests()
    mode = _week_mode()
    odd = "✅" if _week_enabled("ODD") else "🚫"
    even = "✅" if _week_enabled("EVEN") else "🚫"
    mode_label = "Одинаково каждую неделю" if mode == "SAME" else "Чётные + нечётные"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔵 Нечётная неделя", callback_data="schedule_week|ODD"),
         InlineKeyboardButton("🟣 Чётная неделя", callback_data="schedule_week|EVEN")],
        [InlineKeyboardButton(f"{odd} Нечётная", callback_data="schedule_week_toggle|ODD"),
         InlineKeyboardButton(f"{even} Чётная", callback_data="schedule_week_toggle|EVEN")],
        [InlineKeyboardButton(f"⚙️ Режим: {mode_label}", callback_data="schedule_week_mode")],
        [InlineKeyboardButton("🕐 Общий график", callback_data="schedule_working")],
        [InlineKeyboardButton("🚫 Выходные / исключения", callback_data="schedule_exceptions")],
        [InlineKeyboardButton("➕ Дополнительное окно", callback_data="schedule_open_add")],
        [InlineKeyboardButton(f"🔁 Заявки на постоянное ({len(pending)})", callback_data="schedule_regular_requests")],
        [InlineKeyboardButton("📚 Постоянные ученики", callback_data="schedule_regular_active")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="admin_main"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ])


# ============================================================
# MAIN
# ============================================================

async def show_schedule_main(query):
    mode = _week_mode()
    mode_text = "📅 одинаково каждую неделю" if mode == "SAME" else "🔄 чётные и нечётные недели"
    await query.edit_message_text(
        "⚙️ МОЁ РАСПИСАНИЕ\n\n"
        f"🌍 Вы задаёте время: {_teacher_timezone_label()}\n"
        f"📆 Сейчас: {_current_week_text()}\n"
        f"⚙️ Режим: {mode_text}\n\n"
        "🔵 Неделя 31 августа – 6 сентября 2026 считается НЕЧЁТНОЙ.\n"
        "Дальше недели автоматически чередуются.\n\n"
        "Можно задать разные часы для чётной и нечётной недели, временно отключить любую из них или использовать один общий график.\n\n"
        "Исключение конкретной даты всегда имеет приоритет. Отключение недели не переносит и не удаляет уже созданные занятия — оно только закрывает новые свободные окна.",
        reply_markup=schedule_menu(),
    )


# ============================================================
# ODD / EVEN WEEK SCHEDULE
# ============================================================

async def show_week_schedule(query, kind):
    kind = str(kind).upper()
    enabled = _week_enabled(kind)
    lines = [
        f"{_week_name(kind)} НЕДЕЛЯ",
        "",
        f"Статус: {'✅ включена' if enabled else '🚫 отключена'}",
        f"🌍 Время: {_teacher_timezone_label()}",
        "",
    ]
    kb = []
    for weekday in range(7):
        specific = database.get_working_hours(weekday, kind)
        common = database.get_working_hours(weekday, "ALL")
        if database.teacher_week_day_off(kind, weekday):
            txt = "🚫 Выходной"
            source = ""
        elif specific:
            txt = _rows_text(specific)
            source = ""
        elif common:
            txt = _rows_text(common)
            source = " · общий"
        else:
            txt = "Выходной"
            source = ""
        lines.append(f"{WEEKDAYS_SHORT[weekday]}  {txt}{source}")
        kb.append([InlineKeyboardButton(f"✏️ {WEEKDAYS[weekday]}", callback_data=f"schedule_week_day|{kind}|{weekday}")])
    lines += ["", "Если для дня задан отдельный интервал этой недели, он заменяет общий график этого дня."]
    other = "EVEN" if kind == "ODD" else "ODD"
    kb += [
        [InlineKeyboardButton("➕ Добавить интервал", callback_data=f"schedule_work_add_type|{kind}")],
        [InlineKeyboardButton(f"📋 Скопировать из {_week_name(other).replace('🔵 ','').replace('🟣 ','').lower()}", callback_data=f"schedule_week_copy|{other}|{kind}")],
        [InlineKeyboardButton("🧹 Очистить отдельные интервалы", callback_data=f"schedule_week_clear_warn|{kind}")],
        [InlineKeyboardButton("⬅️ Расписание", callback_data="admin_schedule"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ]
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def show_week_day(query, kind, weekday):
    kind = str(kind).upper()
    specific = database.get_working_hours(weekday, kind)
    common = database.get_working_hours(weekday, "ALL")
    day_off = database.teacher_week_day_off(kind, weekday)
    text = f"{_week_name(kind)} • {WEEKDAYS[weekday]}\n\n🌍 {_teacher_timezone_label()}\n\n"
    if day_off:
        text += "🚫 Этот день отключён для выбранной недели. Общий график здесь временно не применяется."
    elif specific:
        text += "Отдельный график:\n" + "\n".join(f"• {r['start_time']}–{r['end_time']}" for r in specific)
    elif common:
        text += "Сейчас используется общий график:\n" + "\n".join(f"• {r['start_time']}–{r['end_time']}" for r in common)
        text += "\n\nПервый добавленный отдельный интервал заменит общий график этого дня для выбранной недели."
    else:
        text += "Сейчас выходной."
    kb = [[InlineKeyboardButton("➕ Добавить интервал", callback_data=f"schedule_work_day|{kind}|{weekday}")]]
    kb.append([InlineKeyboardButton("✅ Сделать рабочим" if day_off else "🚫 Сделать выходным", callback_data=f"schedule_week_day_off|{kind}|{weekday}")])
    for row in specific:
        kb.append([InlineKeyboardButton(f"🗑 {row['start_time']}–{row['end_time']}", callback_data=f"schedule_work_delete_week|{kind}|{weekday}|{row['id']}")])
    kb.append([InlineKeyboardButton("⬅️ К неделе", callback_data=f"schedule_week|{kind}"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def show_week_mode(query):
    mode = _week_mode()
    text = (
        "⚙️ РЕЖИМ НЕДЕЛЬ\n\n"
        "📅 Одинаково каждую неделю — используется общий график.\n\n"
        "🔄 Чётные + нечётные — TutorBot выбирает график по неделе. Если отдельный день ещё не заполнен, используется общий график как безопасный запасной вариант.\n\n"
        "Точка отсчёта: неделя 31.08–06.09.2026 — НЕЧЁТНАЯ.\n\n"
        f"Сейчас: {'📅 одинаково каждую неделю' if mode == 'SAME' else '🔄 чётные + нечётные'}"
    )
    kb = [
        [InlineKeyboardButton("📅 Одинаково каждую неделю", callback_data="schedule_week_mode_set|SAME")],
        [InlineKeyboardButton("🔄 Чётные + нечётные", callback_data="schedule_week_mode_set|ALTERNATING")],
        [InlineKeyboardButton("⬅️ Расписание", callback_data="admin_schedule"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ============================================================
# WORKING HOURS
# ============================================================

async def show_working_hours(
    query
):

    rows = (
        database
        .get_working_hours(week_type="ALL")
    )

    keyboard = []

    for row in rows:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"🕐 "
                    f"{WEEKDAYS_SHORT[row['weekday']]} "
                    f"{row['start_time']}–"
                    f"{row['end_time']}"
                ),

                callback_data=(
                    f"schedule_work_view|"
                    f"{row['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Добавить часы",
            callback_data="schedule_work_add"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Расписание",
            callback_data="admin_schedule"
        )
    ])

    if rows:

        text = (
            "🕐 ОБЩИЙ ГРАФИК\n\n"
            "Этот график используется каждую неделю. В режиме чётных/нечётных недель он служит запасным графиком для тех дней, где отдельное расписание недели ещё не задано.\n\n"
            "Нажмите на интервал для управления."
        )

    else:

        text = (
            "🕐 ОБЩИЙ ГРАФИК\n\n"
            "Общие рабочие часы пока не заданы. Можно заполнить общий график или сразу настроить чётную и нечётную недели."
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
# WORK ADD
# ============================================================

async def work_add_start(
    query,
    week_type="ALL",
):

    week_type = str(week_type or "ALL").upper()
    keyboard = []

    # Kept in query object context via callback payload on the day buttons.
    for weekday in range(7):

        keyboard.append([
            InlineKeyboardButton(
                WEEKDAYS[weekday],

                callback_data=(
                    f"schedule_work_day|{week_type}|{weekday}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="schedule_working"
        )
    ])

    await query.edit_message_text(
        f"➕ ДОБАВИТЬ ИНТЕРВАЛ • {_week_name(week_type) if week_type != 'ALL' else '📅 Общий график'}\n\n"
        f"🌍 Время: {_teacher_timezone_label()}\n\n"
        "Выберите день недели:",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


async def work_day_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    await query.answer()

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    parts = query.data.split("|")
    if len(parts) >= 3:
        week_type = parts[1].upper()
        weekday = int(parts[2])
    else:
        week_type = "ALL"
        weekday = int(parts[1])

    context.user_data["schedule_week_type"] = week_type
    context.user_data["schedule_weekday"] = weekday

    await query.edit_message_text(
        f"🕐 {WEEKDAYS[weekday]}\n\n"

        "Введите время начала.\n\n"

        "Например:\n"
        "10:00"
    )

    return WORK_START


async def work_start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        datetime.strptime(
            value,
            "%H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Например:\n"
            "10:00"
        )

        return WORK_START

    context.user_data[
        "schedule_work_start"
    ] = value

    await update.message.reply_text(
        "Введите время окончания.\n\n"

        "Например:\n"
        "21:00"
    )

    return WORK_END


async def work_end_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        datetime.strptime(
            value,
            "%H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверный формат.\n\n"
            "Например:\n"
            "21:00"
        )

        return WORK_END

    weekday = (
        context.user_data[
            "schedule_weekday"
        ]
    )

    start = (
        context.user_data[
            "schedule_work_start"
        ]
    )

    week_type = context.user_data.get("schedule_week_type", "ALL")

    try:
        if week_type in {"ODD", "EVEN"}:
            database.set_teacher_week_day_off(week_type, weekday, False)

        database.add_working_hours(
            weekday,
            start,
            value,
            week_type=week_type,
        )

    except Exception as error:

        await update.message.reply_text(
            f"❌ {error}"
        )

        return WORK_END

    context.user_data.pop(
        "schedule_weekday",
        None
    )

    context.user_data.pop(
        "schedule_work_start",
        None
    )
    context.user_data.pop("schedule_week_type", None)

    await update.message.reply_text(
        "💜 Готово, сохранила рабочий интервал.\n\n"
        f"{_week_name(week_type) if week_type != 'ALL' else '📅 Общий график'}\n"
        f"{WEEKDAYS[weekday]} • {start}–{value}\n"
        f"🌍 {_teacher_timezone_label()}",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ К неделе" if week_type in {"ODD", "EVEN"} else "🕐 Общий график",
                        callback_data=(f"schedule_week|{week_type}" if week_type in {"ODD", "EVEN"} else "schedule_working"),
                    )
                ],
                [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
            ])
        )
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# WORK VIEW / DELETE
# ============================================================

async def show_work_interval(
    query,
    item_id
):

    rows = (
        database
        .get_all_working_hours()
    )

    row = next(
        (
            item
            for item in rows
            if item["id"]
            == item_id
        ),
        None
    )

    if row is None:

        await query.edit_message_text(
            "❌ Интервал не найден."
        )

        return

    await query.edit_message_text(
        "🕐 РАБОЧИЙ ИНТЕРВАЛ\n\n"

        f"{WEEKDAYS[row['weekday']]}\n"
        f"{row['start_time']}–"
        f"{row['end_time']}",

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "🗑 Удалить",
                        callback_data=(
                            f"schedule_work_delete|"
                            f"{item_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data="schedule_working"
                    )
                ]
            ])
        )
    )


async def delete_work_interval(
    query,
    item_id
):

    database.delete_working_hours(
        item_id
    )

    await query.edit_message_text(
        "✅ Рабочий интервал удалён.",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🕐 Рабочие часы",
                        callback_data="schedule_working"
                    )
                ]
            ])
        )
    )


# ============================================================
# LESSONS ON DATE
# ============================================================

def get_future_lessons_on_date(
    date_value
):

    conn = (
        database.connect()
    )

    rows = conn.execute("""
        SELECT

            l.*,

            u.name,
            u.telegram_id

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            DATE(l.start_time) = ?

            AND l.lesson_status IN (
                'PENDING',
                'CONFIRMED'
            )

        ORDER BY
            l.start_time
    """, (
        date_value,
    )).fetchall()

    conn.close()

    return rows


# ============================================================
# REFUND / CANCEL LESSON FOR DAY OFF
# ============================================================

def cancel_lesson_for_admin_day_off(
    lesson_id
):

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if lesson is None:

        return {
            "cancelled": False,
            "refunded": False,
        }

    refunded = False


    # ========================================================
    # ЕСЛИ УЖЕ СПИСАНО — ВОЗВРАЩАЕМ
    # ========================================================

    if (
        lesson["charged"]
        and lesson["package_id"]
    ):

        refunded = (
            database
            .refund_prepaid_lesson(
                lesson["package_id"]
            )
        )


    conn = (
        database.connect()
    )

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',

            charged = 0,

            package_id = NULL,

            payment_status =
                CASE

                    WHEN payment_status = 'FREE'
                    THEN 'FREE'

                    ELSE 'REFUNDED'

                END,

            cancelled_at = ?,

            cancellation_reason =
                'ADMIN_DAY_OFF',

            updated_at = ?

        WHERE id = ?
    """, (
        database.now_iso(),
        database.now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return {
        "cancelled": True,
        "refunded": refunded,
    }


# ============================================================
# EXCEPTIONS LIST
# ============================================================

async def show_exceptions(
    query
):

    rows = (
        database
        .get_schedule_exceptions()
    )

    today = (
        date.today()
        .isoformat()
    )

    rows = [
        row
        for row in rows
        if row["date"] >= today
    ]

    keyboard = []

    for row in rows[:40]:

        d = (
            format_date(
                row["date"]
            )
        )

        if (
            row[
                "exception_type"
            ] == "CLOSED"
        ):

            if (
                row["start_time"]
                and row["end_time"]
            ):

                title = (
                    f"🚫 {d} "
                    f"{row['start_time']}–"
                    f"{row['end_time']}"
                )

            else:

                title = (
                    f"🚫 {d} "
                    f"весь день"
                )

        else:

            title = (
                f"➕ {d} "
                f"{row['start_time']}–"
                f"{row['end_time']}"
            )

        keyboard.append([
            InlineKeyboardButton(
                title,

                callback_data=(
                    f"schedule_exception_view|"
                    f"{row['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "🚫 Сделать дату выходной",
            callback_data="schedule_closed_add"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Добавить рабочее окно",
            callback_data="schedule_open_add"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Расписание",
            callback_data="admin_schedule"
        )
    ])

    await query.edit_message_text(
        "🚫 ИСКЛЮЧЕНИЯ РАСПИСАНИЯ\n\n"

        "🚫 CLOSED — закрывает дату.\n"
        "➕ OPEN — добавляет рабочее окно "
        "на конкретную дату.",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# CLOSED DATE START
# ============================================================

async def closed_add_start(
    query
):

    await query.edit_message_text(
        "🚫 СДЕЛАТЬ ДАТУ ВЫХОДНОЙ\n\n"

        "Введите дату.\n\n"

        "Например:\n"
        "25.08.2026"
    )

    return CLOSED_DATE


async def closed_date_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        parsed = (
            datetime.strptime(
                value,
                "%d.%m.%Y"
            )
            .date()
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Формат даты:\n"
            "25.08.2026"
        )

        return CLOSED_DATE

    context.user_data[
        "schedule_closed_date"
    ] = (
        parsed.isoformat()
    )

    await update.message.reply_text(
        "Напишите комментарий.\n\n"

        "Например:\n"
        "Отпуск\n\n"

        "Или просто:\n"
        "-"
    )

    return CLOSED_COMMENT


# ============================================================
# CLOSED COMMENT
# ============================================================

async def closed_comment_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    comment = (
        update.message.text
        .strip()
    )

    if comment == "-":
        comment = None

    date_value = (
        context.user_data[
            "schedule_closed_date"
        ]
    )

    context.user_data[
        "schedule_closed_comment"
    ] = comment

    lessons = (
        get_future_lessons_on_date(
            date_value
        )
    )

    date_text = (
        format_date(
            date_value
        )
    )


    # ========================================================
    # ЕСЛИ ЗАНЯТИЙ НЕТ
    # ========================================================

    if not lessons:

        database.add_schedule_exception(
            date=date_value,
            exception_type="CLOSED",
            comment=comment
        )

        context.user_data.pop(
            "schedule_closed_date",
            None
        )

        context.user_data.pop(
            "schedule_closed_comment",
            None
        )

        await update.message.reply_text(
            "✅ Дата закрыта.\n\n"

            f"📅 {date_text}\n\n"

            "Новых записей на этот день "
            "больше не будет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🚫 Исключения",
                            callback_data=(
                                "schedule_exceptions"
                            )
                        )
                    ]
                ])
            )
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # ЕСЛИ УЖЕ ЕСТЬ ЗАНЯТИЯ
    # ========================================================

    lines = [

        "⚠️ НА ЭТУ ДАТУ УЖЕ ЕСТЬ ЗАНЯТИЯ",
        "",
        f"📅 {date_text}",
        "",
    ]

    for lesson in lessons:

        start_dt = (
            datetime.fromisoformat(
                lesson[
                    "start_time"
                ]
            )
        )

        lines.append(
            (
                f"• "
                f"{start_dt.strftime('%H:%M')} "
                f"— {lesson['name']}"
            )
        )

    lines.extend([
        "",
        "Что сделать?",
    ])

    await update.message.reply_text(
        "\n".join(
            lines
        ),

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "🚫 Выходной + отменить занятия",
                        callback_data=(
                            "schedule_closed_cancel_existing"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "🔒 Только закрыть новые записи",
                        callback_data=(
                            "schedule_closed_keep_existing"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Отмена",
                        callback_data=(
                            "schedule_exceptions"
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
# FINALIZE CLOSED — KEEP EXISTING
# ============================================================

async def closed_keep_existing(
    query,
    context
):

    date_value = (
        context.user_data.get(
            "schedule_closed_date"
        )
    )

    comment = (
        context.user_data.get(
            "schedule_closed_comment"
        )
    )

    if not date_value:

        await query.edit_message_text(
            "❌ Дата потеряна. "
            "Попробуйте ещё раз."
        )

        return

    database.add_schedule_exception(
        date=date_value,
        exception_type="CLOSED",
        comment=comment
    )

    context.user_data.pop(
        "schedule_closed_date",
        None
    )

    context.user_data.pop(
        "schedule_closed_comment",
        None
    )

    await query.edit_message_text(
        "🔒 НОВЫЕ ЗАПИСИ ЗАКРЫТЫ\n\n"

        f"📅 "
        f"{format_date(date_value)}\n\n"

        "Уже существующие занятия "
        "остались без изменений.",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🚫 Исключения",
                        callback_data=(
                            "schedule_exceptions"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# FINALIZE CLOSED — CANCEL EXISTING
# ============================================================

async def closed_cancel_existing(
    query,
    context
):

    date_value = (
        context.user_data.get(
            "schedule_closed_date"
        )
    )

    comment = (
        context.user_data.get(
            "schedule_closed_comment"
        )
    )

    if not date_value:

        await query.edit_message_text(
            "❌ Дата потеряна."
        )

        return

    lessons = (
        get_future_lessons_on_date(
            date_value
        )
    )

    database.add_schedule_exception(
        date=date_value,
        exception_type="CLOSED",
        comment=comment
    )

    cancelled_count = 0
    refunded_count = 0

    for lesson in lessons:

        result = (
            cancel_lesson_for_admin_day_off(
                lesson["id"]
            )
        )

        if result[
            "cancelled"
        ]:

            cancelled_count += 1

        if result[
            "refunded"
        ]:

            refunded_count += 1


        # ====================================================
        # УВЕДОМЛЕНИЕ УЧЕНИКУ
        # ====================================================

        if lesson[
            "telegram_id"
        ]:

            message = (
                "🚫 ИЗМЕНЕНИЕ РАСПИСАНИЯ\n\n"

                f"Занятие:\n"
                f"📅 "
                f"{format_datetime(lesson['start_time'])}\n\n"

                "отменено преподавателем "
                "из-за изменения расписания.\n\n"
            )

            if lesson[
                "charged"
            ]:

                message += (
                    "🎟 Занятие возвращено "
                    "на ваш баланс.\n\n"
                )

            else:

                message += (
                    "🎟 Занятие не списано.\n\n"
                )

            if lesson[
                "regular_schedule_id"
            ]:

                schedule = (
                    database
                    .get_regular_schedule(
                        lesson[
                            "regular_schedule_id"
                        ]
                    )
                )

                if schedule:

                    message += (
                        "🔁 Ваше постоянное "
                        "расписание сохраняется:\n"

                        f"{WEEKDAYS[schedule['weekday']]}, "
                        f"{schedule['start_time']}.\n\n"

                        "Отменена только "
                        "эта конкретная дата."
                    )

            try:

                await query.get_bot().send_message(
                    chat_id=(
                        lesson[
                            "telegram_id"
                        ]
                    ),
                    text=message
                )

            except Exception as error:

                print(
                    "DAY OFF STUDENT NOTIFY:",
                    repr(error)
                )


    context.user_data.pop(
        "schedule_closed_date",
        None
    )

    context.user_data.pop(
        "schedule_closed_comment",
        None
    )

    await query.edit_message_text(
        "✅ ВЫХОДНОЙ УСТАНОВЛЕН\n\n"

        f"📅 "
        f"{format_date(date_value)}\n\n"

        f"Отменено занятий: "
        f"{cancelled_count}\n"

        f"Возвращено на баланс: "
        f"{refunded_count}\n\n"

        "Постоянные серии учеников "
        "не удалены.",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🚫 Исключения",
                        callback_data=(
                            "schedule_exceptions"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# OPEN DATE
# ============================================================

async def open_add_start(
    query
):

    await query.edit_message_text(
        "➕ ДОПОЛНИТЕЛЬНОЕ ОКНО\n\n"

        "Введите дату.\n\n"

        "Например:\n"
        "30.08.2026"
    )

    return OPEN_DATE


async def open_date_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        parsed = (
            datetime.strptime(
                value,
                "%d.%m.%Y"
            )
            .date()
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Формат даты:\n"
            "30.08.2026"
        )

        return OPEN_DATE

    context.user_data[
        "schedule_open_date"
    ] = (
        parsed.isoformat()
    )

    await update.message.reply_text(
        "Введите начало окна.\n\n"

        "Например:\n"
        "12:00"
    )

    return OPEN_START


async def open_start_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        datetime.strptime(
            value,
            "%H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Например:\n"
            "12:00"
        )

        return OPEN_START

    context.user_data[
        "schedule_open_start"
    ] = value

    await update.message.reply_text(
        "Введите окончание окна.\n\n"

        "Например:\n"
        "16:00"
    )

    return OPEN_END


async def open_end_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    value = (
        update.message.text
        .strip()
    )

    try:

        datetime.strptime(
            value,
            "%H:%M"
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Например:\n"
            "16:00"
        )

        return OPEN_END

    date_value = (
        context.user_data[
            "schedule_open_date"
        ]
    )

    start = (
        context.user_data[
            "schedule_open_start"
        ]
    )

    try:

        database.add_schedule_exception(
            date=date_value,
            exception_type="OPEN",
            start_time=start,
            end_time=value,
            comment="Дополнительное окно"
        )

    except Exception as error:

        await update.message.reply_text(
            f"❌ {error}"
        )

        return OPEN_END

    context.user_data.pop(
        "schedule_open_date",
        None
    )

    context.user_data.pop(
        "schedule_open_start",
        None
    )

    await update.message.reply_text(
        "✅ Дополнительное окно добавлено.\n\n"

        f"📅 "
        f"{format_date(date_value)}\n"

        f"🕐 "
        f"{start}–{value}",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⚙️ Расписание",
                        callback_data=(
                            "admin_schedule"
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
# EXCEPTION VIEW
# ============================================================

async def show_exception(
    query,
    exception_id
):

    rows = (
        database
        .get_schedule_exceptions()
    )

    item = next(
        (
            row
            for row in rows
            if row["id"]
            == exception_id
        ),
        None
    )

    if item is None:

        await query.edit_message_text(
            "❌ Исключение не найдено."
        )

        return

    if (
        item[
            "exception_type"
        ] == "CLOSED"
    ):

        title = (
            "🚫 Закрытая дата"
        )

    else:

        title = (
            "➕ Дополнительное окно"
        )

    text = (
        f"{title}\n\n"

        f"📅 "
        f"{format_date(item['date'])}"
    )

    if (
        item["start_time"]
        and item["end_time"]
    ):

        text += (
            "\n🕐 "
            f"{item['start_time']}–"
            f"{item['end_time']}"
        )

    if item["comment"]:

        text += (
            "\n\n💬 "
            f"{item['comment']}"
        )

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "🗑 Удалить исключение",
                        callback_data=(
                            f"schedule_exception_delete|"
                            f"{exception_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=(
                            "schedule_exceptions"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# REGULAR REQUESTS
# ============================================================

async def show_regular_requests(
    query
):

    rows = (
        database
        .get_pending_regular_schedule_requests()
    )

    if not rows:

        await query.edit_message_text(
            "🔁 ЗАЯВКИ НА ПОСТОЯННОЕ РАСПИСАНИЕ\n\n"

            "Новых заявок нет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Расписание",
                            callback_data=(
                                "admin_schedule"
                            )
                        )
                    ]
                ])
            )
        )

        return

    keyboard = []

    for row in rows:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"🔁 "
                    f"{row['name']} • "
                    f"{WEEKDAYS_SHORT[row['weekday']]} "
                    f"{row['start_time']}"
                ),

                callback_data=(
                    f"schedule_regular_request|"
                    f"{row['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Расписание",
            callback_data=(
                "admin_schedule"
            )
        )
    ])

    await query.edit_message_text(
        "🔁 ЗАЯВКИ НА ПОСТОЯННОЕ РАСПИСАНИЕ",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# REGULAR REQUEST VIEW
# ============================================================

async def show_regular_request(
    query,
    schedule_id
):

    schedule = (
        database
        .get_regular_schedule(
            schedule_id
        )
    )

    if schedule is None:

        await query.edit_message_text(
            "❌ Заявка не найдена."
        )

        return

    user = (
        database
        .get_user(
            schedule[
                "user_id"
            ]
        )
    )

    count = (
        database
        .count_regular_schedule_dates(
            schedule_id
        )
    )

    await query.edit_message_text(
        "🔁 ЗАЯВКА НА ПОСТОЯННОЕ РАСПИСАНИЕ\n\n"

        f"👤 "
        f"{user['name']}\n"

        f"🎓 "
        f"{user['grade']} класс\n\n"

        f"📅 Каждый "
        f"{WEEKDAYS[schedule['weekday']]}\n"

        f"🕐 "
        f"{schedule['start_time']}\n"

        f"⏱ "
        f"{schedule['duration_minutes']} минут\n\n"

        f"📆 С "
        f"{format_date(schedule['start_date'])}\n"

        f"📆 До "
        f"{format_date(schedule['end_date'])}\n\n"

        f"Всего дат в серии: "
        f"{count}",

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "✅ Подтвердить",
                        callback_data=(
                            f"schedule_regular_approve|"
                            f"{schedule_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=(
                            f"schedule_regular_reject|"
                            f"{schedule_id}"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ К заявкам",
                        callback_data=(
                            "schedule_regular_requests"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# APPROVE REGULAR
# ============================================================

async def approve_regular(
    query,
    context,
    schedule_id
):

    try:

        database.approve_regular_schedule_v2(
            schedule_id
        )

    except Exception as error:

        await query.answer(
            str(error),
            show_alert=True
        )

        return

    schedule = (
        database
        .get_regular_schedule(
            schedule_id
        )
    )

    user = (
        database
        .get_user(
            schedule[
                "user_id"
            ]
        )
    )


    # ========================================================
    # СОЗДАЁМ ТОЛЬКО 28 ДНЕЙ ВПЕРЁД
    # ========================================================

    horizon = (
        date.today()
        + timedelta(days=28)
    )

    try:

        result = (
            database
            .generate_regular_lessons(
                schedule_id,
                until_date=horizon
            )
        )

        # Newly generated regular lessons must receive their jobs
        # immediately. Waiting for the next bot restart is not acceptable.
        schedule_payment = (
            context.application.bot_data.get(
                "schedule_payment_reminders"
            )
        )
        schedule_lesson = (
            context.application.bot_data.get(
                "schedule_lesson_reminders"
            )
        )

        for lesson_id in result.get("created", []):
            lesson = database.get_lesson(lesson_id)

            if not lesson:
                continue

            if (
                lesson["payment_status"]
                == "AWAITING_PAYMENT"
            ):
                if schedule_payment:
                    schedule_payment(
                        context.application,
                        lesson_id
                    )
            else:
                if schedule_lesson:
                    schedule_lesson(
                        context.application,
                        lesson_id
                    )

    except Exception as error:

        print(
            "REGULAR GENERATE:",
            repr(error)
        )

        result = {
            "created_count": 0,
            "skipped_count": 0,
        }


    # ========================================================
    # STUDENT MESSAGE
    # ========================================================

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
                "✅ ПОСТОЯННОЕ РАСПИСАНИЕ "
                "ПОДТВЕРЖДЕНО\n\n"

                f"📅 Каждый "
                f"{WEEKDAYS[schedule['weekday']]}\n"

                f"🕐 "
                f"{schedule['start_time']}\n"

                f"⏱ "
                f"{schedule['duration_minutes']} минут\n"

                f"📆 До "
                f"{format_date(schedule['end_date'])}\n\n"

                "Ваш постоянный слот "
                "закреплён за вами."
            )
        )


    await query.edit_message_text(
        "✅ ПОСТОЯННОЕ РАСПИСАНИЕ "
        "ПОДТВЕРЖДЕНО\n\n"

        f"👤 "
        f"{user['name']}\n"

        f"📅 "
        f"{WEEKDAYS[schedule['weekday']]}\n"

        f"🕐 "
        f"{schedule['start_time']}\n\n"

        f"Создано ближайших занятий: "
        f"{result['created_count']}\n"

        f"Пропущено: "
        f"{result['skipped_count']}",

        reply_markup=(
            InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "📚 Постоянные ученики",
                        callback_data=(
                            "schedule_regular_active"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ Расписание",
                        callback_data=(
                            "admin_schedule"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# REJECT REGULAR
# ============================================================

async def reject_regular(
    query,
    context,
    schedule_id
):

    schedule = (
        database
        .get_regular_schedule(
            schedule_id
        )
    )

    if schedule is None:

        return

    user = (
        database
        .get_user(
            schedule[
                "user_id"
            ]
        )
    )

    database.reject_regular_schedule(
        schedule_id,
        reason=(
            "Отклонено преподавателем"
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
                "❌ Заявка на постоянное "
                "расписание отклонена.\n\n"

                "Можно выбрать другой "
                "день или время."
            )
        )

    await query.edit_message_text(
        "❌ Заявка отклонена.",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ К заявкам",
                        callback_data=(
                            "schedule_regular_requests"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# ACTIVE REGULAR
# ============================================================

async def show_active_regular(
    query
):

    rows = (
        database
        .get_active_regular_schedules()
    )

    if not rows:

        await query.edit_message_text(
            "📚 ПОСТОЯННЫЕ УЧЕНИКИ\n\n"
            "Постоянных расписаний пока нет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Расписание",
                            callback_data=(
                                "admin_schedule"
                            )
                        )
                    ]
                ])
            )
        )

        return

    keyboard = []

    for row in rows:

        if (
            row[
                "status"
            ] == "PAUSED"
        ):

            icon = "⏸"

        else:

            icon = "🔁"

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{icon} "
                    f"{row['name']} • "
                    f"{WEEKDAYS_SHORT[row['weekday']]} "
                    f"{row['start_time']}"
                ),

                callback_data=(
                    f"schedule_regular_view|"
                    f"{row['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Расписание",
            callback_data=(
                "admin_schedule"
            )
        )
    ])

    await query.edit_message_text(
        "📚 ПОСТОЯННЫЕ УЧЕНИКИ",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# ACTIVE REGULAR ITEM
# ============================================================

async def show_regular_active_item(
    query,
    schedule_id
):

    schedule = (
        database
        .get_regular_schedule(
            schedule_id
        )
    )

    if schedule is None:

        return

    user = (
        database
        .get_user(
            schedule[
                "user_id"
            ]
        )
    )

    text = (
        "🔁 ПОСТОЯННОЕ РАСПИСАНИЕ\n\n"

        f"👤 "
        f"{user['name']}\n\n"

        f"📅 "
        f"{WEEKDAYS[schedule['weekday']]}\n"

        f"🕐 "
        f"{schedule['start_time']}\n"

        f"⏱ "
        f"{schedule['duration_minutes']} минут\n\n"

        f"📆 "
        f"{format_date(schedule['start_date'])}"
        f" — "
        f"{format_date(schedule['end_date'])}\n\n"

        f"Статус: "
        f"{schedule['status']}\n"

        f"Создано занятий: "
        f"{schedule['created_lessons_count'] or 0}"
    )

    keyboard = []

    if (
        schedule[
            "status"
        ] == "APPROVED"
    ):

        keyboard.append([
            InlineKeyboardButton(
                "⏸ Приостановить",
                callback_data=(
                    f"schedule_regular_pause|"
                    f"{schedule_id}"
                )
            )
        ])

    elif (
        schedule[
            "status"
        ] == "PAUSED"
    ):

        keyboard.append([
            InlineKeyboardButton(
                "▶️ Возобновить",
                callback_data=(
                    f"schedule_regular_resume|"
                    f"{schedule_id}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ Отменить постоянное расписание",
            callback_data=(
                f"schedule_regular_cancel_warn|"
                f"{schedule_id}"
            )
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Постоянные ученики",
            callback_data=(
                "schedule_regular_active"
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
# CALLBACK ROUTER
# ============================================================

async def schedule_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    if not is_admin(
        update
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


    if data == "admin_schedule":

        await show_schedule_main(
            query
        )

        return


    if data.startswith("schedule_week|"):
        await show_week_schedule(query, data.split("|", 1)[1])
        return

    if data == "schedule_week_mode":
        await show_week_mode(query)
        return

    if data.startswith("schedule_week_mode_set|"):
        mode = data.split("|", 1)[1].upper()
        if mode in {"SAME", "ALTERNATING"}:
            database.set_setting("teacher_week_mode", mode)
        await show_schedule_main(query)
        return

    if data.startswith("schedule_week_toggle|"):
        kind = data.split("|", 1)[1].upper()
        key = "teacher_odd_week_enabled" if kind == "ODD" else "teacher_even_week_enabled"
        database.set_setting(key, "0" if _week_enabled(kind) else "1")
        await show_schedule_main(query)
        return

    if data.startswith("schedule_week_day|"):
        _, kind, weekday = data.split("|", 2)
        await show_week_day(query, kind, int(weekday))
        return

    if data.startswith("schedule_work_add_type|"):
        await work_add_start(query, data.split("|", 1)[1])
        return

    if data.startswith("schedule_week_day_off|"):
        _, kind, weekday = data.split("|", 2)
        weekday = int(weekday)
        current = database.teacher_week_day_off(kind, weekday)
        database.set_teacher_week_day_off(kind, weekday, not current)
        await show_week_day(query, kind, weekday)
        return

    if data.startswith("schedule_work_delete_week|"):
        _, kind, weekday, item_id = data.split("|", 3)
        database.delete_working_hours(int(item_id))
        await show_week_day(query, kind, int(weekday))
        return

    if data.startswith("schedule_week_copy|"):
        _, source, target = data.split("|", 2)
        database.replace_week_schedule(source, target)
        await show_week_schedule(query, target)
        return

    if data.startswith("schedule_week_clear_warn|"):
        kind = data.split("|", 1)[1]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🧹 Да, очистить", callback_data=f"schedule_week_clear|{kind}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"schedule_week|{kind}")],
        ])
        await query.edit_message_text(
            f"🧹 Очистить отдельный график {_week_name(kind).lower()} недели?\n\nОбщий график и уже созданные занятия останутся без изменений.",
            reply_markup=kb,
        )
        return

    if data.startswith("schedule_week_clear|"):
        kind = data.split("|", 1)[1]
        database.clear_week_schedule(kind)
        await show_week_schedule(query, kind)
        return

    if data == "schedule_working":

        await show_working_hours(
            query
        )

        return


    if data == "schedule_work_add":

        await work_add_start(
            query
        )

        return


    if data.startswith(
        "schedule_work_view|"
    ):

        item_id = int(
            data.split("|")[1]
        )

        await show_work_interval(
            query,
            item_id
        )

        return


    if data.startswith(
        "schedule_work_delete|"
    ):

        item_id = int(
            data.split("|")[1]
        )

        await delete_work_interval(
            query,
            item_id
        )

        return


    if data == "schedule_exceptions":

        await show_exceptions(
            query
        )

        return


    if data.startswith(
        "schedule_exception_view|"
    ):

        item_id = int(
            data.split("|")[1]
        )

        await show_exception(
            query,
            item_id
        )

        return


    if data.startswith(
        "schedule_exception_delete|"
    ):

        item_id = int(
            data.split("|")[1]
        )

        database.delete_schedule_exception(
            item_id
        )

        await show_exceptions(
            query
        )

        return


    if data == "schedule_closed_keep_existing":

        await closed_keep_existing(
            query,
            context
        )

        return


    if data == "schedule_closed_cancel_existing":

        await closed_cancel_existing(
            query,
            context
        )

        return


    if data == "schedule_regular_requests":

        await show_regular_requests(
            query
        )

        return


    if data.startswith(
        "schedule_regular_request|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        await show_regular_request(
            query,
            schedule_id
        )

        return


    if data.startswith(
        "schedule_regular_approve|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        await approve_regular(
            query,
            context,
            schedule_id
        )

        return


    if data.startswith(
        "schedule_regular_reject|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        await reject_regular(
            query,
            context,
            schedule_id
        )

        return


    if data == "schedule_regular_active":

        await show_active_regular(
            query
        )

        return


    if data.startswith(
        "schedule_regular_view|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        await show_regular_active_item(
            query,
            schedule_id
        )

        return


    if data.startswith(
        "schedule_regular_pause|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        database.pause_regular_schedule(
            schedule_id
        )

        await show_regular_active_item(
            query,
            schedule_id
        )

        return


    if data.startswith(
        "schedule_regular_resume|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        database.resume_regular_schedule(
            schedule_id
        )

        await show_regular_active_item(
            query,
            schedule_id
        )

        return


    if data.startswith(
        "schedule_regular_cancel_warn|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        await query.edit_message_text(
            "⚠️ ОТМЕНА ПОСТОЯННОГО РАСПИСАНИЯ\n\n"

            "Новые занятия серии "
            "больше создаваться не будут.\n\n"

            "Уже созданные занятия "
            "останутся отдельно.\n\n"

            "Подтверждаете?",

            reply_markup=(
                InlineKeyboardMarkup([

                    [
                        InlineKeyboardButton(
                            "❌ Да, отменить серию",
                            callback_data=(
                                f"schedule_regular_cancel|"
                                f"{schedule_id}"
                            )
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "⬅️ Нет",
                            callback_data=(
                                f"schedule_regular_view|"
                                f"{schedule_id}"
                            )
                        )
                    ]
                ])
            )
        )

        return


    if data.startswith(
        "schedule_regular_cancel|"
    ):

        schedule_id = int(
            data.split("|")[1]
        )

        database.cancel_regular_schedule(
            schedule_id,
            reason=(
                "Отменено преподавателем"
            )
        )

        await query.edit_message_text(
            "✅ Постоянное расписание отменено.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📚 Постоянные ученики",
                            callback_data=(
                                "schedule_regular_active"
                            )
                        )
                    ]
                ])
            )
        )

        return


# ============================================================
# CONVERSATION ENTRY
# ============================================================

async def closed_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    return await closed_add_start(
        query
    )


async def open_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    return await open_add_start(
        query
    )


# ============================================================
# HANDLERS
# ============================================================

def get_schedule_conversation_handler():

    return ConversationHandler(

        entry_points=[

            CallbackQueryHandler(
                work_day_selected,
                pattern=(
                    r"^schedule_work_day\|"
                )
            ),

            CallbackQueryHandler(
                closed_entry,
                pattern=(
                    r"^schedule_closed_add$"
                )
            ),

            CallbackQueryHandler(
                open_entry,
                pattern=(
                    r"^schedule_open_add$"
                )
            ),
        ],

        states={

            WORK_START: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    work_start_handler
                )
            ],

            WORK_END: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    work_end_handler
                )
            ],

            CLOSED_DATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    closed_date_handler
                )
            ],

            CLOSED_COMMENT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    closed_comment_handler
                )
            ],

            OPEN_DATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    open_date_handler
                )
            ],

            OPEN_START: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    open_start_handler
                )
            ],

            OPEN_END: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    open_end_handler
                )
            ],
        },

        fallbacks=[],

        allow_reentry=True
    )


def get_schedule_callback_handler():

    return CallbackQueryHandler(

        schedule_buttons,

        pattern=(
            r"^admin_schedule$"
            r"|^schedule_week"
            r"|^schedule_working$"
            r"|^schedule_work_add$"
            r"|^schedule_work_add_type\|"
            r"|^schedule_work_delete_week\|"
            r"|^schedule_work_view\|"
            r"|^schedule_work_delete\|"
            r"|^schedule_exceptions$"
            r"|^schedule_exception_view\|"
            r"|^schedule_exception_delete\|"
            r"|^schedule_closed_keep_existing$"
            r"|^schedule_closed_cancel_existing$"
            r"|^schedule_regular_"
        )
    )
