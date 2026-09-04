from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
)

import database
from ux_final import service as ux_service
import admin
from core import minute_balance
from crm_plus import service as crm_service


# ============================================================
# НАСТРОЙКИ
# ============================================================

TIMEZONE_NAME = "Europe/Moscow"

TIMEZONE = ZoneInfo(
    TIMEZONE_NAME
)


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

    "PENDING":
        "⏳ Заявка",

    "CONFIRMED":
        "✅ Подтверждено",

    "IN_PROGRESS":
        "▶️ Идёт",

    "COMPLETED":
        "✅ Проведено",

    "NO_SHOW":
        "❌ Неявка",

    "LATE_CANCELLED":
        "⚠️ Поздний перенос",

    "SICKNESS":
        "🤒 Больничный",

    "CANCELLED":
        "🚫 Отменено",

    "REJECTED":
        "❌ Отклонено",
}


PAYMENT_STATUS_NAMES = {

    "PAID":
        "✅ Оплачено",

    "FREE":
        "🎁 Бесплатно",

    "AWAITING_PAYMENT":
        "💳 Ожидает оплаты",

    "REFUNDED":
        "↩️ Возвращено",

    "TRANSFERRED":
        "🔁 Перенесено",

    "UNPAID":
        "❌ Не оплачено",

    "UNPAID_CANCELLED":
        "🚫 Отменено из-за неоплаты",
}


HOMEWORK_STATUS_NAMES = {

    "ASSIGNED":
        "📝 Выдано",

    "UNDER_REVIEW":
        "🔎 На проверке",

    "REVISION":
        "🔁 На доработке",

    "REVIEWED":
        "✅ Проверено",
}


# ============================================================
# ПРОВЕРКА АДМИНА
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
# ФОРМАТИРОВАНИЕ
# ============================================================

def format_datetime(
    value
):

    if not value:

        return "—"

    try:

        dt = (
            datetime.fromisoformat(
                value
            )
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=TIMEZONE
            )

        return dt.strftime(
            "%d.%m.%Y %H:%M"
        )

    except Exception:

        return str(
            value
        )


def format_date(
    value
):

    if not value:

        return "—"

    try:

        dt = (
            datetime.fromisoformat(
                value
            )
        )

        return dt.strftime(
            "%d.%m.%Y"
        )

    except Exception:

        return str(
            value
        )


def money(
    value
):

    try:

        value = int(
            round(
                float(value)
            )
        )

    except Exception:

        value = 0

    return (
        f"{value:,}"
        .replace(",", " ")
        + " ₽"
    )


def minutes_to_text(
    minutes
):

    minutes = int(
        minutes or 0
    )

    hours = (
        minutes // 60
    )

    remainder = (
        minutes % 60
    )

    if hours == 0:

        return (
            f"{remainder} мин"
        )

    if remainder == 0:

        return (
            f"{hours} ч"
        )

    return (
        f"{hours} ч "
        f"{remainder} мин"
    )


# ============================================================
# СПИСОК УЧЕНИКОВ
# ============================================================

async def show_students(
    query
):

    users = (
        database
        .get_all_users(
            active_only=True
        )
    )

    if not users:

        await query.edit_message_text(
            "👥 УЧЕНИКИ\n\n"
            "Учеников пока нет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Админка",
                            callback_data=(
                                "admin_main"
                            )
                        )
                    ]
                ])
            )
        )

        return

    # Группируем учеников по классам.
    by_grade = {}

    for user in users:

        grade = int(
            user["grade"]
        )

        by_grade.setdefault(
            grade,
            []
        ).append(
            user
        )

    keyboard = []

    # Быстрый доступ: закреплённые и недавно открытые ученики.
    try:
        pinned = ux_service.pinned_students(query.from_user.id, 5)
        recent = ux_service.recent_students(query.from_user.id, 5)
        if pinned:
            keyboard.append([InlineKeyboardButton("⭐ ЗАКРЕПЛЁННЫЕ", callback_data="ux_noop")])
            for u in pinned:
                keyboard.append([InlineKeyboardButton(f"⭐ {u['name']} • {u['grade']} кл.", callback_data=f"student_view|{u['id']}")])
        if recent:
            keyboard.append([InlineKeyboardButton("🕘 НЕДАВНИЕ", callback_data="ux_noop")])
            for u in recent:
                keyboard.append([InlineKeyboardButton(f"🕘 {u['name']} • {u['grade']} кл.", callback_data=f"student_view|{u['id']}")])
    except Exception:
        pass

    for grade in sorted(
        by_grade.keys()
    ):

        active_count = len(
            by_grade[grade]
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"🎓 {grade} класс "
                    f"• {active_count}"
                ),

                callback_data=(
                    f"student_grade|{grade}"
                )
            )
        ])

    keyboard.append([InlineKeyboardButton("🔎 Найти ученика", callback_data="crm_search")])
    keyboard.append([InlineKeyboardButton("📋 Все ученики", callback_data="student_grade|ALL")])
    keyboard.append([InlineKeyboardButton("⬅️ Админка", callback_data="admin_main"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")])

    await query.edit_message_text(
        "👥 УЧЕНИКИ\n\n"
        "Выберите класс:",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


async def show_students_by_grade(
    query,
    grade
):

    users = (
        database
        .get_all_users(
            active_only=True
        )
    )

    if grade == "ALL":

        selected = list(
            users
        )

        title = (
            "📋 ВСЕ УЧЕНИКИ"
        )

    else:

        grade_int = int(
            grade
        )

        selected = [
            user
            for user in users
            if int(
                user["grade"]
            ) == grade_int
        ]

        title = (
            f"🎓 {grade_int} КЛАСС"
        )

    # Активных показываем первыми,
    # затем по имени.
    selected.sort(
        key=lambda user: (
            0
            if user["active"]
            else 1,
            (
                user["name"]
                or ""
            ).lower(),
        )
    )

    keyboard = []

    for user in selected:

        prefix = (
            "👤"
            if user["active"]
            else "🚫"
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{prefix} "
                    f"{user['name']} "
                    f"• {user['grade']} кл."
                ),

                callback_data=(
                    f"student_view|"
                    f"{user['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ К классам",
            callback_data=(
                "admin_students"
            )
        )
    ])

    await query.edit_message_text(
        (
            f"{title}\n\n"
            f"Учеников: {len(selected)}"
        ),

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# КАРТОЧКА УЧЕНИКА
# ============================================================

async def show_student(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    if user is None:

        await query.edit_message_text(
            "❌ Ученик не найден."
        )

        return

    programs = (
        database
        .get_student_programs(
            user_id,
            active_only=False,
            approved_only=False,
        )
    )

    pending = (
        database
        .get_pending_booking(
            user["id"]
        )
    )

    trial = (
        "использовано"
        if user["trial_used"]
        else "доступно"
    )

    active_text = (
        "✅ Активен"
        if user["active"]
        else "🚫 Неактивен"
    )

    text = (
        "👤 КАРТОЧКА УЧЕНИКА\n\n"

        f"Имя: {user['name']}\n"
        f"🎓 Класс: {user['grade']}\n"
        f"📱 Телефон: {user['phone'] or '—'}\n"
        f"Telegram: "
        f"{('@' + user['telegram_username']) if user['telegram_username'] else '—'}\n"

        f"🖥 Доска: "
        f"{'✅ сохранена' if user['board_url'] else '❌ не задана'}\n\n"

        f"{active_text}\n"
        f"🎁 Пробное: {trial}\n\n"

        "📚 НАПРАВЛЕНИЯ\n"
    )

    try:
        pinned_note = crm_service.get_pinned_note(user_id)
        if pinned_note:
            text += f"\n📌 ВАЖНО: {pinned_note}\n"
    except Exception:
        pass

    active_programs = []

    if not programs:

        text += (
            "\nНаправления пока не добавлены.\n"
        )

    else:

        for index, program in enumerate(
            programs,
            start=1,
        ):

            if program["active"]:

                active_programs.append(
                    program
                )

            try:

                rate = (
                    database
                    .get_program_rate_info(
                        program["id"]
                    )
                )

                balance = minute_balance.get_balance(
                    user_id,
                    minute_balance.effective_hourly_rate(program["id"])
                )

                source = (
                    "👤 индивидуальная"
                    if rate["source"] == "CUSTOM"
                    else "🌐 общая"
                )

                rate_text = (
                    f"{rate['effective_rate']} ₽/час"
                )

                balance_text = (
                    f"{balance['total']} мин"
                )

            except Exception:

                source = ""
                rate_text = "—"
                balance_text = "—"

            primary = (
                "⭐️ "
                if program["is_primary"]
                else ""
            )

            status = (
                program[
                    "approval_status"
                ]
            )

            if status == "APPROVED":

                status_text = "✅"

            elif status == "PENDING":

                status_text = "⏳"

            elif status == "REJECTED":

                status_text = "❌"

            else:

                status_text = "🚫"

            text += (
                "\n"
                f"{index}. "
                f"{status_text} "
                f"{primary}"
                f"{GOAL_NAMES.get(program['study_goal'], program['study_goal'])}"
                " • "
                f"{SUBJECT_NAMES.get(program['subject'], program['subject'])}\n"
                f"   💰 {rate_text}"
            )

            if source:

                text += (
                    f" • {source}"
                )

            text += (
                "\n"
                f"   🎟 {balance_text}"
            )

            underworked = int(
                program[
                    "underworked_minutes_balance"
                ] or 0
            )

            if underworked:

                text += (
                    "\n"
                    f"   🧮 Недоработано: "
                    f"{minutes_to_text(underworked)}"
                )

            text += "\n"

    try:

        stats = (
            database
            .get_learning_statistics(
                user_id
            )
        )

        total = stats["total"]

        text += (
            "\n📊 ОБЩАЯ СТАТИСТИКА\n"

            f"✅ Проведено: "
            f"{total['completed_lessons']}\n"

            f"🎟 Оплачено: "
            f"{minutes_to_text(total['paid_minutes'])}\n"

            f"⏱ Фактически: "
            f"{minutes_to_text(total['actual_minutes'])}\n"

            f"➕ Переработано: "
            f"{minutes_to_text(total['extra_minutes'])}\n"
        )

        if (
            total[
                "homework_accuracy_percent"
            ]
            is not None
        ):

            text += (
                f"📝 ДЗ: "
                f"{total['homework_correct_tasks']} / "
                f"{total['homework_total_tasks']} "
                f"({total['homework_accuracy_percent']}%)\n"
            )

    except Exception as error:

        print(
            "STUDENT CARD STATS:",
            repr(error)
        )

    if pending is not None:

        text += (
            "\n⏳ ЕСТЬ ЗАЯВКА\n"
            f"{format_datetime(pending['start_time'])}\n"
        )

    keyboard = []

    # Направления остаются сверху: это главный контекст ученика.
    for program in active_programs:
        keyboard.append([
            InlineKeyboardButton(
                (("⭐️ " if program["is_primary"] else "📚 ") +
                 f"{GOAL_NAMES.get(program['study_goal'], program['study_goal'])} • {SUBJECT_NAMES.get(program['subject'], program['subject'])}"),
                callback_data=f"admin_program|{program['id']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton("💬 Написать", callback_data=f"crm_write|{user_id}"),
        InlineKeyboardButton("📅 Записать", callback_data=f"admin_manual_for|{user_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("🎟 Баланс минут", callback_data=f"min_balance|{user_id}"),
        InlineKeyboardButton("📝 ДЗ", callback_data=f"student_homeworks|{user_id}"),
    ])
    keyboard.append([
        InlineKeyboardButton("⚡ Следующее действие", callback_data=f"crm_attention|{user_id}"),
        InlineKeyboardButton("🧪 Пробники", callback_data=f"ff_mocks|{user_id}"),
    ])
    try:
        pin_label = "📌 Открепить" if ux_service.is_student_pinned(query.from_user.id, user_id) else "⭐ Закрепить"
        keyboard.append([InlineKeyboardButton(pin_label, callback_data=f"ux_student_pin|{user_id}"), InlineKeyboardButton("••• Ещё", callback_data=f"ux_student_more|{user_id}")])
    except Exception:
        keyboard.append([InlineKeyboardButton("••• Ещё", callback_data=f"ux_student_more|{user_id}")])

    if pending is not None:

        keyboard.append([
            InlineKeyboardButton(
                "⏳ Открыть заявку",
                callback_data=f"admin_request_view|{pending['id']}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            f"⬅️ К {user['grade']} классу",
            callback_data=f"student_grade|{user['grade']}"
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
# БАЛАНС
# ============================================================

async def show_balance(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    if user is None:

        return

    balances = minute_balance.get_balance_by_rate(user["id"])

    text = (
        "🎟 БАЛАНС УЧЕНИКА\n\n"
        f"👤 {user['name']}\n\n"
    )

    if balances:
        total_minutes = 0
        for rate, item in sorted(balances.items()):
            total_minutes += int(item.get("total") or 0)
            if int(rate) == 0:
                text += f"🎁 Бонусная копилка: {int(item.get('bonus') or 0)} мин\n"
            else:
                text += (
                    f"💳 {int(rate):,} ₽ / 60 мин: "
                    f"{int(item.get('paid') or 0)} оплаченных мин"
                ).replace(",", " ") + "\n"
        text += f"\nВсего доступно: {total_minutes} минут"
    else:
        text += "На балансе пока нет минут."

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ К ученику",
                        callback_data=(
                            f"student_view|"
                            f"{user_id}"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# ЗАНЯТИЯ УЧЕНИКА
# ============================================================

async def show_lessons(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    conn = (
        database.connect()
    )

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE user_id = ?

        ORDER BY
            start_time DESC

        LIMIT 30
    """, (
        user_id,
    )).fetchall()

    conn.close()

    if not rows:

        await query.edit_message_text(
            f"📚 ЗАНЯТИЯ\n\n"
            f"👤 {user['name']}\n\n"
            "Занятий пока нет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ К ученику",
                            callback_data=(
                                f"student_view|"
                                f"{user_id}"
                            )
                        )
                    ]
                ])
            )
        )

        return

    keyboard = []

    for lesson in rows:

        status = (
            LESSON_STATUS_NAMES.get(
                lesson[
                    "lesson_status"
                ],
                lesson[
                    "lesson_status"
                ]
            )
        )

        try:

            start_dt = (
                datetime.fromisoformat(
                    lesson[
                        "start_time"
                    ]
                )
            )

            date_text = (
                start_dt.strftime(
                    "%d.%m %H:%M"
                )
            )

        except Exception:

            date_text = (
                lesson[
                    "start_time"
                ]
            )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{date_text} "
                    f"• {status}"
                ),

                callback_data=(
                    f"student_lesson_view|"
                    f"{lesson['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ К ученику",
            callback_data=(
                f"student_view|"
                f"{user_id}"
            )
        )
    ])

    await query.edit_message_text(
        "📚 ИСТОРИЯ ЗАНЯТИЙ\n\n"

        f"👤 {user['name']}\n\n"

        "Последние 30 записей:",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# КАРТОЧКА ЗАНЯТИЯ
# ============================================================

async def show_lesson(
    query,
    lesson_id
):

    lesson = (
        database
        .get_lesson(
            lesson_id
        )
    )

    if lesson is None:

        await query.edit_message_text(
            "❌ Занятие не найдено."
        )

        return

    user = (
        database
        .get_user(
            lesson[
                "user_id"
            ]
        )
    )

    status = (
        LESSON_STATUS_NAMES.get(
            lesson[
                "lesson_status"
            ],
            lesson[
                "lesson_status"
            ]
        )
    )

    payment = (
        PAYMENT_STATUS_NAMES.get(
            lesson[
                "payment_status"
            ],
            lesson[
                "payment_status"
            ]
        )
    )

    text = (
        "📚 ЗАНЯТИЕ\n\n"

        f"👤 "
        f"{user['name']}\n"

        f"📖 "
        f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n"

        f"⏱ План: "
        f"{lesson['duration_minutes']} минут\n"

        f"💰 Цена: "
        f"{money(lesson['price'])}\n\n"

        f"Статус: "
        f"{status}\n"

        f"Оплата: "
        f"{payment}"
    )

    if lesson[
        "request_source"
    ]:

        text += (
            "\nИсточник: "
            f"{lesson['request_source']}"
        )

    if lesson[
        "started_at"
    ]:

        text += (
            "\n\n▶️ Фактическое начало: "
            f"{format_datetime(lesson['started_at'])}"
        )

    if lesson[
        "finished_at"
    ]:

        text += (
            "\n⏹ Фактическое окончание: "
            f"{format_datetime(lesson['finished_at'])}"
        )

    if (
        lesson[
            "actual_duration_minutes"
        ] is not None
        and
        lesson[
            "lesson_status"
        ] == "COMPLETED"
    ):

        text += (
            "\n\n⏱ ОПЛАЧЕНО: "
            f"{lesson['duration_minutes']} мин"

            "\n⏱ ФАКТИЧЕСКИ: "
            f"{lesson['actual_duration_minutes']} мин"

            "\n➕ СВЕРХ: "
            f"{lesson['extra_minutes'] or 0} мин"
        )

    if lesson[
        "sickness_comment"
    ]:

        text += (
            "\n\n🤒 Комментарий к больничному:\n"
            f"{lesson['sickness_comment']}"
        )

    if lesson[
        "sickness_number_in_month"
    ]:

        text += (
            "\nБольничный №"
            f"{lesson['sickness_number_in_month']} "
            "за месяц"
        )

    if lesson[
        "cancellation_reason"
    ]:

        text += (
            "\n\nПричина отмены:\n"
            f"{lesson['cancellation_reason']}"
        )

    keyboard = []

    if (
        lesson[
            "lesson_status"
        ] in {
            "CONFIRMED",
            "IN_PROGRESS",
            "COMPLETED",
        }
    ):

        keyboard.append([
            InlineKeyboardButton(
                "⚙️ Управлять занятием",
                callback_data=(
                    f"admin_lesson_view|"
                    f"{lesson_id}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ К занятиям",
            callback_data=(
                f"student_lessons|"
                f"{user['id']}"
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
# ДЗ
# ============================================================

async def show_homeworks(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    rows = (
        database
        .get_student_homework(
            user_id,
            active_only=False
        )
    )

    if not rows:

        await query.edit_message_text(
            "📝 ДОМАШНИЕ ЗАДАНИЯ\n\n"

            f"👤 "
            f"{user['name']}\n\n"

            "Домашних заданий пока нет.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ К ученику",
                            callback_data=(
                                f"student_view|"
                                f"{user_id}"
                            )
                        )
                    ]
                ])
            )
        )

        return

    keyboard = []

    for homework in rows[:30]:

        status = (
            HOMEWORK_STATUS_NAMES.get(
                homework[
                    "status"
                ],
                homework[
                    "status"
                ]
            )
        )

        title = (
            homework[
                "title"
            ]
            or
            f"ДЗ #{homework['id']}"
        )

        if len(title) > 30:

            title = (
                title[:27]
                + "..."
            )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{status} "
                    f"• {title}"
                ),

                callback_data=(
                    f"student_homework_view|"
                    f"{homework['id']}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ К ученику",
            callback_data=(
                f"student_view|"
                f"{user_id}"
            )
        )
    ])

    await query.edit_message_text(
        "📝 ДОМАШНИЕ ЗАДАНИЯ\n\n"

        f"👤 "
        f"{user['name']}",

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# КАРТОЧКА ДЗ
# ============================================================

async def show_homework(
    query,
    homework_id
):

    homework = (
        database
        .get_homework(
            homework_id
        )
    )

    if homework is None:

        await query.edit_message_text(
            "❌ ДЗ не найдено."
        )

        return

    user = (
        database
        .get_user(
            homework[
                "user_id"
            ]
        )
    )

    status = (
        HOMEWORK_STATUS_NAMES.get(
            homework[
                "status"
            ],
            homework[
                "status"
            ]
        )
    )

    text = (
        "📝 ДОМАШНЕЕ ЗАДАНИЕ\n\n"

        f"👤 "
        f"{user['name']}\n"

        f"Статус: "
        f"{status}\n\n"

        f"{homework['description'] or '—'}"
    )

    if homework[
        "deadline"
    ]:

        text += (
            "\n\n⏰ Срок: "
            f"{format_datetime(homework['deadline'])}"
        )

    if homework[
        "source_reference"
    ]:

        text += (
            "\n\n🔗 Источник/номер:\n"
            f"{homework['source_reference']}"
        )

    try:
        import homework_attachments

        attachment_count = (
            homework_attachments
            .count_for_homework(
                homework_id
            )
        )

    except Exception as exc:

        print(
            "HOMEWORK ATTACHMENT COUNT ERROR:",
            repr(exc),
        )

        attachment_count = 0


    if attachment_count:

        text += (
            "\n\n📎 Вложения: "
            f"{attachment_count}"
        )


    keyboard = []


    if attachment_count:

        keyboard.append([
            InlineKeyboardButton(
                "📎 Показать вложения",
                callback_data=(
                    f"student_homework_files|"
                    f"{homework_id}"
                )
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "📤 Отправить ученику ещё раз",
                callback_data=(
                    f"student_homework_resend|"
                    f"{homework_id}"
                )
            )
        ])


    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Все ДЗ ученика",
            callback_data=(
                f"student_homeworks|"
                f"{user['id']}"
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
# СТАТИСТИКА
# ============================================================

async def show_statistics(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    if user is None:

        return

    stats = (
        database
        .get_student_statistics(
            user_id
        )
    )

    difference = (
        stats[
            "actual_minutes"
        ]
        -
        stats[
            "paid_minutes"
        ]
    )

    if difference > 0:

        difference_text = (
            f"+{minutes_to_text(difference)}"
        )

    elif difference < 0:

        difference_text = (
            f"-{minutes_to_text(abs(difference))}"
        )

    else:

        difference_text = (
            "0 мин"
        )

    if stats[
        "paid_minutes"
    ] > 0:

        percent = round(
            stats[
                "actual_minutes"
            ]
            /
            stats[
                "paid_minutes"
            ]
            * 100
        )

    else:

        percent = 0

    current_minute_balance = minute_balance.get_balance(user_id)

    text = (
        "📊 СТАТИСТИКА\n\n"

        f"👤 "
        f"{user['name']}\n\n"

        "📚 ПОСЕЩАЕМОСТЬ\n"

        f"✅ Проведено: "
        f"{stats['completed_lessons']}\n"

        f"❌ Неявок: "
        f"{stats['no_show']}\n"

        f"⚠️ Поздних переносов: "
        f"{stats['late_cancelled']}\n"

        f"🤒 Больничных: "
        f"{stats['sickness']}\n\n"

        "⏱ ВРЕМЯ\n"

        f"💳 Оплачено: "
        f"{minutes_to_text(stats['paid_minutes'])}\n"

        f"⏱ Фактически: "
        f"{minutes_to_text(stats['actual_minutes'])}\n"

        f"Разница: "
        f"{difference_text}\n"

        f"Факт к оплате: "
        f"{percent}%\n"

        f"➕ Всего переработано: "
        f"{minutes_to_text(stats['extra_minutes_total'])}\n"

        f"⏳ Сейчас накоплено: "
        f"{minutes_to_text(stats['extra_minutes_balance'])}\n"

        f"🎁 Бонусная копилка сейчас: "
        f"{current_minute_balance['bonus']} мин\n\n"

        "🎟 ТЕКУЩИЙ БАЛАНС\n"

        f"💳 Оплаченных минут: "
        f"{current_minute_balance['paid']}\n"

        f"🎁 Бонусных минут: "
        f"{current_minute_balance['bonus']}\n"

        f"Всего минут: "
        f"{current_minute_balance['total']}\n\n"

        "📝 ДОМАШНИЕ ЗАДАНИЯ\n"

        f"Всего: "
        f"{stats['homework_total']}\n"

        f"Проверено: "
        f"{stats['homework_reviewed']}"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "📋 По занятиям",
                callback_data=(
                    f"student_stats_lessons|"
                    f"{user_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "👨‍👩‍👦 Отчёт для родителей",
                callback_data=(
                    f"student_parent_report|"
                    f"{user_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ К ученику",
                callback_data=(
                    f"student_view|"
                    f"{user_id}"
                )
            )
        ],
    ]

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup(
                keyboard
            )
        )
    )


# ============================================================
# СТАТИСТИКА ПО ЗАНЯТИЯМ
# ============================================================

async def show_statistics_lessons(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    stats = (
        database
        .get_student_statistics(
            user_id
        )
    )

    lessons = (
        stats[
            "lessons"
        ]
    )

    if not lessons:

        text = (
            "📋 СТАТИСТИКА ПО ЗАНЯТИЯМ\n\n"
            "Данных пока нет."
        )

    else:

        lines = [
            "📋 СТАТИСТИКА ПО ЗАНЯТИЯМ",
            "",
            f"👤 {user['name']}",
            "",
        ]

        # последние 20
        for lesson in (
            lessons[-20:]
        ):

            try:

                dt = (
                    datetime.fromisoformat(
                        lesson[
                            "date"
                        ]
                    )
                )

                date_text = (
                    dt.strftime(
                        "%d.%m"
                    )
                )

            except Exception:

                date_text = (
                    lesson[
                        "date"
                    ]
                )

            status = (
                LESSON_STATUS_NAMES.get(
                    lesson[
                        "status"
                    ],
                    lesson[
                        "status"
                    ]
                )
            )

            lines.append(
                (
                    f"{date_text} • "
                    f"{status}\n"

                    f"💳 "
                    f"{lesson['paid_minutes']} мин"
                    f" / "

                    f"⏱ "
                    f"{lesson['actual_minutes']} мин"
                )
            )

        text = (
            "\n\n".join(
                lines
            )
        )

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ К статистике",
                        callback_data=(
                            f"student_stats|"
                            f"{user_id}"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# ОТЧЁТ РОДИТЕЛЯМ
# ============================================================

async def show_parent_report(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    stats = (
        database
        .get_student_statistics(
            user_id
        )
    )

    if stats[
        "paid_minutes"
    ] > 0:

        percent = round(
            stats[
                "actual_minutes"
            ]
            /
            stats[
                "paid_minutes"
            ]
            * 100
        )

    else:

        percent = 0

    text = (
        "👨‍👩‍👦 ОТЧЁТ ДЛЯ РОДИТЕЛЕЙ\n\n"

        f"Ученик: "
        f"{user['name']}\n"

        f"Класс: "
        f"{user['grade']}\n"

        f"Предмет: "
        f"{SUBJECT_NAMES.get(user['main_subject'], user['main_subject'])}\n\n"

        "📚 ЗАНЯТИЯ\n"

        f"Проведено: "
        f"{stats['completed_lessons']}\n"

        f"Неявки: "
        f"{stats['no_show']}\n"

        f"Поздние переносы: "
        f"{stats['late_cancelled']}\n"

        f"Больничные: "
        f"{stats['sickness']}\n\n"

        "⏱ УЧЕБНОЕ ВРЕМЯ\n"

        f"Оплачено: "
        f"{minutes_to_text(stats['paid_minutes'])}\n"

        f"Фактически проведено: "
        f"{minutes_to_text(stats['actual_minutes'])}\n"

        f"Фактическое время к оплаченному: "
        f"{percent}%\n"

        f"Сверх оплаченного времени: "
        f"{minutes_to_text(stats['extra_minutes_total'])}\n"

        f"Бонусная копилка: "
        f"{minute_balance.get_balance(user_id)['bonus']} мин\n\n"

        "📝 ДОМАШНИЕ ЗАДАНИЯ\n"

        f"Всего выдано: "
        f"{stats['homework_total']}\n"

        f"Проверено: "
        f"{stats['homework_reviewed']}\n\n"

        "🎟 ТЕКУЩИЙ БАЛАНС\n"

        f"Осталось минут: "
        f"{minute_balance.get_balance(user_id)['total']}"
    )

    await query.edit_message_text(
        text,

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ К статистике",
                        callback_data=(
                            f"student_stats|"
                            f"{user_id}"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# ВКЛ / ВЫКЛ УЧЕНИКА
# ============================================================

async def toggle_student_active(
    query,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    if user is None:

        return

    new_value = (
        not bool(
            user[
                "active"
            ]
        )
    )

    database.set_user_active(
        user_id,
        new_value
    )

    await show_student(
        query,
        user_id
    )


# ============================================================
# БЫСТРАЯ ЗАПИСЬ ИЗ КАРТОЧКИ
# ============================================================

async def book_student(
    query,
    context,
    user_id
):

    user = (
        database
        .get_user(
            user_id
        )
    )

    if user is None:

        await query.edit_message_text(
            "❌ Ученик не найден."
        )

        return

    # Сохраняем ученика.
    # В финальном bot.py/admin.py
    # это позволит сразу перейти
    # к выбору даты без повторного
    # выбора ученика.

    context.user_data[
        "manual_user_id"
    ] = user_id

    await query.edit_message_text(
        "📅 ЗАПИСАТЬ УЧЕНИКА\n\n"

        f"👤 "
        f"{user['name']}\n\n"

        "Нажмите кнопку ниже, "
        "чтобы открыть форму записи.",

        reply_markup=(
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "➕ Продолжить запись",
                        callback_data=(
                            "admin_manual_lesson"
                        )
                    )
                ],

                [
                    InlineKeyboardButton(
                        "⬅️ К ученику",
                        callback_data=(
                            f"student_view|"
                            f"{user_id}"
                        )
                    )
                ]
            ])
        )
    )


# ============================================================
# ОСНОВНОЙ CALLBACK
# ============================================================

async def students_buttons(
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


    # ========================================================
    # LIST
    # ========================================================

    if data == "admin_students":

        await show_students(
            query
        )

        return


    # ========================================================
    # CLASS
    # ========================================================

    if data.startswith(
        "student_grade|"
    ):

        grade = (
            data.split("|")[1]
        )

        await show_students_by_grade(
            query,
            grade
        )

        return


    # ========================================================
    # VIEW
    # ========================================================

    if data.startswith(
        "student_view|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        try:
            ux_service.mark_recent_student(query.from_user.id, user_id)
        except Exception:
            pass
        await show_student(
            query,
            user_id
        )

        return


    # ========================================================
    # BOOK
    # ========================================================

    if data.startswith(
        "student_book|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await book_student(
            query,
            context,
            user_id
        )

        return


    # ========================================================
    # BALANCE
    # ========================================================

    if data.startswith(
        "student_balance|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_balance(
            query,
            user_id
        )

        return


    # ========================================================
    # LESSONS
    # ========================================================

    if data.startswith(
        "student_lessons|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_lessons(
            query,
            user_id
        )

        return


    # ========================================================
    # LESSON VIEW
    # ========================================================

    if data.startswith(
        "student_lesson_view|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_lesson(
            query,
            lesson_id
        )

        return


    # ========================================================
    # HOMEWORKS
    # ========================================================

    if data.startswith(
        "student_homeworks|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_homeworks(
            query,
            user_id
        )

        return


    # ========================================================
    # HOMEWORK ATTACHMENTS
    # ========================================================

    if data.startswith(
        "student_homework_files|"
    ):

        homework_id = int(
            data.split("|")[1]
        )

        import homework_attachments

        sent = (
            homework_attachments
            .send_to_admin_telegram(
                homework_id,
                query.message.chat_id,
                (
                    "📎 Вложения "
                    f"ДЗ #{homework_id}"
                ),
            )
        )

        if sent:

            await query.message.reply_text(
                (
                    "✅ Вложения отправлены сюда.\n"
                    f"Файлов: {sent}"
                )
            )

        else:

            await query.message.reply_text(
                "⚠️ Вложения сейчас недоступны."
            )

        return


    if data.startswith(
        "student_homework_resend|"
    ):

        homework_id = int(
            data.split("|")[1]
        )

        import homework_attachments

        result = (
            homework_attachments
            .resend_to_student(
                homework_id,
                (
                    "📝 Повторная отправка "
                    f"вложений ДЗ #{homework_id}"
                ),
            )
        )

        await query.message.reply_text(
            (
                "📤 Вложения отправлены повторно.\n\n"
                f"Telegram: {result['telegram']}\n"
                f"VK: {result['vk']}\n"
                f"Всего вложений: {result['count']}"
            )
        )

        return


    # ========================================================
    # HOMEWORK VIEW
    # ========================================================

    if data.startswith(
        "student_homework_view|"
    ):

        homework_id = int(
            data.split("|")[1]
        )

        await show_homework(
            query,
            homework_id
        )

        return


    # ========================================================
    # STATS
    # ========================================================

    if data.startswith(
        "student_stats|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_statistics(
            query,
            user_id
        )

        return


    # ========================================================
    # STATS LESSONS
    # ========================================================

    if data.startswith(
        "student_stats_lessons|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_statistics_lessons(
            query,
            user_id
        )

        return


    # ========================================================
    # PARENT REPORT
    # ========================================================

    if data.startswith(
        "student_parent_report|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_parent_report(
            query,
            user_id
        )

        return


    # ========================================================
    # ACTIVE
    # ========================================================

    if data.startswith(
        "student_toggle_active|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await toggle_student_active(
            query,
            user_id
        )

        return


# ============================================================
# HANDLER №1
# ============================================================

def get_students_admin_handler():

    return CallbackQueryHandler(

        students_buttons,

        pattern=(
            r"^admin_students$"
        )
    )


# ============================================================
# HANDLER №2
# ============================================================

def get_students_callback_handler():

    return CallbackQueryHandler(

        students_buttons,

        pattern=(
            r"^(?:student_grade\||student_homeworks\||student_homework_view\||student_homework_files\||student_homework_resend\||student_view\|)"
        )
    )
