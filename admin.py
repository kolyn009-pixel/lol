# ============================================================
# admin.py
# TutorBot — панель преподавателя
# ============================================================

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
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database
from ux_final import service as ux_service
from core import admin_roles
from core import user_timezone
from core import analytics as core_analytics
from core import audit_log as core_audit_log
from core import financial_ledger as core_financial_ledger
from core import admin_inbox as core_admin_inbox
from crm_plus import service as crm_message_service
from core import minute_balance as core_minute_balance


# ============================================================
# CONFIG
# ============================================================

# ВАЖНО:
# Впиши сюда свой Telegram ID
ADMIN_ID = 913246612


# ============================================================
# STATES
# ============================================================

(
    # ручная запись
    MANUAL_STUDENT,
    MANUAL_DATE,
    MANUAL_TIME,
    MANUAL_DURATION,
    MANUAL_PAYMENT_MODE,

    # промокод
    PROMO_CODE,
    PROMO_TYPE,
    PROMO_VALUE,
    PROMO_MAX_USES,
    PROMO_USER_LIMIT,
    PROMO_EXPIRES,

    # причина отказа
    REJECT_LESSON_REASON,

    # цены
    PRICE_DEFAULT_VALUE,
    PRICE_STUDENT_VALUE,

    # направления ученика
    PROGRAM_SUBJECT,
    PROGRAM_GOAL,
    PROGRAM_PRICE,

    # постоянная доска ученика
    BOARD_URL,

    # ссылка на занятие
    LESSON_LINK,

    # дополнительное ДЗ
    EXTRA_HW_TEXT,
    EXTRA_HW_DEADLINE,

    # ручное время задержки преподавателя
    DELAY_CUSTOM_TIME,

    # карточка преподавателя / время связи
    CONTACT_NAME,
    CONTACT_DESCRIPTION,
    CONTACT_TELEGRAM,
    CONTACT_PHONE,
    CONTACT_NOTE,
    CONTACT_DAY_TIME,

    # способы оплаты
    PAYMENT_METHOD_TITLE,
    PAYMENT_METHOD_DETAILS,

) = range(3000, 3030)


# ============================================================
# CONSTANTS
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


SUBJECT_NAMES = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}


GOAL_NAMES = {
    "EGE": "ЕГЭ",
    "OGE": "ОГЭ",
    "OLYMPIAD": "Олимпиада",
    "SCHOOL": "Школьная программа",
}


def program_title(
    study_goal,
    subject
):

    return (
        f"{GOAL_NAMES.get(study_goal, study_goal)} • "
        f"{SUBJECT_NAMES.get(subject, subject)}"
    )


def program_status_name(
    status
):

    names = {
        "PENDING": "⏳ Ожидает подтверждения",
        "APPROVED": "✅ Подтверждено",
        "REJECTED": "❌ Отклонено",
        "DISABLED": "🚫 Отключено",
    }

    return names.get(
        status,
        "Неизвестный статус",
    )


PAYMENT_NAMES = {
    "PAID": "✅ Оплачено",
    "FREE": "🎁 Бесплатно",
    "AWAITING_PAYMENT": "💳 Ожидает оплаты",
    "RESERVED_BALANCE": "🎟 Зарезервировано",
    "REFUNDED": "↩️ Возвращено",
    "UNPAID": "❌ Не оплачено",
    "WAITING": "💳 Ожидает оплаты",
    "RECEIPT_SENT": "🧾 Чек отправлен",
    "UNPAID_CANCELLED": "❌ Отменено из-за неоплаты",
    "TRANSFERRED": "🔁 Перенесено",
}


LESSON_STATUS_NAMES = {
    "PENDING": "🟡 Заявка",
    "CONFIRMED": "🟢 Подтверждено",
    "IN_PROGRESS": "▶️ Идёт",
    "COMPLETED": "✅ Проведено",
    "CANCELLED": "❌ Отменено",
    "REJECTED": "🚫 Отклонено",
    "NO_SHOW": "👻 Не пришёл",
    "LATE_CANCELLED": "⚠️ Поздняя отмена",
    "SICKNESS": "🤒 Больничный",
}


# ============================================================
# ACCESS
# ============================================================

def is_admin(update: Update):

    return bool(
        update.effective_user
        and admin_roles.is_admin_id(update.effective_user.id)
    )


async def deny_access(update: Update):

    if update.callback_query:

        await update.callback_query.answer(
            "🔒 Доступ только преподавателю.",
            show_alert=True,
        )

    elif update.message:

        await update.message.reply_text(
            "🔒 Команда доступна только преподавателю."
        )


# ============================================================
# FORMAT HELPERS
# ============================================================

def format_date(value):

    if not value:
        return "—"

    try:

        dt = datetime.fromisoformat(value)

        return dt.strftime(
            "%d.%m.%Y"
        )

    except Exception:

        try:

            return (
                datetime.strptime(
                    value,
                    "%Y-%m-%d",
                )
                .strftime(
                    "%d.%m.%Y"
                )
            )

        except Exception:

            return str(value)


def format_datetime(value):

    if not value:
        return "—"

    try:

        return (
            datetime.fromisoformat(value)
            .strftime(
                "%d.%m.%Y %H:%M"
            )
        )

    except Exception:

        return str(value)


def format_time(value):

    if not value:
        return "—"

    try:

        return (
            datetime.fromisoformat(value)
            .strftime("%H:%M")
        )

    except Exception:

        return str(value)


def subject_name(value):

    return SUBJECT_NAMES.get(
        value,
        value or "—",
    )


def goal_name(value):

    return GOAL_NAMES.get(
        value,
        value or "—",
    )


# ============================================================
# COUNTERS
# ============================================================

def count_pending_lessons():

    try:

        return len(
            database.get_pending_requests()
        )

    except Exception:

        return 0


def count_pending_regular():

    try:

        return len(
            database
            .get_pending_regular_schedule_requests()
        )

    except Exception:

        return 0


def count_unpaid():

    conn = database.connect()

    value = conn.execute("""
        SELECT COUNT(*)

        FROM lessons

        WHERE
            lesson_status = 'CONFIRMED'

            AND payment_status =
                'AWAITING_PAYMENT'
    """).fetchone()[0]

    conn.close()

    return int(value)


# ============================================================
# ADMIN MAIN MENU
# ============================================================

def _admin_home_snapshot():
    """Small, resilient snapshot for the teacher home screen."""
    snap = {
        "lessons": 0,
        "messages": 0,
        "unpaid": 0,
        "attention": 0,
        "tasks": 0,
        "review_total": 0,
    }
    try:
        d = crm_message_service.today_dashboard()
        snap["lessons"] = len(d.get("lessons") or [])
        snap["unpaid"] = int(d.get("unpaid") or 0)
        snap["attention"] = len(d.get("attention") or [])
    except Exception:
        pass
    try:
        snap["messages"] = int(crm_message_service.message_counts().get("unread") or 0)
    except Exception:
        try:
            snap["messages"] = int(core_admin_inbox.counts().get("total") or 0)
        except Exception:
            pass
    try:
        from core import teacher_tasks
        teacher_tasks.sync_auto()
        snap["tasks"] = len(teacher_tasks.list_open(50))
    except Exception:
        pass
    snap["review_total"] = snap["messages"] + snap["unpaid"] + snap["attention"]
    return snap


def admin_home_text():
    s = _admin_home_snapshot()
    try:
        tz_name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
        hour = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        hour = datetime.now().hour
    greeting = "Доброе утро!" if hour < 12 else ("Добрый день!" if hour < 18 else "Добрый вечер!")
    if s["review_total"]:
        state = f"🔴 Есть {s['review_total']} вопрос(а), которые лучше разобрать."
    else:
        state = "🟢 Всё спокойно. Я рядом, если понадобится помощь."
    return (
        "💜 АДЕЛИЯ • ГЛАВНАЯ\n\n"
        f"{greeting}\n\n"
        f"{state}\n\n"
        f"📅 Сегодня занятий: {s['lessons']}\n"
        f"💬 Ждут ответа: {s['messages']}\n"
        f"💳 Не оплачено: {s['unpaid']}\n"
        f"⚠️ Требуют внимания: {s['attention']}\n"
        f"📌 Рабочих задач: {s['tasks']}\n\n"
        f"🌍 Ваше время: {user_timezone.zone_label(database.get_setting('bot_timezone', 'Europe/Samara') or 'Europe/Samara')}"
    )


def admin_menu():
    s = _admin_home_snapshot()
    review_label = f"▶️ Разобрать всё • {s['review_total']}" if s["review_total"] else "▶️ Разобрать всё"
    try:
        tz_name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
        hour = datetime.now(ZoneInfo(tz_name)).hour
    except Exception:
        hour = datetime.now().hour
    suffix = f" • {s['review_total']}" if s["review_total"] else ""
    day_label = f"🌅 Подготовить день{suffix}" if hour < 12 else (f"🌙 Закрыть день{suffix}" if hour >= 18 else review_label)

    keyboard = [
        [InlineKeyboardButton(day_label, callback_data="ux_review_start")],
        [InlineKeyboardButton("📅 Сегодня", callback_data="crm_today"),
         InlineKeyboardButton("👥 Ученики", callback_data="admin_students")],
        [InlineKeyboardButton("⚙️ Моё расписание", callback_data="admin_schedule")],
        [InlineKeyboardButton(f"📌 Мои задачи • {s['tasks']}", callback_data="task_home")],
        [InlineKeyboardButton(f"💬 Сообщения • {s['messages']}", callback_data="admin_student_messages"),
         InlineKeyboardButton("➕ Записать", callback_data="admin_manual_lesson")],
        [InlineKeyboardButton(f"💳 Оплаты • {s['unpaid']}", callback_data="mh_debts"),
         InlineKeyboardButton("🔎 Найти", callback_data="crm_search")],
        [InlineKeyboardButton("📢 Канал", callback_data="admin_free_windows"),
         InlineKeyboardButton("👨‍👩‍👧 Родители", callback_data="admin_parents")],
        [InlineKeyboardButton("💜 Спросить Аделию", callback_data="mh_ask")],
        [InlineKeyboardButton("••• Ещё", callback_data="ux_all"),
         InlineKeyboardButton("⚙️ Настройки", callback_data="ux_settings")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ============================================================
# TEACHER CONTACT CARD
# ============================================================

CONTACT_DAY_NAMES = {
    0: "Понедельник",
    1: "Вторник",
    2: "Среда",
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def _contact_setting(key, default=""):
    return database.get_setting(key, default) or default


def _contact_day_value(day):
    return _contact_setting(f"teacher_contact_day_{day}", "выходной")


async def show_admin_contact(query):
    name = _contact_setting("teacher_name", "Николай")
    description = _contact_setting("teacher_description", "Преподаватель физики и химии")
    telegram = _contact_setting("teacher_telegram", "не указан")
    phone = _contact_setting("teacher_phone", "не указан")
    note = _contact_setting("teacher_contact_note", "")
    lines = [
        "👨‍🏫 МОЯ ИНФОРМАЦИЯ",
        "",
        f"Имя: {name}",
        f"Описание: {description}",
        f"Telegram: {telegram}",
        f"Телефон: {phone}",
        "",
        "🕐 Время для связи:",
    ]
    for day in range(7):
        lines.append(f"• {CONTACT_DAY_NAMES[day]}: {_contact_day_value(day)}")
    if note:
        lines.extend(["", f"ℹ️ {note}"])
    kb = [
        [InlineKeyboardButton("✏️ Имя", callback_data="admin_contact_edit_name"), InlineKeyboardButton("📝 Описание", callback_data="admin_contact_edit_description")],
        [InlineKeyboardButton("💬 Telegram", callback_data="admin_contact_edit_telegram"), InlineKeyboardButton("📞 Телефон", callback_data="admin_contact_edit_phone")],
        [InlineKeyboardButton("ℹ️ Примечание", callback_data="admin_contact_edit_note")],
    ]
    for day in range(7):
        kb.append([InlineKeyboardButton(f"🕐 {CONTACT_DAY_NAMES[day]} · {_contact_day_value(day)}", callback_data=f"admin_contact_day|{day}")])
    kb.append([InlineKeyboardButton("⬅️ Админка", callback_data="admin_main")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def _contact_text_entry(update, context, state, field_name, prompt):
    query = update.callback_query
    if not is_admin(update):
        await deny_access(update); return ConversationHandler.END
    await query.answer()
    context.user_data["contact_field"] = field_name
    await query.edit_message_text(prompt + "\n\nДля очистки отправьте: -")
    return state


async def contact_name_entry(update, context):
    return await _contact_text_entry(update, context, CONTACT_NAME, "teacher_name", "Введите имя преподавателя:")
async def contact_description_entry(update, context):
    return await _contact_text_entry(update, context, CONTACT_DESCRIPTION, "teacher_description", "Введите короткое описание (например: Преподаватель физики и химии):")
async def contact_telegram_entry(update, context):
    return await _contact_text_entry(update, context, CONTACT_TELEGRAM, "teacher_telegram", "Введите Telegram для связи, например @username:")
async def contact_phone_entry(update, context):
    return await _contact_text_entry(update, context, CONTACT_PHONE, "teacher_phone", "Введите телефон для связи:")
async def contact_note_entry(update, context):
    return await _contact_text_entry(update, context, CONTACT_NOTE, "teacher_contact_note", "Введите дополнительную информацию для учеников и родителей:")


async def contact_text_handler(update, context):
    if not is_admin(update): return ConversationHandler.END
    value = (update.message.text or "").strip()
    field = context.user_data.pop("contact_field", None)
    if not field: return ConversationHandler.END
    database.set_setting(field, "" if value == "-" else value)
    await update.message.reply_text("✅ Сохранено. Откройте /admin → «Моя информация», чтобы увидеть карточку.")
    return ConversationHandler.END


async def contact_day_entry(update, context):
    query = update.callback_query
    if not is_admin(update):
        await deny_access(update); return ConversationHandler.END
    await query.answer()
    day = int(query.data.split("|", 1)[1])
    context.user_data["contact_day"] = day
    await query.edit_message_text(
        f"🕐 {CONTACT_DAY_NAMES[day]}\n\nВведите интервал в формате 10:00-20:00.\nЕсли в этот день связываться нельзя — отправьте «выходной»."
    )
    return CONTACT_DAY_TIME


async def contact_day_time_handler(update, context):
    if not is_admin(update): return ConversationHandler.END
    import re
    raw = (update.message.text or "").strip().lower().replace("–", "-").replace("—", "-")
    day = context.user_data.pop("contact_day", None)
    if day is None: return ConversationHandler.END
    if raw in {"выходной", "нет", "off"}:
        value = "выходной"
    else:
        m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)\s*-\s*([01]?\d|2[0-3]):([0-5]\d)", raw)
        if not m:
            context.user_data["contact_day"] = day
            await update.message.reply_text("Неверный формат. Пример: 10:00-20:00 или «выходной».")
            return CONTACT_DAY_TIME
        value = f"{int(m.group(1)):02d}:{m.group(2)}-{int(m.group(3)):02d}:{m.group(4)}"
    database.set_setting(f"teacher_contact_day_{day}", value)
    await update.message.reply_text(f"✅ {CONTACT_DAY_NAMES[day]}: {value}. Откройте /admin → «Моя информация» для дальнейшей настройки.")
    return ConversationHandler.END


# ============================================================
# /admin
# ============================================================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not is_admin(update):

        await deny_access(update)
        return

    await update.message.reply_text(
        admin_home_text(),
        reply_markup=admin_menu(),
    )


async def show_admin_main(query):

    await query.edit_message_text(
        admin_home_text(),
        reply_markup=admin_menu(),
    )


# ============================================================
# LESSON REQUESTS
# ============================================================

async def show_requests(query):

    rows = database.get_pending_requests()

    if not rows:

        await query.edit_message_text(
            "🔔 ЗАЯВКИ НА ЗАНЯТИЯ\n\n"
            "Новых заявок нет.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Админка",
                        callback_data="admin_main",
                    )
                ]
            ]),
        )

        return

    keyboard = []

    for lesson in rows:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"🔔 {lesson['name']} • "
                    f"{format_datetime(lesson['start_time'])}"
                ),

                callback_data=(
                    f"admin_request_view|"
                    f"{lesson['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "🔔 ЗАЯВКИ НА ЗАНЯТИЯ",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def show_request(
    query,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        await query.answer(
            "Заявка не найдена.",
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    balance = core_minute_balance.get_balance(
        user["id"], hourly_rate=int(lesson["hourly_rate"] or 0)
    )

    text = (
        "🔔 ЗАЯВКА НА ЗАНЯТИЕ\n\n"

        f"👤 {user['name']}\n"
        f"🎓 {user['grade']} класс\n\n"

        f"🎯 {goal_name(lesson['study_goal'])}\n"
        f"📚 {subject_name(lesson['subject'])}\n\n"

        f"📅 {format_datetime(lesson['start_time'])}\n"
        f"⏱ {lesson['duration_minutes']} минут\n\n"

        f"💰 Стоимость: {lesson['price']} ₽\n"

        f"🎟 Баланс: {balance['total']} минут "
        f"(оплачено {balance['paid']}, бонус {balance['bonus']})\n\n"

        f"Статус оплаты: "
        f"{PAYMENT_NAMES.get(lesson['payment_status'], lesson['payment_status'])}"
    )

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "✅ Подтвердить",
                    callback_data=(
                        f"admin_request_approve|"
                        f"{lesson_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Отклонить",
                    callback_data=(
                        f"admin_request_reject|"
                        f"{lesson_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ К заявкам",
                    callback_data="admin_requests",
                )
            ],
        ]),
    )


# ============================================================
# APPROVE REQUEST
# ============================================================

async def approve_request(
    query,
    context,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        await query.answer(
            "Заявка не найдена.",
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    try:

        database.approve_lesson_request(
            lesson_id
        )

    except Exception as error:

        print(
            "APPROVE REQUEST ERROR:",
            lesson_id,
            type(error).__name__,
            repr(error),
        )

        try:
            await query.edit_message_text(
                "❌ Не удалось подтвердить заявку.\n\n"
                f"Ошибка: {type(error).__name__}: {error}"
            )
        except Exception as edit_error:
            print(
                "APPROVE REQUEST UI ERROR:",
                repr(edit_error),
            )

        return

    lesson = database.get_lesson(
        lesson_id
    )

    if user["telegram_id"]:

        try:

            await context.bot.send_message(

                chat_id=user["telegram_id"],

                text=(
                    "✅ ЗАПИСЬ ПОДТВЕРЖДЕНА\n\n"

                    f"📅 "
                    f"{format_datetime(lesson['start_time'])}\n"

                    f"📚 "
                    f"{subject_name(lesson['subject'])}\n"

                    f"⏱ "
                    f"{lesson['duration_minutes']} минут\n\n"

                    "До встречи!"
                ),
            )

        except Exception as error:

            print(
                "APPROVE STUDENT NOTIFY:",
                repr(error),
            )

    await query.edit_message_text(
        "✅ Заявка подтверждена.\n\n"

        f"👤 {user['name']}\n"
        f"📅 {format_datetime(lesson['start_time'])}",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔔 К заявкам",
                    callback_data="admin_requests",
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Админка",
                    callback_data="admin_main",
                )
            ],
        ]),
    )


# ============================================================
# REJECT REQUEST
# ============================================================

async def reject_request(
    query,
    context,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:
        return

    user = database.get_user(
        lesson["user_id"]
    )

    database.reject_lesson_request(
        lesson_id,
        reason=(
            "Отклонено преподавателем"
        ),
    )

    if user["telegram_id"]:

        try:

            await context.bot.send_message(

                chat_id=user["telegram_id"],

                text=(
                    "❌ Заявка на занятие "
                    "отклонена преподавателем.\n\n"

                    "Вы можете выбрать другое "
                    "свободное время."
                ),
            )

        except Exception as error:

            print(
                "REJECT STUDENT NOTIFY:",
                repr(error),
            )

    await query.edit_message_text(
        "❌ Заявка отклонена.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔔 К заявкам",
                    callback_data="admin_requests",
                )
            ]
        ]),
    )

# ============================================================
# ADMIN LESSON MANAGEMENT HELPERS
# ============================================================

def get_upcoming_admin_lessons(
    limit=100
):

    conn = database.connect()

    rows = conn.execute("""
        SELECT

            l.*,

            u.name,
            u.grade,
            u.telegram_id,
            u.telegram_username

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            l.start_time >= ?

            AND l.lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS'
            )

        ORDER BY l.start_time

        LIMIT ?
    """, (
        database.now_iso(),
        int(limit),
    )).fetchall()

    conn.close()

    return rows


def cancel_lesson_by_admin(
    lesson_id,
    reason="ADMIN_CANCEL",
    refund=True,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson["lesson_status"] in {
        "COMPLETED",
        "CANCELLED",
        "REJECTED",
        "NO_SHOW",
        "LATE_CANCELLED",
        "SICKNESS",
    }:

        raise ValueError(
            "Это занятие уже нельзя отменить."
        )

    was_charged = bool(
        lesson["charged"]
    )

    refunded = False

    if (
        refund
        and was_charged
        and lesson["package_id"]
    ):

        refunded = (
            database.refund_lesson_balance(
                lesson_id, lesson["package_id"]
            )
        )

    conn = database.connect()

    if refund:

        payment_status = (
            "FREE"
            if lesson["payment_status"] == "FREE"
            else "REFUNDED"
        )

        charged = 0
        package_id = None

    else:

        payment_status = lesson["payment_status"]
        charged = lesson["charged"]
        package_id = lesson["package_id"]

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',
            attendance_status = 'CANCELLED',
            payment_status = ?,
            charged = ?,
            package_id = ?,
            cancelled_at = ?,
            cancellation_reason = ?,
            homework_required = 0,
            updated_at = ?

        WHERE id = ?
    """, (
        payment_status,
        charged,
        package_id,
        database.now_iso(),
        reason,
        database.now_iso(),
        lesson_id,
    ))

    conn.commit()
    conn.close()

    return {
        "cancelled": True,
        "refunded": refunded,
        "was_charged": was_charged,
        "regular_schedule_id": lesson["regular_schedule_id"],
    }


# ============================================================
# ALL UPCOMING LESSONS
# ============================================================

async def show_admin_lessons(
    query
):

    lessons = get_upcoming_admin_lessons(
        limit=100
    )

    if not lessons:

        await query.edit_message_text(
            "📚 БЛИЖАЙШИЕ ЗАНЯТИЯ\n\n"
            "Занятий пока нет.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Админка",
                        callback_data="admin_main",
                    )
                ]
            ]),
        )

        return

    keyboard = []

    current_date = None

    for lesson in lessons:

        start_dt = (
            datetime.fromisoformat(
                lesson["start_time"]
            )
        )

        date_text = (
            start_dt.strftime(
                "%d.%m"
            )
        )

        time_text = (
            start_dt.strftime(
                "%H:%M"
            )
        )

        if (
            lesson[
                "regular_schedule_id"
            ]
        ):

            icon = "🔁"

        else:

            icon = "📚"

        status_icon = {

            "PENDING":
                "🟡",

            "CONFIRMED":
                "🟢",

            "IN_PROGRESS":
                "▶️",

        }.get(
            lesson[
                "lesson_status"
            ],
            ""
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{status_icon}{icon} "
                    f"{date_text} "
                    f"{time_text} • "
                    f"{lesson['name']}"
                ),

                callback_data=(
                    f"admin_lesson_view|"
                    f"{lesson['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "📚 БЛИЖАЙШИЕ ЗАНЯТИЯ\n\n"
        "🔁 — постоянное занятие",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

# ============================================================
# TODAY
# ============================================================

def get_today_lessons():

    conn = database.connect()

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

            AND l.lesson_status NOT IN (
                'REJECTED'
            )

        ORDER BY l.start_time
    """, (
        date.today().isoformat(),
    )).fetchall()

    conn.close()

    return rows


async def show_today(query):

    lessons = get_today_lessons()

    if not lessons:

        await query.edit_message_text(
            "📅 СЕГОДНЯ\n\n"
            "Занятий нет.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Админка",
                        callback_data="admin_main",
                    )
                ]
            ]),
        )

        return

    keyboard = []

    for lesson in lessons:

        status = LESSON_STATUS_NAMES.get(
            lesson["lesson_status"],
            lesson["lesson_status"],
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{format_time(lesson['start_time'])} "
                    f"• {lesson['name']} "
                    f"• {status}"
                ),

                callback_data=(
                    f"admin_lesson_view|"
                    f"{lesson['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "📅 ЗАНЯТИЯ СЕГОДНЯ",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# LESSON CARD
# ============================================================

async def show_lesson(
    query,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        await query.answer(
            "Занятие не найдено.",
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    status = LESSON_STATUS_NAMES.get(
        lesson["lesson_status"],
        lesson["lesson_status"],
    )

    payment = PAYMENT_NAMES.get(
        lesson["payment_status"],
        lesson["payment_status"],
    )

    text = (
        "📚 ЗАНЯТИЕ\n\n"

        f"👤 {user['name']}\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n"

        f"⏱ "
        f"{lesson['duration_minutes']} минут\n"

        f"📚 "
        f"{subject_name(lesson['subject'])}\n\n"

        f"Статус: {status}\n"

        f"Оплата: {payment}"
    )

    if lesson["actual_duration_minutes"]:

        text += (
            "\n\n"
            f"⏱ Фактически: "
            f"{lesson['actual_duration_minutes']} минут"
        )

    notes = database.get_lesson_notes(
        lesson_id
    )

    if notes:

        text += (
            "\n\n💬 МАТЕРИАЛЫ ОТ УЧЕНИКА"
        )

        for index, note in enumerate(
            notes,
            start=1,
        ):

            text += "\n"

            if note["text"]:

                preview = note["text"]

                if len(preview) > 180:

                    preview = (
                        preview[:177]
                        + "..."
                    )

                text += (
                    f"{index}. {preview}"
                )

            elif note["photo_file_id"]:

                text += (
                    f"{index}. 📷 Фото/материал"
                )

            if (
                note["photo_file_id"]
                and note["text"]
            ):

                text += " 📷"

    keyboard = []

    if lesson["lesson_status"] in {
        "PENDING",
        "CONFIRMED",
    }:

        keyboard.append([
            InlineKeyboardButton(
                "❌ Отменить занятие",
                callback_data=(
                    f"admin_cancel_lesson|"
                    f"{lesson_id}"
                ),
            )
        ])

    if (
        lesson["lesson_status"]
        == "CONFIRMED"
    ):

        if (
            lesson["payment_status"]
            == "AWAITING_PAYMENT"
        ):

            keyboard.append([
                InlineKeyboardButton(
                    "💳 Подтвердить оплату",
                    callback_data=(
                        f"admin_lesson_paid|"
                        f"{lesson_id}"
                    ),
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔗 Отправить ссылку на занятие",
                callback_data=(
                    f"admin_send_lesson_link|{lesson_id}"
                ),
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "▶️ Начать без ссылки",
                callback_data=(
                    f"admin_lesson_start|"
                    f"{lesson_id}"
                ),
            )
        ])

    elif (
        lesson["lesson_status"]
        == "IN_PROGRESS"
    ):

        keyboard.append([
            InlineKeyboardButton(
                "⏹ Завершить занятие",
                callback_data=(
                    f"admin_lesson_finish|"
                    f"{lesson_id}"
                ),
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "👻 Ученик не пришёл",
                callback_data=(
                    f"admin_lesson_noshow|"
                    f"{lesson_id}"
                ),
            )
        ])

    elif (
        lesson["lesson_status"]
        == "COMPLETED"
    ):

        if (
            lesson["homework_required"]
            and not lesson["homework_assigned"]
            and not lesson["homework_skipped"]
        ):

            keyboard.append([
                InlineKeyboardButton(
                    "📝 Задать ДЗ",
                    callback_data=(
                        f"admin_homework|"
                        f"{lesson_id}"
                    ),
                )
            ])

            keyboard.append([
                InlineKeyboardButton(
                    "⏭ Без ДЗ",
                    callback_data=(
                        f"admin_homework_skip|"
                        f"{lesson_id}"
                    ),
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Сегодня",
            callback_data="admin_today",
        )
    ])

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# START LESSON
# ============================================================

async def start_lesson(
    query,
    context,
    lesson_id,
):

    try:

        database.start_lesson(
            lesson_id
        )

    except Exception as error:

        await query.answer(
            str(error),
            show_alert=True,
        )

        return

    lesson = database.get_lesson(
        lesson_id
    )

    user = database.get_user(
        lesson["user_id"]
    )

    if user["telegram_id"]:

        try:

            await context.bot.send_message(
                chat_id=user["telegram_id"],

                text=(
                    "▶️ ЗАНЯТИЕ НАЧАЛОСЬ\n\n"

                    "Фактическое время "
                    "занятия начало учитываться."
                ),
            )

        except Exception:

            pass

    await show_lesson(
        query,
        lesson_id,
    )


# ============================================================
# FINISH LESSON
# ============================================================

async def finish_lesson(
    query,
    context,
    lesson_id,
):

    try:

        result = (
            database.finish_lesson(
                lesson_id
            )
        )

    except Exception as error:

        await query.answer(
            str(error),
            show_alert=True,
        )

        return

    lesson = database.get_lesson(
        lesson_id
    )

    user = database.get_user(
        lesson["user_id"]
    )

    text = (
        "✅ ЗАНЯТИЕ ЗАВЕРШЕНО\n\n"

        f"👤 {user['name']}\n"

        f"🎟 Оплачено времени: "
        f"{result['scheduled_minutes']} минут\n"

        f"⏱ Фактически: "
        f"{result['actual_minutes']} минут\n"

        f"➕ Переработано: "
        f"{result['extra_minutes']} минут\n"

        f"⏳ Недоработано: "
        f"{result['underworked_minutes']} минут\n"

        f"🧮 Копилка недоработанного времени: "
        f"{result['underworked_minutes_balance']} минут"
    )

    if result[
        "bonus_lessons_awarded"
    ]:

        text += (
            "\n\n🎁 Начислено занятий в счёт "
            "накопленного недоработанного времени: "
            f"{result['bonus_lessons_awarded']}"
        )

    if user["telegram_id"]:

        student_text = (
            "✅ ЗАНЯТИЕ ЗАВЕРШЕНО\n\n"

            f"🎟 Оплачено времени: "
            f"{result['scheduled_minutes']} минут\n"

            f"⏱ Фактически прошло: "
            f"{result['actual_minutes']} минут"
        )

        student_text += (
            "\n"
            f"🧮 Недоработанное время в копилке: "
            f"{result['underworked_minutes_balance']} минут"
        )

        if result[
            "bonus_lessons_awarded"
        ]:

            student_text += (
                "\n\n🎁 Вам начислено "
                f"{result['bonus_lessons_awarded']} "
                "занятие в счёт накопленного "
                "недоработанного времени."
            )

        try:

            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=student_text,
            )

        except Exception:

            pass

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "📝 Задать ДЗ",
                    callback_data=(
                        f"admin_homework|"
                        f"{lesson_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⏭ Без ДЗ",
                    callback_data=(
                        f"admin_homework_skip|"
                        f"{lesson_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "📅 Сегодня",
                    callback_data="admin_today",
                )
            ],
        ]),
    )


# ============================================================
# NO SHOW
# ============================================================

async def no_show(
    query,
    context,
    lesson_id,
):

    database.mark_no_show(
        lesson_id
    )

    lesson = database.get_lesson(
        lesson_id
    )

    user = database.get_user(
        lesson["user_id"]
    )

    if user["telegram_id"]:

        try:

            await context.bot.send_message(

                chat_id=user["telegram_id"],

                text=(
                    "⚠️ Занятие отмечено "
                    "как пропущенное."
                ),
            )

        except Exception:

            pass

    await query.edit_message_text(
        "👻 Ученик отмечен как не пришедший.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📅 Сегодня",
                    callback_data="admin_today",
                )
            ]
        ]),
    )


# ============================================================
# CONFIRM MANUAL PAYMENT
# ============================================================

async def confirm_lesson_payment(
    query,
    context,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    try:

        database.confirm_manual_lesson_payment(
            lesson_id
        )

    except Exception as error:

        await query.answer(
            str(error),
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    if user["telegram_id"]:

        try:

            await context.bot.send_message(

                chat_id=user["telegram_id"],

                text=(
                    "✅ Оплата занятия подтверждена.\n\n"

                    f"📅 "
                    f"{format_datetime(lesson['start_time'])}"
                ),
            )

        except Exception:

            pass

    await show_lesson(
        query,
        lesson_id,
    )


# ============================================================
# HOMEWORK SKIP
# ============================================================

async def skip_homework(
    query,
    lesson_id,
):

    database.skip_homework_for_lesson(
        lesson_id
    )

    await query.edit_message_text(
        "✅ Занятие отмечено без домашнего задания.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📅 Сегодня",
                    callback_data="admin_today",
                )
            ]
        ]),
    )


# ============================================================
# STUDENTS
# ============================================================

async def show_students(
    query,
    grade_filter=None,
):
    if grade_filter is None:
        conn=database.connect()
        try:
            rows=conn.execute(
                "SELECT grade, COUNT(*) total "
                "FROM users "
                "WHERE active=1 "
                "GROUP BY grade "
                "ORDER BY grade"
            ).fetchall()

            blocked=conn.execute(
                "SELECT COUNT(*) FROM users WHERE active=0"
            ).fetchone()[0]
        finally:
            conn.close()

        active=sum(int(r['total']) for r in rows)
        keyboard=[]
        try:
            pinned=ux_service.pinned_students(query.from_user.id,5)
            recent=ux_service.recent_students(query.from_user.id,5)
            if pinned:
                keyboard.append([InlineKeyboardButton('⭐ ЗАКРЕПЛЁННЫЕ',callback_data='ux_noop')])
                for u in pinned: keyboard.append([InlineKeyboardButton(f"⭐ {u['name']} • {u['grade']} кл.",callback_data=f"student_view|{u['id']}")])
            if recent:
                keyboard.append([InlineKeyboardButton('🕘 НЕДАВНИЕ',callback_data='ux_noop')])
                for u in recent: keyboard.append([InlineKeyboardButton(f"🕘 {u['name']} • {u['grade']} кл.",callback_data=f"student_view|{u['id']}")])
        except Exception: pass
        for r in rows:
            keyboard.append([
                InlineKeyboardButton(
                    f"🎓 {r['grade']} класс • {r['total']}",
                    callback_data=f"admin_students_grade|{r['grade']}"
                )
            ])
        keyboard.extend([[InlineKeyboardButton('🔎 Найти ученика',callback_data='crm_search')],[InlineKeyboardButton(f'🚫 Заблокированные • {blocked}',callback_data='mh_blocked_students')],[InlineKeyboardButton('⬅️ Админка',callback_data='admin_main'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await query.edit_message_text(
            f"👥 УЧЕНИКИ\n\n"
            f"Учеников: {active}\n\n"
            f"Выберите класс:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    users=database.get_users_by_grade(
        grade_filter,
        active_only=True,
    )

    keyboard=[
        [
            InlineKeyboardButton(
                f"👤 {u['name']}",
                callback_data=f"admin_student|{u['id']}"
            )
        ]
        for u in users
    ]
    keyboard.extend([[InlineKeyboardButton('⬅️ К классам',callback_data='admin_students'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
    await query.edit_message_text(f"🎓 {grade_filter} КЛАСС • {len(users)} УЧЕНИКОВ",reply_markup=InlineKeyboardMarkup(keyboard))


async def show_student(
    query,
    user_id,
):

    user = database.get_user(
        user_id
    )

    if user is None:
        return

    programs = (
        database.get_student_programs(
            user_id,
            active_only=False,
            approved_only=False,
        )
    )

    text = (
        "👤 КАРТОЧКА УЧЕНИКА\n\n"

        f"Имя: {user['name']}\n"
        f"🎓 {user['grade']} класс\n"

        f"Telegram: "
        f"@{user['telegram_username'] or '—'}\n"
        f"Статус: {'✅ активен' if user['active'] else '🚫 заблокирован'}\n"

        f"🖥 Доска: "
        f"{'✅ сохранена' if user['board_url'] else '❌ не задана'}\n\n"

        "📚 НАПРАВЛЕНИЯ\n"
    )

    active_programs = [
        p
        for p in programs
        if p["active"]
    ]

    if not programs:

        text += (
            "\nНаправления пока не добавлены.\n"
        )

    else:

        for index, program in enumerate(
            programs,
            start=1,
        ):

            try:

                rate_info = (
                    database.get_program_rate_info(
                        program["id"]
                    )
                )

                rate_text = (
                    f"{rate_info['effective_rate']} ₽/час"
                )

                source_text = (
                    "👤 Индивидуальная"
                    if rate_info["source"] == "CUSTOM"
                    else "🌐 Общая"
                )

            except Exception:

                rate_text = "—"
                source_text = ""

            primary_icon = (
                "⭐️ "
                if program["is_primary"]
                else ""
            )

            status = (
                program_status_name(
                    program["approval_status"]
                )
            )

            text += (
                f"\n{index}. {primary_icon}"
                f"{program_title(program['study_goal'], program['subject'])}\n"
                f"   💰 {rate_text}"
            )

            if source_text:

                text += (
                    f" • {source_text}"
                )

            text += (
                f"\n   {status}\n"
            )

    try:

        stats = (
            database.get_learning_statistics(
                user_id
            )
        )

        total = stats["total"]

        text += (
            "\n📊 ОБЩАЯ СТАТИСТИКА\n"
            f"✅ Проведено: {total['completed_lessons']}\n"
            f"🎟 Оплачено: {total['paid_minutes']} мин\n"
            f"⏱ Фактически: {total['actual_minutes']} мин\n"
            f"➕ Переработка: {total['extra_minutes']} мин\n"
        )

        if total[
            "homework_accuracy_percent"
        ] is not None:

            text += (
                f"📝 ДЗ: "
                f"{total['homework_correct_tasks']} / "
                f"{total['homework_total_tasks']} "
                f"({total['homework_accuracy_percent']}%)\n"
            )

    except Exception:

        pass

    keyboard = []

    for program in active_programs:

        icon = (
            "⭐️"
            if program["is_primary"]
            else "📚"
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{icon} "
                    f"{program_title(program['study_goal'], program['subject'])}"
                ),
                callback_data=(
                    f"admin_program|{program['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            (
                "✏️ Изменить ссылку на доску"
                if user["board_url"]
                else "🖥 Добавить ссылку на доску"
            ),
            callback_data=(
                f"admin_board_set|{user_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Добавить направление",
            callback_data=(
                f"admin_program_add|{user_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "💬 Написать",
            callback_data=f"mh_write|{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "💜 Спросить Аделию об ученике",
            callback_data=f"mh_student_ask|{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "📌 Добавить задачу",
            callback_data=f"task_add_user|{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🎟 Баланс минут",
            callback_data=f"min_balance|{user_id}",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⏱ Основное время занятий",
            callback_data=f"min_duration_user|{user_id}",
        )
    ])

    keyboard.extend([

        [
            InlineKeyboardButton(
                "➕ Записать ученика",
                callback_data=(
                    f"admin_manual_for|{user_id}"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data=(
                    f"admin_student_stats|{user_id}"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "🚫 Заблокировать ученика" if user["active"] else "✅ Разблокировать ученика",
                callback_data=(
                    f"admin_student_block_warn|{user_id}" if user["active"]
                    else f"admin_student_unblock|{user_id}"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "🗑 Полностью удалить ученика",
                callback_data=(
                    f"admin_student_delete_warn|{user_id}"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Ученики",
                callback_data="admin_students",
            )
        ],
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# STUDENT PROGRAMS
# ============================================================

async def show_program(
    query,
    program_id,
):

    program = (
        database.get_student_program(
            program_id
        )
    )

    if program is None:

        await query.answer(
            "Направление не найдено.",
            show_alert=True,
        )

        return

    rate_info = (
        database.get_program_rate_info(
            program_id
        )
    )

    balance = (
        database.get_program_balance_breakdown(
            program_id
        )
    )

    source_text = (
        "👤 Индивидуальная"
        if rate_info["source"] == "CUSTOM"
        else "🌐 Общая"
    )

    text = (
        "📚 НАПРАВЛЕНИЕ УЧЕНИКА\n\n"

        f"👤 {program['name']}\n"
        f"🎓 {program['grade']} класс\n\n"

        f"📚 "
        f"{program_title(program['study_goal'], program['subject'])}\n"

        f"Статус: "
        f"{program_status_name(program['approval_status'])}\n"

        f"{'⭐️ Основное направление' if program['is_primary'] else ''}\n\n"

        f"💰 Текущая ставка: "
        f"{rate_info['effective_rate']} ₽/час\n"

        f"{source_text}\n"

        f"🌐 Общая ставка: "
        f"{rate_info['common_rate']} ₽/час\n\n"

        f"🎟 Баланс: "
        f"{balance['total']} занятий\n"

        f"• оплаченных: "
        f"{balance['paid']}\n"

        f"• бонусных: "
        f"{balance['bonus']}"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "💰 Изменить цену",
                callback_data=(
                    f"admin_program_price|{program_id}"
                ),
            )
        ],
    ]

    if rate_info["source"] == "CUSTOM":

        keyboard.append([
            InlineKeyboardButton(
                "♻️ Вернуть общую ставку",
                callback_data=(
                    f"admin_program_price_reset|{program_id}"
                ),
            )
        ])

    if not program["is_primary"]:

        keyboard.append([
            InlineKeyboardButton(
                "⭐️ Сделать основным",
                callback_data=(
                    f"admin_program_primary|{program_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Дополнительное ДЗ",
            callback_data=(
                f"admin_extra_hw|{program_id}"
            ),
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "📊 Статистика направления",
            callback_data=(
                f"admin_program_stats|{program_id}"
            ),
        )
    ])

    if len(
        database.get_student_programs(
            program["user_id"],
            active_only=True,
        )
    ) > 1:

        keyboard.append([
            InlineKeyboardButton(
                "🚫 Отключить направление",
                callback_data=(
                    f"admin_program_disable_warn|{program_id}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Карточка ученика",
            callback_data=(
                f"admin_student|{program['user_id']}"
            ),
        )
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def program_add_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        return ConversationHandler.END

    await query.answer()

    user_id = int(
        query.data.split("|")[1]
    )

    context.user_data[
        "program_user_id"
    ] = user_id

    await query.edit_message_text(
        "➕ ДОБАВИТЬ НАПРАВЛЕНИЕ\n\n"
        "Выберите предмет:",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "⚛️ Физика",
                    callback_data=(
                        "admin_program_subject|PHYSICS"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "🧪 Химия",
                    callback_data=(
                        "admin_program_subject|CHEMISTRY"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Отмена",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ],
        ]),
    )

    return PROGRAM_SUBJECT


async def program_subject_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    subject = (
        query.data.split("|")[1]
    )

    context.user_data[
        "program_subject"
    ] = subject

    user_id = (
        context.user_data[
            "program_user_id"
        ]
    )

    user = database.get_user(
        user_id
    )

    if user is None:

        await query.edit_message_text(
            "❌ Ученик не найден."
        )

        return ConversationHandler.END

    grade = int(
        user["grade"]
    )

    keyboard = []

    # Школьная программа:
    # и физика, и химия до 11 класса.
    if grade <= 11:

        keyboard.append([
            InlineKeyboardButton(
                "📚 Повышение успеваемости",
                callback_data=(
                    "admin_program_goal|SCHOOL"
                ),
            )
        ])

    # ОГЭ:
    # 9 класс, физика и химия.
    if grade == 9:

        keyboard.append([
            InlineKeyboardButton(
                "🎯 ОГЭ",
                callback_data=(
                    "admin_program_goal|OGE"
                ),
            )
        ])

    # ЕГЭ:
    # только физика.
    if (
        subject == "PHYSICS"
        and grade >= 10
    ):

        keyboard.append([
            InlineKeyboardButton(
                "🎯 ЕГЭ",
                callback_data=(
                    "admin_program_goal|EGE"
                ),
            )
        ])

    # Олимпиада:
    # пока только физика.
    if subject == "PHYSICS":

        keyboard.append([
            InlineKeyboardButton(
                "🏆 Олимпиада",
                callback_data=(
                    "admin_program_goal|OLYMPIAD"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=(
                f"admin_program_add|{user_id}"
            ),
        )
    ])

    await query.edit_message_text(
        "Теперь выберите направление:",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return PROGRAM_GOAL


async def program_goal_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    goal = (
        query.data.split("|")[1]
    )

    context.user_data[
        "program_goal"
    ] = goal

    user_id = (
        context.user_data[
            "program_user_id"
        ]
    )

    subject = (
        context.user_data[
            "program_subject"
        ]
    )

    user = database.get_user(
        user_id
    )

    if user is None:

        await query.edit_message_text(
            "❌ Ученик не найден."
        )

        return ConversationHandler.END

    grade = int(
        user["grade"]
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
            goal == "EGE"
            and grade >= 10
            and subject == "PHYSICS"
        )
        or (
            goal == "OLYMPIAD"
            and subject == "PHYSICS"
        )
    )

    if not valid:

        await query.edit_message_text(
            "❌ Такое сочетание предмета, "
            "направления и класса недоступно.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Карточка ученика",
                        callback_data=(
                            f"admin_student|{user_id}"
                        ),
                    )
                ]
            ]),
        )

        return ConversationHandler.END

    try:

        program_id = (
            database.create_student_program(
                user_id=user_id,
                study_goal=goal,
                subject=subject,
                approval_status="APPROVED",
                created_by="ADMIN",
            )
        )

    except Exception as error:

        await query.edit_message_text(
            f"❌ {error}",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Карточка ученика",
                        callback_data=(
                            f"admin_student|{user_id}"
                        ),
                    )
                ]
            ]),
        )

        return ConversationHandler.END

    context.user_data[
        "program_new_id"
    ] = program_id

    rate_info = (
        database.get_program_rate_info(
            program_id
        )
    )

    await query.edit_message_text(
        "✅ НАПРАВЛЕНИЕ ДОБАВЛЕНО\n\n"

        f"📚 "
        f"{program_title(goal, subject)}\n"

        f"🌐 Общая ставка: "
        f"{rate_info['common_rate']} ₽/час\n\n"

        "Хотите сразу установить "
        "индивидуальную цену?",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "💰 Да, установить",
                    callback_data=(
                        f"admin_program_price|{program_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "✅ Оставить общую",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ],
        ]),
    )

    return ConversationHandler.END


async def program_price_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        return ConversationHandler.END

    await query.answer()

    program_id = int(
        query.data.split("|")[1]
    )

    program = (
        database.get_student_program(
            program_id
        )
    )

    if program is None:

        return ConversationHandler.END

    rate_info = (
        database.get_program_rate_info(
            program_id
        )
    )

    context.user_data[
        "program_price_id"
    ] = program_id

    await query.edit_message_text(
        "💰 ИНДИВИДУАЛЬНАЯ ЦЕНА\n\n"

        f"👤 {program['name']}\n"
        f"📚 "
        f"{program_title(program['study_goal'], program['subject'])}\n\n"

        f"Текущая: "
        f"{rate_info['effective_rate']} ₽/час\n"

        f"Общая: "
        f"{rate_info['common_rate']} ₽/час\n\n"

        "Введите новую цену за 60 минут.\n"
        "Например: 2200"
    )

    return PROGRAM_PRICE


async def program_price_value_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text.strip()
        )

        if value <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите положительное число.\n"
            "Например: 2200"
        )

        return PROGRAM_PRICE

    program_id = (
        context.user_data.get(
            "program_price_id"
        )
    )

    if program_id is None:

        await update.message.reply_text(
            "❌ Направление потеряно. "
            "Откройте карточку заново."
        )

        return ConversationHandler.END

    info = (
        database.set_program_custom_rate(
            program_id,
            value,
        )
    )

    program = (
        database.get_student_program(
            program_id
        )
    )

    context.user_data.pop(
        "program_price_id",
        None,
    )

    await update.message.reply_text(
        "✅ ЦЕНА ИЗМЕНЕНА\n\n"

        f"👤 {program['name']}\n"
        f"📚 "
        f"{program_title(program['study_goal'], program['subject'])}\n"

        f"💰 "
        f"{info['effective_rate']} ₽/час",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть направление",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ]
        ]),
    )

    return ConversationHandler.END


async def reset_program_price(
    query,
    program_id,
):

    info = (
        database.clear_program_custom_rate(
            program_id
        )
    )

    await query.edit_message_text(
        "♻️ Индивидуальная цена удалена.\n\n"

        f"Теперь используется общая ставка: "
        f"{info['effective_rate']} ₽/час",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 К направлению",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ]
        ]),
    )


async def make_program_primary(
    query,
    program_id,
):

    program = (
        database.get_student_program(
            program_id
        )
    )

    database.set_primary_student_program(
        program["user_id"],
        program_id,
    )

    await show_program(
        query,
        program_id,
    )


async def show_program_stats(
    query,
    program_id,
):

    now = datetime.now()

    stats = (
        database.get_program_monthly_statistics(
            program_id,
            now.year,
            now.month,
        )
    )

    program = (
        database.get_student_program(
            program_id
        )
    )

    hw = stats["homework"]

    text = (
        "📊 СТАТИСТИКА НАПРАВЛЕНИЯ\n\n"

        f"👤 {program['name']}\n"
        f"📚 "
        f"{program_title(program['study_goal'], program['subject'])}\n\n"

        f"📅 {now.strftime('%m.%Y')}\n\n"

        f"✅ Проведено: "
        f"{stats['completed_lessons']}\n"

        f"🎟 Оплачено: "
        f"{stats['paid_minutes']} мин\n"

        f"⏱ Фактически: "
        f"{stats['actual_minutes']} мин\n"

        f"➕ Переработка: "
        f"{stats['extra_minutes']} мин\n\n"

        f"🤒 Больничных: "
        f"{stats['sickness']}\n"

        f"👻 Неявок: "
        f"{stats['no_show']}\n"

        f"⚠️ Поздних отмен: "
        f"{stats['late_cancelled']}\n\n"

        f"📝 Проверено ДЗ: "
        f"{hw['checked_homeworks']}\n"
    )

    if hw["accuracy_percent"] is not None:

        text += (
            f"✅ Правильно: "
            f"{hw['correct_tasks']} из "
            f"{hw['total_tasks']}\n"

            f"📈 Результат: "
            f"{hw['accuracy_percent']}%"
        )

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Направление",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ]
        ]),
    )


async def disable_program_warning(
    query,
    program_id,
):

    program = (
        database.get_student_program(
            program_id
        )
    )

    await query.edit_message_text(
        "⚠️ ОТКЛЮЧИТЬ НАПРАВЛЕНИЕ?\n\n"

        f"👤 {program['name']}\n"
        f"📚 "
        f"{program_title(program['study_goal'], program['subject'])}\n\n"

        "Новые записи по этому направлению "
        "станут недоступны. История занятий "
        "и статистика сохранятся.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🚫 Да, отключить",
                    callback_data=(
                        f"admin_program_disable|{program_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Отмена",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ],
        ]),
    )


async def disable_program(
    query,
    program_id,
):

    program = (
        database.get_student_program(
            program_id
        )
    )

    database.disable_student_program(
        program_id
    )

    await query.edit_message_text(
        "✅ Направление отключено.\n\n"
        "История сохранена.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👤 Карточка ученика",
                    callback_data=(
                        f"admin_student|{program['user_id']}"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# STUDENT ACCESS / BLOCKING
# ============================================================

async def student_block_warning(query, user_id):
    user = database.get_user(user_id)
    if user is None:
        await query.answer("Ученица или ученик не найден.", show_alert=True)
        return
    await query.edit_message_text(
        "🚫 БЛОКИРОВКА УЧЕНИКА\n\n"
        f"{user['name']} потеряет доступ к TutorBot. Я сразу отправлю уведомление о блокировке.\n\n"
        "Учебные данные, занятия и история сохранятся — доступ можно вернуть в любой момент.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin_student_block_confirm|{user_id}")],
            [InlineKeyboardButton("⬅️ Отмена", callback_data=f"admin_student|{user_id}")],
        ]),
    )


async def student_block_confirm(query, context, user_id):
    user = database.get_user(user_id)
    if user is None:
        await query.answer("Ученик не найден.", show_alert=True)
        return
    database.set_user_active(user_id, False)
    delivered = False
    if user["telegram_id"]:
        try:
            await context.bot.send_message(
                chat_id=int(user["telegram_id"]),
                text=(
                    "⛔️ Доступ к TutorBot временно ограничен.\n\n"
                    "Я — Аделия. Преподаватель ограничил доступ к личному кабинету. "
                    "Учебные данные сохранены. Если это неожиданно, свяжись с преподавателем напрямую."
                ),
            )
            delivered = True
        except Exception as error:
            print("STUDENT BLOCK NOTIFY:", repr(error))
    await query.edit_message_text(
        "Готово 💜 Я заблокировала доступ ученику.\n\n"
        f"👤 {user['name']}\n"
        + ("🔔 Уведомление доставлено." if delivered else "🔕 Уведомление отправить не удалось, но блокировка уже действует."),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 Карточка ученика", callback_data=f"admin_student|{user_id}")]]),
    )


async def student_unblock(query, context, user_id):
    user = database.get_user(user_id)
    if user is None:
        await query.answer("Ученик не найден.", show_alert=True)
        return
    database.set_user_active(user_id, True)
    if user["telegram_id"]:
        try:
            await context.bot.send_message(
                chat_id=int(user["telegram_id"]),
                text="✅ Доступ к TutorBot восстановлен 💜\n\nЯ снова рядом — можно пользоваться расписанием, занятиями и другими разделами как обычно.",
            )
        except Exception as error:
            print("STUDENT UNBLOCK NOTIFY:", repr(error))
    await query.edit_message_text(
        f"Готово 💜 Я снова открыла доступ для {user['name']}.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 Карточка ученика", callback_data=f"admin_student|{user_id}")]]),
    )


# ============================================================
# PARENTS DIRECTORY
# ============================================================

async def show_parents(query):
    parents = database.get_all_parents(active_only=False)
    lines = ["👨‍👩‍👧 РОДИТЕЛИ", "", "Я собрала все родительские аккаунты в одном месте."]
    keyboard = []
    if parents:
        lines.extend(["", f"Всего: {len(parents)}"] )
        for parent in parents:
            icon = "👤" if parent["active"] else "🚫"
            keyboard.append([InlineKeyboardButton(
                f"{icon} {parent['name']} · учеников: {int(parent['students_count'] or 0)}",
                callback_data=f"admin_parent|{parent['id']}",
            )])
    else:
        lines.extend(["", "Пока ни один родитель не зарегистрирован."])
    keyboard.append([InlineKeyboardButton("⬅️ Админка", callback_data="admin_main")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(keyboard))


async def show_parent(query, parent_id):
    parent = database.get_parent(parent_id)
    if parent is None:
        await query.answer("Родитель не найден.", show_alert=True)
        return
    students = database.get_parent_students_admin(parent_id)
    username = f"@{parent['telegram_username']}" if parent['telegram_username'] else "—"
    lines = [
        "👨‍👩‍👧 КАРТОЧКА РОДИТЕЛЯ", "",
        f"Имя: {parent['name']}",
        f"Telegram: {username}",
        f"Телефон: {parent['phone'] or '—'}",
        f"Статус: {'✅ активен' if parent['active'] else '🚫 отключён'}",
        "", "Связанные ученики:",
    ]
    kb = []
    if students:
        for student in students:
            lines.append(f"• {student['name']} · {student['grade']} класс")
            kb.append([InlineKeyboardButton(f"👤 {student['name']}", callback_data=f"admin_student|{student['id']}")])
    else:
        lines.append("• нет привязанных учеников")
    kb.append([InlineKeyboardButton("⬅️ Родители", callback_data="admin_parents")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


# ============================================================
# PAYMENT METHODS ADMIN
# ============================================================

async def show_payment_methods(query):
    methods = database.get_payment_methods(active_only=False)
    lines = [
        "💳 СПОСОБЫ ОПЛАТЫ", "",
        "Здесь я храню реквизиты. При предложении оплаты ученику Вы сможете выбрать нужный способ.",
    ]
    kb = []
    if methods:
        lines.extend(["", f"Сохранено: {len(methods)}"] )
        for method in methods:
            status = "⭐" if method["is_default"] else ("✅" if method["active"] else "🚫")
            kb.append([InlineKeyboardButton(f"{status} {method['title']}", callback_data=f"admin_paymethod|{method['id']}")])
    else:
        lines.extend(["", "Пока способов оплаты нет."])
    kb.append([InlineKeyboardButton("➕ Добавить способ", callback_data="admin_paymethod_add")])
    kb.append([InlineKeyboardButton("⬅️ Админка", callback_data="admin_main")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def show_payment_method(query, method_id):
    method = database.get_payment_method(method_id)
    if method is None:
        await query.answer("Способ оплаты не найден.", show_alert=True)
        return
    text = (
        "💳 СПОСОБ ОПЛАТЫ\n\n"
        f"{method['title']}\n"
        f"Статус: {'✅ активен' if method['active'] else '🚫 выключен'}\n"
        f"Основной: {'⭐ да' if method['is_default'] else 'нет'}\n\n"
        f"{method['details']}"
    )
    kb = [
        [InlineKeyboardButton("⭐ Сделать основным", callback_data=f"admin_paymethod_default|{method_id}")],
        [InlineKeyboardButton("🚫 Выключить" if method["active"] else "✅ Включить", callback_data=f"admin_paymethod_toggle|{method_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"admin_paymethod_delete_warn|{method_id}")],
        [InlineKeyboardButton("⬅️ Способы оплаты", callback_data="admin_payment_methods")],
    ]
    await query.edit_message_text(text[:3900], reply_markup=InlineKeyboardMarkup(kb))


async def payment_method_add_entry(update, context):
    query = update.callback_query
    if not is_admin(update):
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text(
        "💳 Новый способ оплаты\n\nКак он будет называться?\nНапример: «СБП • Альфа-Банк» или «Карта Т-Банк»."
    )
    return PAYMENT_METHOD_TITLE


async def payment_method_title_handler(update, context):
    title = (update.message.text or "").strip()
    if not title:
        await update.message.reply_text("Название не должно быть пустым.")
        return PAYMENT_METHOD_TITLE
    context.user_data["new_payment_method_title"] = title[:120]
    await update.message.reply_text(
        "Теперь пришлите реквизиты одним сообщением. Можно использовать несколько строк.\n\n"
        "Например: банк, номер телефона/карты, получатель и короткая инструкция."
    )
    return PAYMENT_METHOD_DETAILS


async def payment_method_details_handler(update, context):
    details = (update.message.text or "").strip()
    title = context.user_data.pop("new_payment_method_title", None)
    if not title:
        return ConversationHandler.END
    if not details:
        context.user_data["new_payment_method_title"] = title
        await update.message.reply_text("Реквизиты не должны быть пустыми.")
        return PAYMENT_METHOD_DETAILS
    method_id = database.add_payment_method(title, details)
    await update.message.reply_text(
        f"Готово 💜 Я сохранила способ оплаты «{title}».",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Открыть способ", callback_data=f"admin_paymethod|{method_id}")]]),
    )
    return ConversationHandler.END


async def payment_method_delete_warning(query, method_id):
    method = database.get_payment_method(method_id)
    if method is None:
        return
    await query.edit_message_text(
        f"Удалить способ оплаты «{method['title']}»?\n\nСтарые предложения оплаты останутся в истории, но этот способ больше нельзя будет выбрать.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Да, удалить", callback_data=f"admin_paymethod_delete|{method_id}")],
            [InlineKeyboardButton("⬅️ Отмена", callback_data=f"admin_paymethod|{method_id}")],
        ]),
    )


# ============================================================
# FULL STUDENT DELETE
# ============================================================

async def student_delete_warning(
    query,
    user_id,
):

    preview = (
        database.get_student_delete_preview(
            user_id
        )
    )

    user = preview["user"]
    counts = preview["counts"]

    await query.edit_message_text(
        "⚠️ ПОЛНОЕ УДАЛЕНИЕ УЧЕНИКА\n\n"

        f"👤 {user['name']}\n\n"

        "Будут удалены данные ученика:\n"

        f"• направлений: "
        f"{counts.get('student_programs', 0)}\n"

        f"• занятий: "
        f"{counts.get('lessons', 0)}\n"

        f"• домашних заданий: "
        f"{counts.get('homework', 0)}\n"

        f"• постоянных расписаний: "
        f"{counts.get('regular_schedules', 0)}\n"

        f"• оплат: "
        f"{counts.get('payments', 0)}\n\n"

        "Это действие необратимо.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "Продолжить",
                    callback_data=(
                        f"admin_student_delete_confirm|{user_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Отмена",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ],
        ]),
    )


async def student_delete_confirm(
    query,
    user_id,
):

    user = (
        database.get_user(
            user_id
        )
    )

    if user is None:
        return

    await query.edit_message_text(
        "❗ ПОСЛЕДНЕЕ ПОДТВЕРЖДЕНИЕ\n\n"

        f"Полностью удалить "
        f"{user['name']}?\n\n"

        "Восстановить профиль после этого "
        "через бота будет невозможно.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🗑 Да, удалить полностью",
                    callback_data=(
                        f"admin_student_delete_final|{user_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Нет",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ],
        ]),
    )


async def student_delete_final(
    query,
    user_id,
):

    preview = (
        database.delete_student_completely(
            user_id
        )
    )

    await query.edit_message_text(
        "✅ УЧЕНИК ПОЛНОСТЬЮ УДАЛЁН\n\n"

        f"👤 "
        f"{preview['user']['name']}\n\n"

        "Профиль и связанные учебные данные "
        "удалены из базы.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👥 К ученикам",
                    callback_data=(
                        "admin_students"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# PRICES
# ============================================================

async def show_prices(
    query,
):

    rows = database.get_all_price_settings()

    keyboard = []

    for row in rows:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"💰 {row['title']} — "
                    f"{row['hourly_rate']} ₽/ч"
                ),
                callback_data=(
                    f"admin_price_default|{row['rate_key']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "💰 ОБЩИЕ СТАВКИ\n\n"
        "Эти цены используются для всех "
        "учеников, у которых не задана "
        "индивидуальная ставка.\n\n"
        "Нажмите на тариф, чтобы изменить цену.",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def show_default_price(
    query,
    rate_key,
):

    setting = database.get_price_setting(
        rate_key
    )

    if setting is None:

        await query.answer(
            "Тариф не найден.",
            show_alert=True,
        )
        return

    await query.edit_message_text(
        "💰 ОБЩАЯ СТАВКА\n\n"

        f"{setting['title']}\n"
        f"Текущая цена: "
        f"{setting['hourly_rate']} ₽/час",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✏️ Изменить",
                    callback_data=(
                        f"admin_price_default_edit|{rate_key}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Общие ставки",
                    callback_data="admin_prices",
                )
            ],
        ]),
    )


async def default_price_edit_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):
        return ConversationHandler.END

    await query.answer()

    rate_key = (
        query.data.split("|", 1)[1]
    )

    setting = database.get_price_setting(
        rate_key
    )

    if setting is None:

        await query.edit_message_text(
            "❌ Тариф не найден."
        )
        return ConversationHandler.END

    context.user_data[
        "price_rate_key"
    ] = rate_key

    await query.edit_message_text(
        "✏️ ИЗМЕНИТЬ ОБЩУЮ СТАВКУ\n\n"

        f"{setting['title']}\n"
        f"Сейчас: "
        f"{setting['hourly_rate']} ₽/час\n\n"

        "Введите новую цену за 60 минут.\n"
        "Например: 2200"
    )

    return PRICE_DEFAULT_VALUE


async def default_price_value_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text.strip()
        )

        if value <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите положительное число.\n"
            "Например: 2200"
        )
        return PRICE_DEFAULT_VALUE

    rate_key = context.user_data.get(
        "price_rate_key"
    )

    if not rate_key:

        await update.message.reply_text(
            "❌ Тариф потерян. "
            "Откройте раздел цен заново."
        )
        return ConversationHandler.END

    database.set_default_rate(
        rate_key,
        value,
    )

    setting = database.get_price_setting(
        rate_key
    )

    context.user_data.pop(
        "price_rate_key",
        None,
    )

    await update.message.reply_text(
        "✅ ОБЩАЯ СТАВКА ИЗМЕНЕНА\n\n"

        f"{setting['title']}\n"
        f"Новая цена: "
        f"{setting['hourly_rate']} ₽/час\n\n"

        "У учеников с индивидуальной "
        "ставкой цена не изменится.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💰 Общие ставки",
                    callback_data="admin_prices",
                )
            ]
        ]),
    )

    return ConversationHandler.END


async def student_price_edit_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):
        return ConversationHandler.END

    await query.answer()

    user_id = int(
        query.data.split("|")[1]
    )

    user = database.get_user(
        user_id
    )

    if user is None:

        await query.edit_message_text(
            "❌ Ученик не найден."
        )
        return ConversationHandler.END

    rate_info = database.get_student_rate_info(
        user_id,
        user["study_goal"],
        user["main_subject"],
    )

    context.user_data[
        "price_student_id"
    ] = user_id

    await query.edit_message_text(
        "💰 ИНДИВИДУАЛЬНАЯ СТАВКА\n\n"

        f"👤 {user['name']}\n"
        f"🎓 {user['grade']} класс\n"
        f"📚 {subject_name(user['main_subject'])}\n\n"

        f"Текущая ставка: "
        f"{rate_info['effective_rate']} ₽/час\n"

        f"Общая ставка: "
        f"{rate_info['common_rate']} ₽/час\n\n"

        "Введите индивидуальную цену "
        "за 60 минут.\n"
        "Например: 1900"
    )

    return PRICE_STUDENT_VALUE


async def student_price_value_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text.strip()
        )

        if value <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите положительное число.\n"
            "Например: 1900"
        )
        return PRICE_STUDENT_VALUE

    user_id = context.user_data.get(
        "price_student_id"
    )

    user = database.get_user(
        user_id
    ) if user_id else None

    if user is None:

        await update.message.reply_text(
            "❌ Ученик не найден."
        )
        return ConversationHandler.END

    database.set_custom_rate(
        user_id,
        user["study_goal"],
        user["main_subject"],
        value,
    )

    context.user_data.pop(
        "price_student_id",
        None,
    )

    await update.message.reply_text(
        "✅ ИНДИВИДУАЛЬНАЯ СТАВКА УСТАНОВЛЕНА\n\n"

        f"👤 {user['name']}\n"
        f"💰 {value} ₽/час\n\n"

        "Новая ставка применяется "
        "к новым покупкам и новым занятиям. "
        "Уже оплаченные пакеты не пересчитываются.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👤 Карточка ученика",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ]
        ]),
    )

    return ConversationHandler.END


async def reset_student_price(
    query,
    user_id,
):

    user = database.get_user(
        user_id
    )

    if user is None:
        return

    rate_info = database.clear_custom_rate(
        user_id,
        user["study_goal"],
        user["main_subject"],
    )

    await query.edit_message_text(
        "♻️ ИНДИВИДУАЛЬНАЯ СТАВКА УДАЛЕНА\n\n"

        f"👤 {user['name']}\n"

        f"Теперь используется общая ставка: "
        f"{rate_info['effective_rate']} ₽/час",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👤 Карточка ученика",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# STUDENT STATISTICS
# ============================================================

async def show_student_stats(
    query,
    user_id,
):

    user = database.get_user(
        user_id
    )

    stats = (
        database.get_learning_statistics(
            user_id
        )
    )

    total = stats["total"]

    text = (
        "📊 СТАТИСТИКА УЧЕНИКА\n\n"

        f"👤 {user['name']}\n\n"

        f"✅ Проведено занятий: "
        f"{total['completed_lessons']}\n"

        f"👻 Неявок: "
        f"{total['no_show']}\n"

        f"⚠️ Поздних отмен: "
        f"{total['late_cancelled']}\n"

        f"🤒 Больничных: "
        f"{total['sickness']}\n\n"

        f"🎟 Оплачено минут: "
        f"{total['paid_minutes']}\n"

        f"⏱ Фактически прошло: "
        f"{total['actual_minutes']}\n"

        f"➕ Переработка: "
        f"{total['extra_minutes']} мин\n\n"

        f"📝 Проверено ДЗ: "
        f"{total['homework_checked']}\n"
    )

    if total[
        "homework_accuracy_percent"
    ] is not None:

        text += (
            f"✅ Правильно: "
            f"{total['homework_correct_tasks']} из "
            f"{total['homework_total_tasks']}\n"

            f"📈 Средний результат: "
            f"{total['homework_accuracy_percent']}%\n"
        )

    if stats["programs"]:

        text += (
            "\n📚 ПО НАПРАВЛЕНИЯМ\n"
        )

        for item in stats["programs"]:

            program = item["program"]

            text += (
                "\n"
                f"• "
                f"{program_title(program['study_goal'], program['subject'])}\n"
                f"  ✅ {item['completed_lessons']} занятий\n"
                f"  🎟 {item['paid_minutes']} мин оплачено\n"
                f"  ⏱ {item['actual_minutes']} мин фактически\n"
            )

            accuracy = item[
                "homework"
            ][
                "accuracy_percent"
            ]

            if accuracy is not None:

                text += (
                    f"  📝 ДЗ: {accuracy}%\n"
                )

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ Ученик",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# GENERAL STATISTICS
# ============================================================

async def show_statistics(query, period="all"):

    now = datetime.now()
    start = None
    end = None

    titles = {
        "all": "📊 ОБЩАЯ СТАТИСТИКА",
        "day": "📊 СТАТИСТИКА ЗА ДЕНЬ",
        "week": "📊 СТАТИСТИКА ЗА НЕДЕЛЮ",
        "month": "📊 СТАТИСТИКА ЗА МЕСЯЦ",
    }

    if period == "day":
        start = datetime.combine(now.date(), datetime.min.time())
        end = start + timedelta(days=1)
    elif period == "week":
        start = datetime.combine(now.date() - timedelta(days=now.weekday()), datetime.min.time())
        end = start + timedelta(days=7)
    elif period == "month":
        start = datetime(now.year, now.month, 1)
        end = datetime(now.year + (1 if now.month == 12 else 0), 1 if now.month == 12 else now.month + 1, 1)

    stats = database.get_admin_statistics(
        start.isoformat(timespec="seconds") if start else None,
        end.isoformat(timespec="seconds") if end else None,
    )
    finance = core_analytics.financial_stats(
        start.isoformat(timespec="seconds") if start else None,
        end.isoformat(timespec="seconds") if end else None,
    )

    text = (
        f"{titles.get(period, titles['all'])}\n\n"
        f"👥 Активных учеников: {stats['active_users']}\n\n"
        f"✅ Проведено занятий: {stats['completed']}\n"
        f"⏱ Фактического времени: {stats['actual_minutes']} минут\n\n"
        f"💰 Заработано по проведённым занятиям: {finance['earned']:,} ₽\n"
        f"💳 Получено оплатами: {finance['received']:,} ₽\n"
        f"📦 Предоплачено, но ещё не отработано: {finance['prepaid']:,} ₽".replace(",", " ")
    )

    if start and end:
        text += f"\n\n🗓 {start.strftime('%d.%m.%Y')} — {(end - timedelta(days=1)).strftime('%d.%m.%Y')}"

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌐 Всё время", callback_data="admin_statistics|all"),
                InlineKeyboardButton("☀️ День", callback_data="admin_statistics|day"),
            ],
            [
                InlineKeyboardButton("📅 Неделя", callback_data="admin_statistics|week"),
                InlineKeyboardButton("🗓 Месяц", callback_data="admin_statistics|month"),
            ],
            [InlineKeyboardButton("⬅️ Админка", callback_data="admin_main")],
        ]),
    )


async def show_admin_balance(query, user_id):
    user=database.get_user(user_id)
    if user is None: return
    balances=core_minute_balance.get_balance_by_rate(user_id)
    text=f"🎟 БАЛАНС В МИНУТАХ\n\n👤 {user['name']}\n\n"
    if not balances:
        text += "Баланс пуст.\n"
    else:
        for rate,item in balances.items():
            if rate==0:
                text += f"🎁 Бонусная копилка: {item['bonus']} мин\n"
            else:
                text += f"• {rate:,} ₽ / 60 мин: {item['paid']} мин\n".replace(',', ' ')
    await query.edit_message_text(text,reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Управление минутами",callback_data=f"min_balance|{user_id}")],
        [InlineKeyboardButton("⬅️ Ученик",callback_data=f"admin_student|{user_id}")],
    ]))


# ============================================================
# UNPAID LESSONS
# ============================================================

def get_unpaid_lessons():

    conn = database.connect()

    rows = conn.execute("""
        SELECT

            l.*,

            u.name,
            u.telegram_id

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            l.lesson_status = 'CONFIRMED'

            AND l.payment_status =
                'AWAITING_PAYMENT'

        ORDER BY
            l.start_time
    """).fetchall()

    conn.close()

    return rows


async def show_unpaid(query):

    rows = get_unpaid_lessons()

    if not rows:

        await query.edit_message_text(
            "💳 НЕОПЛАЧЕННЫЕ ЗАНЯТИЯ\n\n"
            "Все занятия оплачены.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Админка",
                        callback_data="admin_main",
                    )
                ]
            ]),
        )

        return

    keyboard = []

    for row in rows:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"💳 {row['name']} • "
                    f"{format_datetime(row['start_time'])}"
                ),

                callback_data=(
                    f"admin_lesson_view|"
                    f"{row['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "💳 НЕОПЛАЧЕННЫЕ ЗАНЯТИЯ",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


# ============================================================
# MANUAL LESSON — START
# ============================================================

async def manual_lesson_start(
    query,
    context,
):

    users = database.get_all_users()

    if not users:

        await query.edit_message_text(
            "❌ Нет учеников."
        )

        return (
            ConversationHandler.END
        )

    keyboard = []

    for user in users:

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{user['name']} • "
                    f"{user['grade']} кл."
                ),

                callback_data=(
                    f"admin_manual_student|"
                    f"{user['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "➕ ЗАПИСАТЬ УЧЕНИКА\n\n"
        "Выберите ученика:",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )

    return MANUAL_STUDENT


async def manual_for_student(
    query,
    context,
    user_id,
):

    context.user_data[
        "manual_user_id"
    ] = user_id

    user = database.get_user(
        user_id
    )

    context.user_data.pop("manual_date", None)
    context.user_data.pop("manual_time", None)
    context.user_data.pop("manual_duration", None)
    await query.edit_message_text(
        "➕ РУЧНАЯ ЗАПИСЬ\n\n"
        f"👤 {user['name']}\n\n"
        "Сначала выберите длительность. После этого покажу ближайшие свободные окна на 14 дней.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("60 мин", callback_data="admin_manual_duration|60"),
            InlineKeyboardButton("90 мин", callback_data="admin_manual_duration|90"),
        ],[
            InlineKeyboardButton("120 мин", callback_data="admin_manual_duration|120"),
            InlineKeyboardButton("⬅️ Ученики", callback_data="admin_manual_lesson"),
        ]])
    )
    return MANUAL_DURATION


async def manual_student_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    user_id = int(
        query.data.split("|")[1]
    )

    return await manual_for_student(
        query,
        context,
        user_id,
    )


async def manual_date_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = (
        update.message.text
        .strip()
    )

    try:

        parsed = (
            datetime.strptime(
                value,
                "%d.%m.%Y",
            )
            .date()
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Формат даты:\n"
            "25.08.2026"
        )

        return MANUAL_DATE

    context.user_data[
        "manual_date"
    ] = parsed.isoformat()

    await update.message.reply_text(
        "Введите время начала.\n\n"
        "Например:\n"
        "18:00"
    )

    return MANUAL_TIME


async def manual_time_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = (
        update.message.text
        .strip()
    )

    try:

        datetime.strptime(
            value,
            "%H:%M",
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Например:\n"
            "18:00"
        )

        return MANUAL_TIME

    context.user_data["manual_time"] = value
    duration=int(context.user_data.get("manual_duration",90))
    start_dt=datetime.fromisoformat(f"{context.user_data['manual_date']}T{value}:00")
    end_dt=start_dt+timedelta(minutes=duration)
    if database.is_slot_reserved(start_dt.isoformat(),end_dt.isoformat()):
        await update.message.reply_text(
            "⚠️ Это время пересекается с уже существующим занятием. Выберите другую дату/время.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📆 Выбрать дату",callback_data="admin_manual_dates")],[InlineKeyboardButton("🔄 Перенос / обмен",callback_data="ff_swap_admin")]])
        )
        return MANUAL_DATE
    await update.message.reply_text("✅ Интервал свободен. Выберите способ оплаты:",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎟 Списать абонемент",callback_data="admin_manual_payment|BALANCE")],[InlineKeyboardButton("💳 Не оплачено",callback_data="admin_manual_payment|AWAITING_PAYMENT")],[InlineKeyboardButton("🎁 Бесплатно",callback_data="admin_manual_payment|FREE")]]))
    return MANUAL_PAYMENT_MODE


async def _manual_payment_menu(query):
    await query.edit_message_text(
        "💳 Как оформить занятие?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 Списать абонемент", callback_data="admin_manual_payment|BALANCE")],
            [InlineKeyboardButton("💳 Не оплачено", callback_data="admin_manual_payment|AWAITING_PAYMENT")],
            [InlineKeyboardButton("🎁 Бесплатно", callback_data="admin_manual_payment|FREE")],
        ]),
    )
    return MANUAL_PAYMENT_MODE


def _manual_date_buttons():
    today=date.today(); last=(date(today.year+1,1,1)-timedelta(days=1)) if today.month==12 else (date(today.year,today.month+1,1)-timedelta(days=1))
    days=[]; d=today
    while d<=last:
        days.append(d); d+=timedelta(days=1)
    rows=[]
    for i in range(0,len(days),3):
        rows.append([InlineKeyboardButton(x.strftime('%d.%m'),callback_data=f'admin_manual_day|{x.isoformat()}') for x in days[i:i+3]])
    rows.append([InlineKeyboardButton('✍️ Ввести другую дату',callback_data='admin_manual_type_date')])
    rows.append([InlineKeyboardButton('⬅️ К ученику',callback_data=f"admin_manual_for|{{UID}}")])
    return rows


async def _manual_show_slots(query,context):
    import bot as tutor_bot
    duration=int(context.user_data['manual_duration'])
    uid=int(context.user_data['manual_user_id'])
    now=date.today(); found=[]
    for offset in range(14):
        day=now+timedelta(days=offset)
        try: slots=await __import__('asyncio').to_thread(tutor_bot.get_free_slots,day,duration,None)
        except Exception: slots=[]
        for dt in slots:
            found.append(dt)
    found=found[:18]
    rows=[]
    for i in range(0,len(found),2):
        row=[]
        for dt in found[i:i+2]:
            row.append(InlineKeyboardButton(dt.strftime('%d.%m • %H:%M'),callback_data=f'admin_manual_slot|{dt.isoformat()}'))
        rows.append(row)
    rows.append([InlineKeyboardButton('📆 Выбрать дату самостоятельно',callback_data='admin_manual_dates')])
    rows.append([InlineKeyboardButton('⬅️ К ученику',callback_data=f'admin_manual_for|{uid}')])
    text=f"📅 БЛИЖАЙШИЕ СВОБОДНЫЕ ОКНА\\n\\nДлительность: {duration} мин\\nПериод: ближайшие 14 дней."
    if not found:text+='\\n\\nСвободных окон по рабочему расписанию не найдено — выберите дату самостоятельно.'
    await query.edit_message_text(text,reply_markup=InlineKeyboardMarkup(rows))
    return MANUAL_DATE


async def manual_duration_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query=update.callback_query; await query.answer()
    context.user_data['manual_duration']=int(query.data.split('|')[1])
    return await _manual_show_slots(query,context)


async def manual_slot_selected(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); dt=datetime.fromisoformat(q.data.split('|',1)[1])
    context.user_data['manual_date']=dt.date().isoformat(); context.user_data['manual_time']=dt.strftime('%H:%M')
    return await _manual_payment_menu(q)


async def manual_dates_menu(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=int(context.user_data['manual_user_id'])
    rows=_manual_date_buttons(); rows[-1]=[InlineKeyboardButton('⬅️ К ученику',callback_data=f'admin_manual_for|{uid}')]
    await q.edit_message_text('📆 ВЫБЕРИТЕ ДАТУ\\n\\nДаты до конца текущего месяца:',reply_markup=InlineKeyboardMarkup(rows))
    return MANUAL_DATE


async def manual_day_selected(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); day=date.fromisoformat(q.data.split('|')[1]); duration=int(context.user_data['manual_duration'])
    import bot as tutor_bot
    try: slots=await __import__('asyncio').to_thread(tutor_bot.get_free_slots,day,duration,None)
    except Exception: slots=[]
    rows=[]
    for i in range(0,len(slots),3):
        rows.append([InlineKeyboardButton(dt.strftime('%H:%M'),callback_data=f'admin_manual_slot|{dt.isoformat()}') for dt in slots[i:i+3]])
    rows.append([InlineKeyboardButton('✍️ Указать своё время',callback_data=f'admin_manual_custom_time|{day.isoformat()}')])
    rows.append([InlineKeyboardButton('⬅️ Даты',callback_data='admin_manual_dates')])
    txt=f"📅 {day.strftime('%d.%m.%Y')}\\n\\n" + ('Выберите свободное время:' if slots else 'Свободных стандартных окон нет. Можно предложить своё время — бот проверит конфликт перед записью.')
    await q.edit_message_text(txt,reply_markup=InlineKeyboardMarkup(rows)); return MANUAL_DATE


async def manual_custom_time(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); context.user_data['manual_date']=q.data.split('|')[1]
    await q.edit_message_text('✍️ Введите желаемое время, например 18:30.\\n\\nПеред записью бот проверит, свободен ли этот интервал.'); return MANUAL_TIME


async def manual_type_date(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); await q.edit_message_text('Введите дату в формате 25.08.2026'); return MANUAL_DATE


async def manual_payment_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    payment_mode = (
        query.data.split("|")[1]
    )

    user_id = (
        context.user_data[
            "manual_user_id"
        ]
    )

    user = database.get_user(
        user_id
    )

    date_value = (
        context.user_data[
            "manual_date"
        ]
    )

    time_value = (
        context.user_data[
            "manual_time"
        ]
    )

    duration = (
        context.user_data[
            "manual_duration"
        ]
    )

    start_dt = datetime.fromisoformat(
        f"{date_value}T{time_value}:00"
    )

    end_dt = (
        start_dt
        + timedelta(
            minutes=duration
        )
    )

    rate = database.get_student_rate(
        user_id,
        user["study_goal"],
        user["main_subject"],
    )

    price = (
        database.calculate_lesson_price(
            rate,
            duration,
        )
    )

    try:

        lesson_id = (
            database.create_admin_lesson(

                user_id=user_id,

                study_goal=(
                    user["study_goal"]
                ),

                subject=(
                    user["main_subject"]
                ),

                start_time=(
                    start_dt.isoformat()
                ),

                end_time=(
                    end_dt.isoformat()
                ),

                duration_minutes=duration,

                hourly_rate=rate,

                price=price,

                payment_mode=payment_mode,
            )
        )

    except Exception as error:

        await query.edit_message_text(
            f"❌ {error}",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Админка",
                        callback_data="admin_main",
                    )
                ]
            ]),
        )

        return (
            ConversationHandler.END
        )

    lesson = database.get_lesson(
        lesson_id
    )

    if user["telegram_id"]:

        message = (
            "📅 ВАМ НАЗНАЧЕНО ЗАНЯТИЕ\n\n"

            f"📅 "
            f"{format_datetime(lesson['start_time'])}\n"

            f"📚 "
            f"{subject_name(lesson['subject'])}\n"

            f"⏱ "
            f"{duration} минут\n"
        )

        if (
            payment_mode
            == "AWAITING_PAYMENT"
        ):

            message += (
                "\n💳 Занятие пока не оплачено.\n"
                "Оплатить необходимо не позднее "
                "чем за 2 часа до начала."
            )

        elif payment_mode == "BALANCE":

            message += (
                "\n🎟 Занятие списано "
                "с абонемента."
            )

        elif payment_mode == "FREE":

            message += (
                "\n🎁 Занятие бесплатное."
            )

        try:

            reply_markup = None

            if (
                payment_mode
                == "AWAITING_PAYMENT"
            ):

                reply_markup = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "💳 Оплатить занятие",
                            callback_data=(
                                f"payment_lesson|{lesson_id}"
                            ),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📚 Мои занятия",
                            callback_data="lessons",
                        )
                    ],
                ])

            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=message,
                reply_markup=reply_markup,
            )

        except Exception as error:

            print(
                "MANUAL STUDENT NOTIFY:",
                repr(error),
            )

    for key in (
        "manual_user_id",
        "manual_date",
        "manual_time",
        "manual_duration",
    ):

        context.user_data.pop(
            key,
            None,
        )

    await query.edit_message_text(
        "✅ ЗАНЯТИЕ СОЗДАНО\n\n"

        f"👤 {user['name']}\n"

        f"📅 "
        f"{format_datetime(lesson['start_time'])}\n"

        f"⏱ {duration} минут\n"

        f"💰 {price} ₽",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "📚 Открыть занятие",
                    callback_data=(
                        f"admin_lesson_view|"
                        f"{lesson_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Админка",
                    callback_data="admin_main",
                )
            ],
        ]),
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# PROMOS
# ============================================================

async def show_promos(query):

    promos = database.get_all_promos()

    keyboard = []

    for promo in promos:

        icon = (
            "🟢"
            if promo["active"]
            else "⚫️"
        )

        keyboard.append([
            InlineKeyboardButton(
                (
                    f"{icon} "
                    f"{promo['code']} • "
                    f"{promo['discount_value']}"
                    f"{'%' if promo['discount_type'] == 'PERCENT' else ' ₽'}"
                ),

                callback_data=(
                    f"admin_promo|"
                    f"{promo['id']}"
                ),
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Создать промокод",
            callback_data="admin_promo_create",
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Админка",
            callback_data="admin_main",
        )
    ])

    await query.edit_message_text(
        "🎁 ПРОМОКОДЫ",

        reply_markup=InlineKeyboardMarkup(
            keyboard
        ),
    )


async def show_promo(
    query,
    promo_id,
):

    promo = database.get_promo(
        promo_id
    )

    if promo is None:
        return

    if (
        promo["discount_type"]
        == "PERCENT"
    ):

        discount = (
            f"{promo['discount_value']}%"
        )

    else:

        discount = (
            f"{promo['discount_value']} ₽"
        )

    status = (
        "🟢 Активен"
        if promo["active"]
        else "⚫️ Выключен"
    )

    await query.edit_message_text(
        "🎁 ПРОМОКОД\n\n"

        f"Код: {promo['code']}\n"

        f"Скидка: {discount}\n"

        f"Использовано: "
        f"{promo['uses_count']}\n"

        f"Максимум: "
        f"{promo['max_uses'] or 'без лимита'}\n"

        f"На ученика: "
        f"{promo['per_user_limit'] or 'без лимита'}\n"

        f"До: "
        f"{format_datetime(promo['expires_at'])}\n\n"

        f"{status}",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    (
                        "⏸ Выключить"
                        if promo["active"]
                        else "▶️ Включить"
                    ),

                    callback_data=(
                        f"admin_promo_toggle|"
                        f"{promo_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 Удалить",
                    callback_data=(
                        f"admin_promo_delete|"
                        f"{promo_id}"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Промокоды",
                    callback_data="admin_promos",
                )
            ],
        ]),
    )


# ============================================================
# PROMO CREATION
# ============================================================

async def promo_create_start(
    query,
):

    await query.edit_message_text(
        "🎁 НОВЫЙ ПРОМОКОД\n\n"

        "Введите код.\n\n"
        "Например:\n"
        "SEPTEMBER10"
    )

    return PROMO_CODE


async def promo_code_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    code = (
        update.message.text
        .strip()
        .upper()
    )

    context.user_data[
        "promo_code"
    ] = code

    await update.message.reply_text(
        "Выберите тип скидки:",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "📉 Процент",
                    callback_data=(
                        "admin_promo_type|PERCENT"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "💰 Фиксированная сумма",
                    callback_data=(
                        "admin_promo_type|FIXED"
                    ),
                )
            ],
        ]),
    )

    return PROMO_TYPE


async def promo_type_selected(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    await query.answer()

    promo_type = (
        query.data.split("|")[1]
    )

    context.user_data[
        "promo_type"
    ] = promo_type

    if promo_type == "PERCENT":

        text = (
            "Введите размер скидки в процентах.\n\n"
            "Например:\n"
            "10"
        )

    else:

        text = (
            "Введите сумму скидки в рублях.\n\n"
            "Например:\n"
            "500"
        )

    await query.edit_message_text(
        text
    )

    return PROMO_VALUE


async def promo_value_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text
            .strip()
        )

        if value <= 0:

            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите положительное число."
        )

        return PROMO_VALUE

    context.user_data[
        "promo_value"
    ] = value

    await update.message.reply_text(
        "Сколько раз промокод можно "
        "использовать всего?\n\n"

        "Введите число или:\n"
        "0 — без лимита"
    )

    return PROMO_MAX_USES


async def promo_max_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text
            .strip()
        )

        if value < 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите 0 или положительное число."
        )

        return PROMO_MAX_USES

    context.user_data[
        "promo_max"
    ] = (
        None
        if value == 0
        else value
    )

    await update.message.reply_text(
        "Сколько раз один ученик "
        "может использовать промокод?\n\n"

        "Например:\n"
        "1"
    )

    return PROMO_USER_LIMIT


async def promo_user_limit_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    try:

        value = int(
            update.message.text
            .strip()
        )

        if value <= 0:
            raise ValueError

    except ValueError:

        await update.message.reply_text(
            "❌ Введите положительное число."
        )

        return PROMO_USER_LIMIT

    context.user_data[
        "promo_user_limit"
    ] = value

    await update.message.reply_text(
        "Введите дату окончания действия.\n\n"

        "Например:\n"
        "31.12.2026\n\n"

        "Или отправьте:\n"
        "-"
    )

    return PROMO_EXPIRES


async def promo_expires_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = (
        update.message.text
        .strip()
    )

    expires = None

    if value != "-":

        try:

            parsed = datetime.strptime(
                value,
                "%d.%m.%Y",
            )

            parsed = parsed.replace(
                hour=23,
                minute=59,
                second=59,
            )

            expires = (
                parsed.isoformat()
            )

        except ValueError:

            await update.message.reply_text(
                "❌ Формат:\n"
                "31.12.2026\n\n"
                "Или -"
            )

            return PROMO_EXPIRES

    try:

        promo_id = database.create_promo_code(

            code=(
                context.user_data[
                    "promo_code"
                ]
            ),

            discount_type=(
                context.user_data[
                    "promo_type"
                ]
            ),

            discount_value=(
                context.user_data[
                    "promo_value"
                ]
            ),

            max_uses=(
                context.user_data[
                    "promo_max"
                ]
            ),

            per_user_limit=(
                context.user_data[
                    "promo_user_limit"
                ]
            ),

            expires_at=expires,
        )

    except Exception as error:

        await update.message.reply_text(
            f"❌ {error}"
        )

        return (
            ConversationHandler.END
        )

    for key in (
        "promo_code",
        "promo_type",
        "promo_value",
        "promo_max",
        "promo_user_limit",
    ):

        context.user_data.pop(
            key,
            None,
        )

    promo = database.get_promo(
        promo_id
    )

    await update.message.reply_text(
        "✅ ПРОМОКОД СОЗДАН\n\n"

        f"🎁 {promo['code']}",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎁 Промокоды",
                    callback_data="admin_promos",
                )
            ]
        ]),
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# PROMO ACTIONS
# ============================================================

async def promo_toggle(
    query,
    promo_id,
):

    database.toggle_promo(
        promo_id
    )

    await show_promo(
        query,
        promo_id,
    )


async def promo_delete(
    query,
    promo_id,
):

    database.delete_promo(
        promo_id
    )

    await query.edit_message_text(
        "✅ Промокод удалён / отключён.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🎁 Промокоды",
                    callback_data="admin_promos",
                )
            ]
        ]),
    )


# ============================================================
# ADMIN CANCEL LESSON
# ============================================================

async def show_cancel_lesson_menu(
    query,
    lesson_id,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        await query.answer(
            "Занятие не найдено.",
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    start_dt = datetime.fromisoformat(
        lesson["start_time"]
    )

    now = (
        datetime.now(tz=start_dt.tzinfo)
        if start_dt.tzinfo
        else datetime.now()
    )

    hours_left = max(
        (start_dt - now).total_seconds() / 3600,
        0,
    )

    await query.edit_message_text(
        "❌ ОТМЕНА ЗАНЯТИЯ\n\n"
        f"👤 {user['name']}\n"
        f"📅 {format_datetime(lesson['start_time'])}\n"
        f"⏱ {lesson['duration_minutes']} минут\n\n"
        f"До занятия: {hours_left:.1f} ч.\n\n"
        "Почему отменяем?",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👨‍🏫 Отмена преподавателем",
                    callback_data=(
                        f"admin_cancel_reason|"
                        f"{lesson_id}|ADMIN"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🤒 Я заболел — перенести",
                    callback_data=(
                        f"admin_cancel_reason|"
                        f"{lesson_id}|ADMIN_SICK"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "👤 По просьбе ученика",
                    callback_data=(
                        f"admin_cancel_reason|"
                        f"{lesson_id}|STUDENT"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ],
        ]),
    )


async def process_cancel_reason(
    query,
    context,
    lesson_id,
    reason,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:
        return

    start_dt = datetime.fromisoformat(
        lesson["start_time"]
    )

    now = (
        datetime.now(tz=start_dt.tzinfo)
        if start_dt.tzinfo
        else datetime.now()
    )

    hours_left = (
        start_dt - now
    ).total_seconds() / 3600

    if reason == "ADMIN_SICK":

        lesson_before = database.get_lesson(
            lesson_id
        )

        user = database.get_user(
            lesson_before["user_id"]
        )

        database.prepare_lesson_for_forced_reschedule(
            lesson_id,
            "ADMIN_SICKNESS_RESCHEDULE",
        )

        if user["telegram_id"]:

            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=(
                    "🤒 ПРЕПОДАВАТЕЛЬ ЗАБОЛЕЛ\n\n"
                    f"Занятие "
                    f"{format_datetime(lesson_before['start_time'])} "
                    "нужно перенести.\n\n"
                    "Выберите новое время сейчас "
                    "или позже."
                ),
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "📅 Выбрать новое время",
                            callback_data=(
                                f"reschedule_free|{lesson_id}"
                            ),
                        )
                    ]
                ]),
            )

        await query.edit_message_text(
            "🤒 Занятие поставлено на перенос.\n\n"
            "Если ученик не выберет новое время, "
            "через 2 дня бот ему напомнит."
        )

        return


    if reason == "ADMIN":

        await perform_admin_cancel(
            query=query,
            context=context,
            lesson_id=lesson_id,
            reason="ADMIN_CANCEL",
            refund=True,
        )

        return

    if (
        reason == "STUDENT"
        and hours_left >= 2
    ):

        await perform_admin_cancel(
            query=query,
            context=context,
            lesson_id=lesson_id,
            reason="STUDENT_CANCEL_FREE",
            refund=True,
        )

        return

    await query.edit_message_text(
        "⚠️ ДО ЗАНЯТИЯ МЕНЬШЕ 2 ЧАСОВ\n\n"
        "По правилам занятие должно быть списано.\n\n"
        "Как поступить?",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "💸 Списать занятие",
                    callback_data=(
                        f"admin_cancel_final|"
                        f"{lesson_id}|STUDENT_LATE|0"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "🎟 Вернуть занятие",
                    callback_data=(
                        f"admin_cancel_final|"
                        f"{lesson_id}|STUDENT_LATE_EXCEPTION|1"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ],
        ]),
    )


async def perform_admin_cancel(
    query,
    context,
    lesson_id,
    reason,
    refund,
):

    lesson_before = database.get_lesson(
        lesson_id
    )

    if lesson_before is None:
        return

    user = database.get_user(
        lesson_before["user_id"]
    )

    try:

        result = cancel_lesson_by_admin(
            lesson_id=lesson_id,
            reason=reason,
            refund=refund,
        )

    except Exception as error:

        await query.answer(
            str(error),
            show_alert=True,
        )

        return

    if user["telegram_id"]:

        message = (
            "❌ ЗАНЯТИЕ ОТМЕНЕНО\n\n"
            f"📅 {format_datetime(lesson_before['start_time'])}\n"
            f"📚 {subject_name(lesson_before['subject'])}\n\n"
        )

        if refund:

            if lesson_before["charged"]:
                message += "🎟 Занятие возвращено на ваш баланс."
            else:
                message += "🎟 Занятие не списано."

        else:
            message += (
                "⚠️ Занятие списано согласно "
                "правилам поздней отмены."
            )

        if lesson_before["regular_schedule_id"]:

            schedule = database.get_regular_schedule(
                lesson_before["regular_schedule_id"]
            )

            if schedule:

                message += (
                    "\n\n🔁 Постоянное расписание сохраняется:\n"
                    f"{WEEKDAYS[schedule['weekday']]}, "
                    f"{schedule['start_time']}.\n\n"
                    "Отменено только это занятие."
                )

        try:

            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=message,
            )

        except Exception as error:

            print(
                "CANCEL STUDENT NOTIFY:",
                repr(error),
            )

    text = (
        "✅ ЗАНЯТИЕ ОТМЕНЕНО\n\n"
        f"👤 {user['name']}\n"
        f"📅 {format_datetime(lesson_before['start_time'])}\n\n"
    )

    if refund:

        if result["refunded"]:
            text += "🎟 Занятие возвращено на баланс."
        elif not result["was_charged"]:
            text += "🎟 Списания ещё не было."
        else:
            text += "⚠️ Возврат не потребовался или не был выполнен."

    else:
        text += "💸 Занятие оставлено списанным."

    if result["regular_schedule_id"]:
        text += "\n\n🔁 Постоянная серия сохранена."

    await query.edit_message_text(
        text,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 К занятиям",
                    callback_data="admin_lessons",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Админка",
                    callback_data="admin_main",
                )
            ],
        ]),
    )


# ============================================================
# BOARD URL
# ============================================================

async def board_url_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):
        return ConversationHandler.END

    await query.answer()

    user_id = int(
        query.data.split("|")[1]
    )

    user = database.get_user(
        user_id
    )

    if user is None:
        return ConversationHandler.END

    context.user_data[
        "board_user_id"
    ] = user_id

    await query.edit_message_text(
        "🖥 ССЫЛКА НА ДОСКУ\n\n"

        f"👤 {user['name']}\n\n"

        "Отправьте постоянную ссылку "
        "на доску ученика.\n\n"

        "Она будет автоматически "
        "прикладываться к каждой ссылке "
        "на занятие."
    )

    return BOARD_URL


async def board_url_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    if not (
        value.startswith("http://")
        or value.startswith("https://")
    ):

        await update.message.reply_text(
            "❌ Отправьте ссылку, начинающуюся "
            "с http:// или https://"
        )

        return BOARD_URL

    user_id = context.user_data.get(
        "board_user_id"
    )

    if not user_id:
        return ConversationHandler.END

    database.set_student_board_url(
        user_id,
        value,
    )

    context.user_data.pop(
        "board_user_id",
        None,
    )

    await update.message.reply_text(
        "✅ Ссылка на доску сохранена.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👤 Карточка ученика",
                    callback_data=(
                        f"admin_student|{user_id}"
                    ),
                )
            ]
        ]),
    )

    return ConversationHandler.END


# ============================================================
# LESSON LINK -> START
# ============================================================

async def lesson_link_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):
        return ConversationHandler.END

    await query.answer()

    lesson_id = int(
        query.data.split("|")[1]
    )

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:
        return ConversationHandler.END

    user = database.get_user(
        lesson["user_id"]
    )

    context.user_data[
        "lesson_link_id"
    ] = lesson_id

    text = (
        "🔗 ССЫЛКА НА ЗАНЯТИЕ\n\n"

        f"👤 {user['name']}\n"
        f"📅 {format_datetime(lesson['start_time'])}\n\n"

        "Отправьте ссылку на созвон.\n\n"

        "После успешной отправки ссылки "
        "ученику занятие автоматически "
        "начнётся и запустится фактический таймер."
    )

    if not user["board_url"]:

        text += (
            "\n\n⚠️ У ученика пока не сохранена "
            "ссылка на постоянную доску."
        )

    await query.edit_message_text(
        text
    )

    return LESSON_LINK


async def send_link_and_start_lesson(
    context,
    lesson_id,
    value,
    force=False,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    user = database.get_user(
        lesson["user_id"]
    )

    student_text = (
        "🎓 ЗАНЯТИЕ НАЧИНАЕТСЯ\n\n"

        "🔗 Ссылка на занятие:\n"
        f"{value}"
    )

    if user["board_url"]:

        student_text += (
            "\n\n🖥 Ваша постоянная доска:\n"
            f"{user['board_url']}"
        )

    # Сначала проверяем, можно ли начать.
    # Для force=True разрешаем параллельный таймер осознанно.
    active = database.get_active_lesson(
        exclude_lesson_id=lesson_id
    )

    if (
        active is not None
        and not force
    ):

        raise RuntimeError(
            "ACTIVE_LESSON_CONFLICT"
        )

    # Ссылка должна быть доставлена ДО фиксации started_at.
    await context.bot.send_message(
        chat_id=user["telegram_id"],
        text=student_text,
    )

    sent_at = database.now_iso()

    database.save_lesson_meeting_url(
        lesson_id,
        value,
        sent_at=sent_at,
    )

    database.start_lesson(
        lesson_id,
        started_at=sent_at,
        force=force,
    )

    return {
        "lesson": lesson,
        "user": user,
        "started_at": sent_at,
    }



async def lesson_link_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    if not (
        value.startswith("http://")
        or value.startswith("https://")
    ):

        await update.message.reply_text(
            "❌ Отправьте ссылку, начинающуюся "
            "с http:// или https://"
        )

        return LESSON_LINK

    lesson_id = context.user_data.get(
        "lesson_link_id"
    )

    if not lesson_id:

        return ConversationHandler.END

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        return ConversationHandler.END

    active = database.get_active_lesson(
        exclude_lesson_id=lesson_id
    )

    if active is not None:

        # Ссылку пока НЕ отправляем ученику.
        context.user_data[
            "pending_lesson_link_id"
        ] = lesson_id

        context.user_data[
            "pending_lesson_link_url"
        ] = value

        await update.message.reply_text(
            "⚠️ СЕЙЧАС УЖЕ ИДЁТ ЗАНЯТИЕ\n\n"

            f"👤 {active['name']}\n"
            f"▶️ Начато: "
            f"{format_datetime(active['started_at'])}\n\n"

            "Новому ученику ссылка пока "
            "не отправлена.\n\n"

            "Что сделать?",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⏹ Завершить текущее",
                        callback_data=(
                            f"admin_overlap_finish_only|"
                            f"{active['id']}|{lesson_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⏳ +5 мин",
                        callback_data=(
                            f"admin_overlap_delay|{lesson_id}|5"
                        ),
                    ),
                    InlineKeyboardButton(
                        "⏳ +10 мин",
                        callback_data=(
                            f"admin_overlap_delay|{lesson_id}|10"
                        ),
                    ),
                    InlineKeyboardButton(
                        "⏳ +15 мин",
                        callback_data=(
                            f"admin_overlap_delay|{lesson_id}|15"
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "▶️ Всё равно начать новое",
                        callback_data=(
                            f"admin_overlap_force_start|{lesson_id}"
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Пока не начинать",
                        callback_data=(
                            f"admin_lesson_view|{lesson_id}"
                        ),
                    )
                ],
            ]),
        )

        return ConversationHandler.END

    try:

        result = await send_link_and_start_lesson(
            context,
            lesson_id,
            value,
            force=False,
        )

    except Exception as error:

        await update.message.reply_text(
            "❌ Не удалось отправить ссылку "
            "и начать занятие.\n\n"
            f"{error}\n\n"
            "Занятие НЕ запущено."
        )

        return LESSON_LINK

    context.user_data.pop(
        "lesson_link_id",
        None,
    )

    text = (
        "✅ Ссылка отправлена ученику.\n\n"
        "▶️ Занятие запущено.\n"
        f"⏱ Начало: "
        f"{format_datetime(result['started_at'])}"
    )

    if not result["user"]["board_url"]:

        text += (
            "\n\n⚠️ Доска не была приложена, "
            "так как она ещё не сохранена."
        )

    await update.message.reply_text(
        text,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть занятие",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ]
        ]),
    )

    return ConversationHandler.END


async def lesson_delay_menu(query, lesson_id):
    lesson = database.get_lesson(lesson_id)
    if lesson is None:
        await query.answer("Занятие не найдено.", show_alert=True)
        return

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("+5 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|5"),
                InlineKeyboardButton("+10 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|10"),
                InlineKeyboardButton("+15 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|15"),
            ],
            [
                InlineKeyboardButton("+20 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|20"),
                InlineKeyboardButton("+25 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|25"),
                InlineKeyboardButton("+30 мин", callback_data=f"admin_lesson_delay_choose|{lesson_id}|30"),
            ],
            [
                InlineKeyboardButton(
                    "🤷 Не знаю, сообщу позже",
                    callback_data=f"admin_lesson_delay_choose|{lesson_id}|unknown",
                )
            ],
            [
                InlineKeyboardButton("🔗 Отправить ссылку", callback_data=f"admin_send_lesson_link|{lesson_id}"),
            ],
            [
                InlineKeyboardButton("📚 Открыть занятие", callback_data=f"admin_lesson_view|{lesson_id}"),
            ],
        ])
    )
    await query.answer("На сколько задерживаетесь?")


def _delay_recipient_keyboard(lesson_id, delay_value):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "👥 Всем",
            callback_data=f"admin_lesson_delay_send|{lesson_id}|{delay_value}|all",
        )],
        [
            InlineKeyboardButton(
                "👤 Ученику",
                callback_data=f"admin_lesson_delay_send|{lesson_id}|{delay_value}|student",
            ),
            InlineKeyboardButton(
                "👨‍👩‍👧 Родителям",
                callback_data=f"admin_lesson_delay_send|{lesson_id}|{delay_value}|parents",
            ),
        ],
        [InlineKeyboardButton(
            "⬅️ Назад",
            callback_data=f"admin_lesson_delay_menu|{lesson_id}",
        )],
    ])


async def choose_lesson_delay_recipients(query, lesson_id, delay_value):
    lesson = database.get_lesson(lesson_id)
    if lesson is None:
        await query.answer("Занятие не найдено.", show_alert=True)
        return

    if delay_value == "unknown":
        label = "точное время пока неизвестно"
    else:
        label = f"задержка примерно на {int(delay_value)} мин"

    await query.edit_message_reply_markup(
        reply_markup=_delay_recipient_keyboard(lesson_id, delay_value)
    )
    await query.answer(f"Кому сообщить: {label}?")


async def _send_delay_notice(context, lesson, recipient, minutes=None, unknown=False, estimated_dt=None):
    user = database.get_user(lesson["user_id"])
    start_dt = datetime.fromisoformat(lesson["start_time"])

    if unknown:
        student_text = (
            "⏳ Преподаватель задерживается.\n\n"
            f"📅 Занятие: {start_dt.strftime('%d.%m.%Y')}\n"
            f"🕐 Плановое начало: {start_dt.strftime('%H:%M')}\n"
            "🤷 Точное время начала пока неизвестно.\n"
            "Преподаватель сообщит его дополнительно."
        )
        parent_text = (
            f"⏳ Задержка занятия у {user['name'] if user else 'ученика'}\n\n"
            f"Плановое начало: {start_dt.strftime('%H:%M')}\n"
            "Точное время начала пока неизвестно. Преподаватель сообщит его дополнительно."
        )
    else:
        if estimated_dt is None:
            estimated_dt = start_dt + timedelta(minutes=int(minutes or 0))
        student_text = (
            "⏳ Преподаватель немного задерживается.\n\n"
            f"📅 Занятие: {start_dt.strftime('%d.%m.%Y')}\n"
            f"🕐 Плановое начало: {start_dt.strftime('%H:%M')}\n"
            + (f"⏱ Задержка: примерно {minutes} мин\n" if minutes is not None else "")
            + f"▶️ Ориентировочно начнём в {estimated_dt.strftime('%H:%M')}.\n\n"
            "Ссылка на занятие придёт, как только преподаватель будет готов."
        )
        parent_text = (
            f"⏳ Задержка занятия у {user['name'] if user else 'ученика'}\n\n"
            f"Плановое начало: {start_dt.strftime('%H:%M')}\n"
            + (f"Преподаватель задерживается примерно на {minutes} мин.\n" if minutes is not None else "")
            + f"Ориентировочное начало: {estimated_dt.strftime('%H:%M')}."
        )

    delivered = 0
    if recipient in ("all", "student") and user and user["telegram_id"]:
        try:
            await context.bot.send_message(chat_id=user["telegram_id"], text=student_text)
            delivered += 1
        except Exception:
            pass

    if recipient in ("all", "parents"):
        for parent in database.get_student_parents(lesson["user_id"], schedule_only=True):
            if not parent["telegram_id"]:
                continue
            try:
                await context.bot.send_message(chat_id=parent["telegram_id"], text=parent_text)
                delivered += 1
            except Exception:
                pass

    return delivered


def _cancel_delay_reminder(context, lesson_id):
    if not context.job_queue:
        return
    name = f"tutor_delay_followup_{lesson_id}"
    for job in context.job_queue.get_jobs_by_name(name):
        job.schedule_removal()


def _schedule_delay_reminder(context, lesson_id, recipient):
    if not context.job_queue:
        return False
    _cancel_delay_reminder(context, lesson_id)
    context.job_queue.run_once(
        tutor_delay_followup_job,
        when=5 * 60,
        data={"lesson_id": lesson_id, "recipient": recipient},
        name=f"tutor_delay_followup_{lesson_id}",
    )
    return True


async def tutor_delay_followup_job(context):
    data = context.job.data or {}
    lesson_id = int(data.get("lesson_id", 0))
    recipient = data.get("recipient", "all")
    lesson = database.get_lesson(lesson_id)
    if not lesson or lesson["lesson_status"] not in ("CONFIRMED", "PENDING"):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("+5", callback_data=f"admin_lesson_delay_followup|{lesson_id}|5|{recipient}"),
            InlineKeyboardButton("+10", callback_data=f"admin_lesson_delay_followup|{lesson_id}|10|{recipient}"),
            InlineKeyboardButton("+15", callback_data=f"admin_lesson_delay_followup|{lesson_id}|15|{recipient}"),
        ],
        [
            InlineKeyboardButton("+20", callback_data=f"admin_lesson_delay_followup|{lesson_id}|20|{recipient}"),
            InlineKeyboardButton("+25", callback_data=f"admin_lesson_delay_followup|{lesson_id}|25|{recipient}"),
            InlineKeyboardButton("+30", callback_data=f"admin_lesson_delay_followup|{lesson_id}|30|{recipient}"),
        ],
        [InlineKeyboardButton(
            "✍️ Указать время начала",
            callback_data=f"admin_lesson_delay_custom|{lesson_id}|{recipient}",
        )],
        [InlineKeyboardButton(
            "🤷 Ещё не знаю",
            callback_data=f"admin_lesson_delay_followup|{lesson_id}|unknown|{recipient}",
        )],
    ])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=(
            "⏰ Вы обещали уточнить время начала занятия.\n\n"
            "Выберите задержку, укажите точное время или нажмите «Ещё не знаю»."
        ),
        reply_markup=keyboard,
    )


async def send_lesson_delay(query, context, lesson_id, delay_value, recipient):
    lesson = database.get_lesson(lesson_id)
    if lesson is None:
        await query.answer("Занятие не найдено.", show_alert=True)
        return
    if lesson["lesson_status"] not in ("CONFIRMED", "PENDING"):
        await query.answer("Для этого занятия задержку уже нельзя отметить.", show_alert=True)
        return

    if recipient not in ("all", "student", "parents"):
        recipient = "all"

    if delay_value == "unknown":
        database.set_lesson_tutor_delay(lesson_id, 0)
        await _send_delay_notice(context, lesson, recipient, unknown=True)
        scheduled = _schedule_delay_reminder(context, lesson_id, recipient)
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🤷 Время уточняется", callback_data=f"admin_lesson_delay_menu|{lesson_id}")],
                [InlineKeyboardButton("📚 Открыть занятие", callback_data=f"admin_lesson_view|{lesson_id}")],
            ])
        )
        await query.answer(
            "Уведомление отправлено. Напомню через 5 минут." if scheduled else "Уведомление отправлено.",
            show_alert=False,
        )
        return

    minutes = max(5, min(30, int(delay_value)))
    database.set_lesson_tutor_delay(lesson_id, minutes)
    _cancel_delay_reminder(context, lesson_id)
    start_dt = datetime.fromisoformat(lesson["start_time"])
    estimated_dt = start_dt + timedelta(minutes=minutes)
    await _send_delay_notice(context, lesson, recipient, minutes=minutes, estimated_dt=estimated_dt)

    await query.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⏱ Задержка: {minutes} мин", callback_data=f"admin_lesson_delay_menu|{lesson_id}")],
            [InlineKeyboardButton("🔗 Отправить ссылку на занятие", callback_data=f"admin_send_lesson_link|{lesson_id}")],
            [InlineKeyboardButton("📚 Открыть занятие", callback_data=f"admin_lesson_view|{lesson_id}")],
        ])
    )
    await query.answer(f"Отправлено. Ориентир: {estimated_dt.strftime('%H:%M')}", show_alert=False)


async def followup_lesson_delay(query, context, lesson_id, delay_value, recipient):
    if delay_value == "unknown":
        lesson = database.get_lesson(lesson_id)
        if lesson is None:
            await query.answer("Занятие не найдено.", show_alert=True)
            return
        await _send_delay_notice(context, lesson, recipient, unknown=True)
        _schedule_delay_reminder(context, lesson_id, recipient)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("Хорошо. Ещё раз напомню через 5 минут.")
        return

    await send_lesson_delay(query, context, lesson_id, delay_value, recipient)


async def delay_custom_time_entry(update, context):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("|")
    lesson_id = int(parts[1])
    recipient = parts[2] if len(parts) > 2 else "all"
    context.user_data["delay_custom_lesson_id"] = lesson_id
    context.user_data["delay_custom_recipient"] = recipient
    await query.message.reply_text(
        "✍️ Напишите новое ориентировочное время начала в формате ЧЧ:ММ.\n"
        "Например: 18:35"
    )
    return DELAY_CUSTOM_TIME


async def delay_custom_time_handler(update, context):
    raw = (update.message.text or "").strip()
    try:
        parsed = datetime.strptime(raw, "%H:%M")
    except ValueError:
        await update.message.reply_text("Введите время в формате ЧЧ:ММ, например 18:35.")
        return DELAY_CUSTOM_TIME

    lesson_id = context.user_data.get("delay_custom_lesson_id")
    recipient = context.user_data.get("delay_custom_recipient", "all")
    lesson = database.get_lesson(lesson_id) if lesson_id else None
    if lesson is None:
        await update.message.reply_text("Занятие не найдено.")
        return ConversationHandler.END

    start_dt = datetime.fromisoformat(lesson["start_time"])
    estimated_dt = start_dt.replace(hour=parsed.hour, minute=parsed.minute, second=0, microsecond=0)
    if estimated_dt < start_dt - timedelta(hours=6):
        estimated_dt += timedelta(days=1)

    delay_minutes = max(0, int(round((estimated_dt - start_dt).total_seconds() / 60)))
    database.set_lesson_tutor_delay(lesson_id, delay_minutes)
    _cancel_delay_reminder(context, lesson_id)
    await _send_delay_notice(context, lesson, recipient, minutes=None, estimated_dt=estimated_dt)

    context.user_data.pop("delay_custom_lesson_id", None)
    context.user_data.pop("delay_custom_recipient", None)
    await update.message.reply_text(
        f"✅ Новое ориентировочное начало {estimated_dt.strftime('%H:%M')} отправлено выбранным получателям."
    )
    return ConversationHandler.END


async def overlap_send_delay(
    query,
    context,
    lesson_id,
    minutes,
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        await query.answer(
            "Занятие не найдено.",
            show_alert=True,
        )

        return

    user = database.get_user(
        lesson["user_id"]
    )

    if not user or not user["telegram_id"]:

        await query.answer(
            "У ученика нет Telegram.",
            show_alert=True,
        )

        return

    try:

        await context.bot.send_message(
            chat_id=user["telegram_id"],
            text=(
                "⏳ Преподаватель немного задерживается.\n\n"
                f"Ориентировочно ещё {minutes} минут.\n\n"
                "Ссылка на занятие придёт сразу, "
                "как только преподаватель освободится."
            ),
        )

    except Exception as error:

        await query.answer(
            f"Не удалось отправить сообщение: {error}",
            show_alert=True,
        )

        return

    await query.answer(
        f"Ученику отправлено: ещё {minutes} мин.",
        show_alert=False,
    )


async def overlap_finish_only(
    query,
    context,
    active_lesson_id,
    new_lesson_id,
):

    try:

        finish_result = database.finish_lesson(
            active_lesson_id
        )

    except Exception as error:

        await query.answer(
            f"Не удалось завершить текущее: {error}",
            show_alert=True,
        )

        return

    # Старую заранее введённую ссылку намеренно забываем.
    # Для нового занятия преподаватель отправляет новую.
    for key in (
        "pending_lesson_link_url",
        "pending_lesson_link_id",
        "lesson_link_id",
    ):

        context.user_data.pop(
            key,
            None,
        )

    await query.edit_message_text(
        "✅ Предыдущее занятие завершено.\n\n"

        f"Фактически: "
        f"{finish_result['actual_minutes']} мин\n\n"

        "Следующее занятие пока НЕ начато.\n"
        "Когда будете готовы, отправьте ученику "
        "новую ссылку на занятие.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔗 Отправить новую ссылку",
                    callback_data=(
                        f"admin_send_lesson_link|{new_lesson_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Открыть следующее занятие",
                    callback_data=(
                        f"admin_lesson_view|{new_lesson_id}"
                    ),
                )
            ],
        ]),
    )


async def overlap_force_start(
    query,
    context,
    lesson_id,
):

    value = context.user_data.get(
        "pending_lesson_link_url"
    )

    pending_id = context.user_data.get(
        "pending_lesson_link_id"
    )

    if (
        not value
        or pending_id != lesson_id
    ):

        await query.answer(
            "Ссылка потеряна. "
            "Отправьте её заново.",
            show_alert=True,
        )

        return

    try:

        result = await send_link_and_start_lesson(
            context,
            lesson_id,
            value,
            force=True,
        )

    except Exception as error:

        await query.edit_message_text(
            f"❌ {error}"
        )

        return

    for key in (
        "pending_lesson_link_url",
        "pending_lesson_link_id",
        "lesson_link_id",
    ):

        context.user_data.pop(
            key,
            None,
        )

    await query.edit_message_text(
        "✅ Новое занятие запущено "
        "параллельно.\n\n"

        f"⏱ Начало: "
        f"{format_datetime(result['started_at'])}\n\n"

        "⚠️ Теперь в системе одновременно "
        "идут два занятия. Завершите каждое "
        "отдельно, чтобы статистика была корректной.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть новое занятие",
                    callback_data=(
                        f"admin_lesson_view|{lesson_id}"
                    ),
                )
            ]
        ]),
    )


async def overlap_finish_and_start(
    query,
    context,
    active_lesson_id,
    new_lesson_id,
):

    value = context.user_data.get(
        "pending_lesson_link_url"
    )

    pending_id = context.user_data.get(
        "pending_lesson_link_id"
    )

    if (
        not value
        or pending_id != new_lesson_id
    ):

        await query.answer(
            "Ссылка потеряна. "
            "Отправьте её заново.",
            show_alert=True,
        )

        return

    try:

        finish_result = database.finish_lesson(
            active_lesson_id
        )

    except Exception as error:

        await query.answer(
            f"Не удалось завершить текущее: {error}",
            show_alert=True,
        )

        return

    try:

        result = await send_link_and_start_lesson(
            context,
            new_lesson_id,
            value,
            force=False,
        )

    except Exception as error:

        await query.edit_message_text(
            "⚠️ Текущее занятие завершено, "
            "но новое не удалось запустить.\n\n"
            f"{error}"
        )

        return

    for key in (
        "pending_lesson_link_url",
        "pending_lesson_link_id",
        "lesson_link_id",
    ):

        context.user_data.pop(
            key,
            None,
        )

    await query.edit_message_text(
        "✅ Предыдущее занятие завершено.\n\n"

        f"Фактически: "
        f"{finish_result['actual_minutes']} мин\n\n"

        "▶️ Новое занятие запущено.\n"
        f"⏱ Начало: "
        f"{format_datetime(result['started_at'])}",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Открыть новое занятие",
                    callback_data=(
                        f"admin_lesson_view|{new_lesson_id}"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# EXTRA HOMEWORK
# ============================================================

async def extra_hw_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):
        return ConversationHandler.END

    await query.answer()

    program_id = int(
        query.data.split("|")[1]
    )

    program = database.get_student_program(
        program_id
    )

    if program is None:
        return ConversationHandler.END

    context.user_data[
        "extra_hw_program_id"
    ] = program_id

    await query.edit_message_text(
        "➕ ДОПОЛНИТЕЛЬНОЕ ДЗ\n\n"

        f"👤 {program['name']}\n"
        f"📚 {program_title(program['study_goal'], program['subject'])}\n\n"

        "Напишите задание одним сообщением."
    )

    return EXTRA_HW_TEXT


async def extra_hw_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    value = update.message.text.strip()

    if not value:

        await update.message.reply_text(
            "❌ Задание не может быть пустым."
        )

        return EXTRA_HW_TEXT

    context.user_data[
        "extra_hw_text"
    ] = value

    await update.message.reply_text(
        "Введите срок выполнения:\n"
        "например 25.08.2026\n\n"
        "Или отправьте «-», если без срока."
    )

    return EXTRA_HW_DEADLINE


async def extra_hw_deadline_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    raw = update.message.text.strip()
    deadline = None

    if raw != "-":

        try:

            parsed = datetime.strptime(
                raw,
                "%d.%m.%Y",
            )

            parsed = parsed.replace(
                hour=23,
                minute=59,
                second=0,
            )

            deadline = parsed.isoformat()

        except ValueError:

            await update.message.reply_text(
                "❌ Формат даты: 25.08.2026\n"
                "Или отправьте -"
            )

            return EXTRA_HW_DEADLINE

    program_id = context.user_data.get(
        "extra_hw_program_id"
    )

    description = context.user_data.get(
        "extra_hw_text"
    )

    program = database.get_student_program(
        program_id
    )

    if program is None:
        return ConversationHandler.END

    homework_id = database.create_homework(
        user_id=program["user_id"],
        study_goal=program["study_goal"],
        subject=program["subject"],
        description=description,
        title="Дополнительное домашнее задание",
        lesson_id=None,
        deadline=deadline,
        program_id=program_id,
        homework_type="ADDITIONAL",
    )

    if program["telegram_id"]:

        message = (
            "➕ ДОПОЛНИТЕЛЬНОЕ ДОМАШНЕЕ ЗАДАНИЕ\n\n"

            f"📚 {program_title(program['study_goal'], program['subject'])}\n\n"

            f"{description}"
        )

        if deadline:

            message += (
                "\n\n📅 Срок: "
                f"{format_datetime(deadline)}"
            )

        try:

            await context.bot.send_message(
                chat_id=program["telegram_id"],
                text=message,
            )

        except Exception as error:

            print(
                "EXTRA HW STUDENT NOTIFY:",
                repr(error),
            )

    for key in (
        "extra_hw_program_id",
        "extra_hw_text",
    ):

        context.user_data.pop(
            key,
            None,
        )

    await update.message.reply_text(
        "✅ Дополнительное ДЗ задано.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📚 Направление",
                    callback_data=(
                        f"admin_program|{program_id}"
                    ),
                )
            ]
        ]),
    )

    return ConversationHandler.END


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def admin_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        await deny_access(update)
        return

    await query.answer()

    data = query.data

    # ========================================================
    # MAIN
    # ========================================================

    if data == "admin_main":

        await show_admin_main(
            query
        )

        return

    if data == "admin_contact":
        await show_admin_contact(query)
        return


    # ========================================================
    # ВАЖНО:
    # admin_schedule ЗДЕСЬ НЕТ.
    # Его обрабатывает schedule_admin.py
    # ========================================================


    # ========================================================
    # PARENTS / PAYMENT METHODS / ACCESS
    # ========================================================

    if data == "admin_parents":
        await show_parents(query)
        return

    if data.startswith("admin_parent|"):
        await show_parent(query, int(data.split("|")[1]))
        return

    if data == "admin_payment_methods":
        await show_payment_methods(query)
        return

    if data.startswith("admin_paymethod_default|"):
        method_id = int(data.split("|")[1])
        database.set_payment_method_default(method_id)
        await query.answer("Готово 💜 Теперь это основной способ оплаты.", show_alert=True)
        await show_payment_method(query, method_id)
        return

    if data.startswith("admin_paymethod_toggle|"):
        method_id = int(data.split("|")[1])
        database.toggle_payment_method(method_id)
        await show_payment_method(query, method_id)
        return

    if data.startswith("admin_paymethod_delete_warn|"):
        await payment_method_delete_warning(query, int(data.split("|")[1]))
        return

    if data.startswith("admin_paymethod_delete|"):
        database.delete_payment_method(int(data.split("|")[1]))
        await query.answer("Я удалила способ оплаты.", show_alert=True)
        await show_payment_methods(query)
        return

    if data.startswith("admin_paymethod|"):
        await show_payment_method(query, int(data.split("|")[1]))
        return

    if data.startswith("admin_student_block_warn|"):
        await student_block_warning(query, int(data.split("|")[1]))
        return

    if data.startswith("admin_student_block_confirm|"):
        await student_block_confirm(query, context, int(data.split("|")[1]))
        return

    if data.startswith("admin_student_unblock|"):
        await student_unblock(query, context, int(data.split("|")[1]))
        return


    # ========================================================
    # REQUESTS
    # ========================================================

    if data == "admin_requests":

        await show_requests(
            query
        )

        return


    if data.startswith(
        "admin_request_view|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_request(
            query,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_request_approve|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await approve_request(
            query,
            context,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_request_reject|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await reject_request(
            query,
            context,
            lesson_id,
        )

        return


    # ========================================================
    # ALL LESSONS / CANCELLATION
    # ========================================================

    if data == "admin_lessons":

        await show_admin_lessons(
            query
        )

        return


    if data.startswith(
        "admin_cancel_lesson|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_cancel_lesson_menu(
            query,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_cancel_reason|"
    ):

        parts = data.split("|")

        await process_cancel_reason(
            query,
            context,
            int(parts[1]),
            parts[2],
        )

        return


    if data.startswith(
        "admin_cancel_final|"
    ):

        parts = data.split("|")

        await perform_admin_cancel(
            query=query,
            context=context,
            lesson_id=int(parts[1]),
            reason=parts[2],
            refund=(parts[3] == "1"),
        )

        return


    # ========================================================
    # TODAY
    # ========================================================

    if data == "admin_today":

        await show_today(
            query
        )

        return


    # ========================================================
    # LESSON
    # ========================================================

    if data.startswith(
        "admin_lesson_view|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await show_lesson(
            query,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_lesson_start|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await start_lesson(
            query,
            context,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_lesson_finish|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await finish_lesson(
            query,
            context,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_lesson_noshow|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await no_show(
            query,
            context,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_lesson_paid|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await confirm_lesson_payment(
            query,
            context,
            lesson_id,
        )

        return


    # ========================================================
    # HOMEWORK
    # ========================================================

    if data.startswith(
        "admin_homework_skip|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await skip_homework(
            query,
            lesson_id,
        )

        return


    # Кнопку admin_homework|ID
    # позже подключим к полноценному
    # редактору ДЗ в bot.py / homework модуле.


    # ========================================================
    # PRICES
    # ========================================================

    if data == "admin_prices":

        await show_prices(
            query
        )
        return


    if data.startswith(
        "admin_price_default|"
    ):

        rate_key = (
            data.split("|", 1)[1]
        )

        await show_default_price(
            query,
            rate_key,
        )
        return


    if data.startswith(
        "admin_student_price_reset|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await reset_student_price(
            query,
            user_id,
        )
        return


    if data.startswith("admin_lesson_delay_menu|"):
        lesson_id = int(data.split("|")[1])
        await lesson_delay_menu(query, lesson_id)
        return

    if data.startswith("admin_lesson_delay_choose|"):
        parts = data.split("|")
        lesson_id = int(parts[1])
        delay_value = parts[2]
        await choose_lesson_delay_recipients(query, lesson_id, delay_value)
        return

    if data.startswith("admin_lesson_delay_send|"):
        parts = data.split("|")
        lesson_id = int(parts[1])
        delay_value = parts[2]
        recipient = parts[3]
        await send_lesson_delay(query, context, lesson_id, delay_value, recipient)
        return

    if data.startswith("admin_lesson_delay_followup|"):
        parts = data.split("|")
        lesson_id = int(parts[1])
        delay_value = parts[2]
        recipient = parts[3]
        await followup_lesson_delay(query, context, lesson_id, delay_value, recipient)
        return


    # ========================================================
    # OVERLAPPING LESSONS
    # ========================================================

    if data.startswith(
        "admin_overlap_delay|"
    ):

        parts = data.split("|")

        lesson_id = int(
            parts[1]
        )

        minutes = int(
            parts[2]
        )

        await overlap_send_delay(
            query,
            context,
            lesson_id,
            minutes,
        )

        return


    if data.startswith(
        "admin_overlap_finish_only|"
    ):

        parts = data.split("|")

        active_lesson_id = int(
            parts[1]
        )

        new_lesson_id = int(
            parts[2]
        )

        await overlap_finish_only(
            query,
            context,
            active_lesson_id,
            new_lesson_id,
        )

        return


    if data.startswith(
        "admin_overlap_force_start|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        await overlap_force_start(
            query,
            context,
            lesson_id,
        )

        return


    if data.startswith(
        "admin_overlap_finish_start|"
    ):

        parts = data.split("|")

        active_lesson_id = int(
            parts[1]
        )

        new_lesson_id = int(
            parts[2]
        )

        await overlap_finish_and_start(
            query,
            context,
            active_lesson_id,
            new_lesson_id,
        )

        return


    # ========================================================
    # STUDENT PROGRAMS
    # ========================================================

    if data.startswith(
        "admin_program_price_reset|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await reset_program_price(
            query,
            program_id,
        )

        return


    if data.startswith(
        "admin_program_primary|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await make_program_primary(
            query,
            program_id,
        )

        return


    if data.startswith(
        "admin_program_stats|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await show_program_stats(
            query,
            program_id,
        )

        return


    if data.startswith(
        "admin_program_disable_warn|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await disable_program_warning(
            query,
            program_id,
        )

        return


    if data.startswith(
        "admin_program_disable|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await disable_program(
            query,
            program_id,
        )

        return


    if data.startswith(
        "admin_program|"
    ):

        program_id = int(
            data.split("|")[1]
        )

        await show_program(
            query,
            program_id,
        )

        return


    # ========================================================
    # FULL STUDENT DELETE
    # ========================================================

    if data.startswith(
        "admin_student_delete_warn|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await student_delete_warning(
            query,
            user_id,
        )

        return


    if data.startswith(
        "admin_student_delete_confirm|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await student_delete_confirm(
            query,
            user_id,
        )

        return


    if data.startswith(
        "admin_student_delete_final|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await student_delete_final(
            query,
            user_id,
        )

        return


    # ========================================================
    # STUDENTS
    # ========================================================

    if data == "admin_students":

        await show_students(
            query
        )

        return


    if data.startswith(
        "admin_students_grade|"
    ):

        grade = int(
            data.split("|")[1]
        )

        await show_students(
            query,
            grade_filter=grade,
        )

        return


    if data.startswith(
        "admin_student|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_student(
            query,
            user_id,
        )

        return


    if data.startswith(
        "admin_student_stats|"
    ):

        user_id = int(
            data.split("|")[1]
        )

        await show_student_stats(
            query,
            user_id,
        )

        return


    # ========================================================
    # UNPAID
    # ========================================================

    if data == "admin_unpaid_lessons":

        await show_unpaid(
            query
        )

        return


    # ========================================================
    # STATISTICS
    # ========================================================

    if data == "admin_statistics":
        await show_statistics(query, "all")
        return

    if data.startswith("admin_statistics|"):
        period = data.split("|", 1)[1]
        await show_statistics(query, period)
        return

    if data.startswith("admin_balance|"):
        user_id = int(data.split("|")[1])
        await show_admin_balance(query, user_id)
        return

    if data.startswith("admin_balance_add|"):
        _, user_id, program_id = data.split("|")
        user_id = int(user_id)
        program_id = int(program_id)
        program = database.get_student_program(program_id)
        rate = database.get_program_rate_info(program_id)["effective_rate"] if program else 0
        duration = 90 if program and program["study_goal"] in {"OGE", "EGE", "OLYMPIAD"} else 60
        nominal = database.calculate_lesson_price(rate, duration) if program else 0
        package_id = database.admin_add_balance_lesson(user_id, program_id)
        actor_id = update.effective_user.id
        core_financial_ledger.append(user_id, lessons_delta=1, nominal=nominal, entry_type="ADMIN_BALANCE_ADD", source_type="package", source_id=package_id, description="Ручное добавление занятия", actor_id=actor_id)
        core_audit_log.log("BALANCE_ADD", actor_id, "user", user_id, {"nominal": nominal, "package_id": package_id})
        await query.answer("Занятие добавлено на баланс.")
        await show_admin_balance(query, user_id)
        return

    if data.startswith("admin_balance_remove|"):
        _, user_id, nominal = data.split("|")
        user_id = int(user_id)
        nominal = int(nominal)
        package_id = database.admin_remove_balance_lesson(user_id, nominal)
        if package_id is None:
            await query.answer("На этом номинале нет занятий.", show_alert=True)
        else:
            actor_id = update.effective_user.id
            core_financial_ledger.append(user_id, lessons_delta=-1, nominal=nominal, entry_type="ADMIN_BALANCE_REMOVE", source_type="package", source_id=package_id, description="Ручное списание занятия", actor_id=actor_id)
            core_audit_log.log("BALANCE_REMOVE", actor_id, "user", user_id, {"nominal": nominal, "package_id": package_id})
            await query.answer("Одно занятие списано с баланса.")
        await show_admin_balance(query, user_id)
        return


    # ========================================================
    # PROMOS
    # ========================================================

    if data == "admin_promos":

        await show_promos(
            query
        )

        return


    if data.startswith(
        "admin_promo_toggle|"
    ):

        promo_id = int(
            data.split("|")[1]
        )

        await promo_toggle(
            query,
            promo_id,
        )

        return


    if data.startswith(
        "admin_promo_delete|"
    ):

        promo_id = int(
            data.split("|")[1]
        )

        await promo_delete(
            query,
            promo_id,
        )

        return


    if data.startswith(
        "admin_promo|"
    ):

        promo_id = int(
            data.split("|")[1]
        )

        await show_promo(
            query,
            promo_id,
        )

        return


# ============================================================
# MANUAL CONVERSATION ENTRY
# ============================================================

async def manual_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        return (
            ConversationHandler.END
        )

    await query.answer()

    return await manual_lesson_start(
        query,
        context,
    )


async def manual_for_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        return (
            ConversationHandler.END
        )

    await query.answer()

    user_id = int(
        query.data.split("|")[1]
    )

    return await manual_for_student(
        query,
        context,
        user_id,
    )


# ============================================================
# PROMO CONVERSATION ENTRY
# ============================================================

async def promo_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not is_admin(update):

        return (
            ConversationHandler.END
        )

    await query.answer()

    return await promo_create_start(
        query
    )


# ============================================================
# CONVERSATION HANDLER
# ============================================================

def get_admin_conversation_handler():

    return ConversationHandler(

        entry_points=[

            CallbackQueryHandler(
                manual_entry,
                pattern=(
                    r"^admin_manual_lesson$"
                ),
            ),

            CallbackQueryHandler(
                manual_for_entry,
                pattern=(
                    r"^admin_manual_for\|"
                ),
            ),

            CallbackQueryHandler(
                promo_entry,
                pattern=(
                    r"^admin_promo_create$"
                ),
            ),

            CallbackQueryHandler(
                payment_method_add_entry,
                pattern=r"^admin_paymethod_add$",
            ),

            CallbackQueryHandler(
                default_price_edit_entry,
                pattern=(
                    r"^admin_price_default_edit\|"
                ),
            ),

            CallbackQueryHandler(
                student_price_edit_entry,
                pattern=(
                    r"^admin_student_price\|"
                ),
            ),

            CallbackQueryHandler(
                program_add_entry,
                pattern=(
                    r"^admin_program_add\|"
                ),
            ),

            CallbackQueryHandler(
                program_price_entry,
                pattern=(
                    r"^admin_program_price\|"
                ),
            ),

            CallbackQueryHandler(
                board_url_entry,
                pattern=(
                    r"^admin_board_set\|"
                ),
            ),

            CallbackQueryHandler(
                lesson_link_entry,
                pattern=(
                    r"^admin_send_lesson_link\|"
                ),
            ),

            CallbackQueryHandler(
                extra_hw_entry,
                pattern=(
                    r"^admin_extra_hw\|"
                ),
            ),

            CallbackQueryHandler(
                delay_custom_time_entry,
                pattern=(r"^admin_lesson_delay_custom\|"),
            ),

            CallbackQueryHandler(contact_name_entry, pattern=r"^admin_contact_edit_name$"),
            CallbackQueryHandler(contact_description_entry, pattern=r"^admin_contact_edit_description$"),
            CallbackQueryHandler(contact_telegram_entry, pattern=r"^admin_contact_edit_telegram$"),
            CallbackQueryHandler(contact_phone_entry, pattern=r"^admin_contact_edit_phone$"),
            CallbackQueryHandler(contact_note_entry, pattern=r"^admin_contact_edit_note$"),
            CallbackQueryHandler(contact_day_entry, pattern=r"^admin_contact_day\|"),
        ],

        states={

            # =================================================
            # MANUAL LESSON
            # =================================================

            MANUAL_STUDENT: [

                CallbackQueryHandler(
                    manual_student_selected,
                    pattern=(
                        r"^admin_manual_student\|"
                    ),
                )
            ],

            MANUAL_DATE: [
                CallbackQueryHandler(manual_slot_selected,pattern=r"^admin_manual_slot\|"),
                CallbackQueryHandler(manual_dates_menu,pattern=r"^admin_manual_dates$"),
                CallbackQueryHandler(manual_day_selected,pattern=r"^admin_manual_day\|"),
                CallbackQueryHandler(manual_custom_time,pattern=r"^admin_manual_custom_time\|"),
                CallbackQueryHandler(manual_type_date,pattern=r"^admin_manual_type_date$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND,manual_date_handler),
            ],

            MANUAL_TIME: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    manual_time_handler,
                )
            ],

            MANUAL_DURATION: [

                CallbackQueryHandler(
                    manual_duration_selected,
                    pattern=(
                        r"^admin_manual_duration\|"
                    ),
                )
            ],

            MANUAL_PAYMENT_MODE: [

                CallbackQueryHandler(
                    manual_payment_selected,
                    pattern=(
                        r"^admin_manual_payment\|"
                    ),
                )
            ],


            # =================================================
            # PROMO
            # =================================================

            PROMO_CODE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_code_handler,
                )
            ],

            PROMO_TYPE: [

                CallbackQueryHandler(
                    promo_type_selected,
                    pattern=(
                        r"^admin_promo_type\|"
                    ),
                )
            ],

            PROMO_VALUE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_value_handler,
                )
            ],

            PROMO_MAX_USES: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_max_handler,
                )
            ],

            PROMO_USER_LIMIT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_user_limit_handler,
                )
            ],

            PROMO_EXPIRES: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_expires_handler,
                )
            ],

            # =================================================
            # PRICES
            # =================================================

            PRICE_DEFAULT_VALUE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    default_price_value_handler,
                )
            ],

            PRICE_STUDENT_VALUE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    student_price_value_handler,
                )
            ],

            # =================================================
            # STUDENT PROGRAMS
            # =================================================

            PROGRAM_SUBJECT: [

                CallbackQueryHandler(
                    program_subject_selected,
                    pattern=(
                        r"^admin_program_subject\|"
                    ),
                )
            ],

            PROGRAM_GOAL: [

                CallbackQueryHandler(
                    program_goal_selected,
                    pattern=(
                        r"^admin_program_goal\|"
                    ),
                )
            ],

            PROGRAM_PRICE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    program_price_value_handler,
                )
            ],

            BOARD_URL: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    board_url_handler,
                )
            ],

            LESSON_LINK: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    lesson_link_handler,
                )
            ],

            EXTRA_HW_TEXT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    extra_hw_text_handler,
                )
            ],

            EXTRA_HW_DEADLINE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    extra_hw_deadline_handler,
                )
            ],

            DELAY_CUSTOM_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    delay_custom_time_handler,
                )
            ],

            PAYMENT_METHOD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_method_title_handler)],
            PAYMENT_METHOD_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, payment_method_details_handler)],

            CONTACT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_text_handler)],
            CONTACT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_text_handler)],
            CONTACT_TELEGRAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_text_handler)],
            CONTACT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_text_handler)],
            CONTACT_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_text_handler)],
            CONTACT_DAY_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, contact_day_time_handler)],
        },

        fallbacks=[],

        allow_reentry=True,
    )


# ============================================================
# CALLBACK HANDLER
# ============================================================

def get_admin_callback_handler():

    return CallbackQueryHandler(

        admin_buttons,

        # admin_schedule намеренно НЕ включаем
        pattern=(
            r"^admin_main$"
            r"|^admin_contact$"
            r"|^admin_parents$"
            r"|^admin_parent\|"
            r"|^admin_payment_methods$"
            r"|^admin_paymethod"
            r"|^admin_student_block_"
            r"|^admin_student_unblock\|"
            r"|^admin_requests$"
            r"|^admin_request_"
            r"|^admin_today$"
            r"|^admin_lessons$"
            r"|^admin_cancel_lesson\|"
            r"|^admin_cancel_reason\|"
            r"|^admin_cancel_final\|"
            r"|^admin_lesson_"
            r"|^admin_homework"
            r"|^admin_students$"
            r"|^admin_students_grade\|"
            r"|^admin_student\|"
            r"|^admin_student_stats\|"
            r"|^admin_balance\|"
            r"|^admin_balance_add\|"
            r"|^admin_balance_remove\|"
            r"|^admin_student_price_reset\|"
            r"|^admin_student_delete_"
            r"|^admin_lesson_delay_menu\|"
            r"|^admin_lesson_delay_choose\|"
            r"|^admin_lesson_delay_send\|"
            r"|^admin_lesson_delay_followup\|"
            r"|^admin_overlap_delay\|"
            r"|^admin_overlap_finish_only\|"
            r"|^admin_overlap_force_start\|"
            r"|^admin_overlap_finish_start\|"
            r"|^admin_program\|"
            r"|^admin_program_price_reset\|"
            r"|^admin_program_primary\|"
            r"|^admin_program_stats\|"
            r"|^admin_program_disable_warn\|"
            r"|^admin_program_disable\|"
            r"|^admin_prices$"
            r"|^admin_price_default\|"
            r"|^admin_unpaid_lessons$"
            r"|^admin_statistics$"
            r"|^admin_statistics\|"
            r"|^admin_promos$"
            r"|^admin_promo\|"
            r"|^admin_promo_toggle\|"
            r"|^admin_promo_delete\|"
        ),
    )


# ============================================================
# COMMAND HANDLER
# ============================================================

def get_admin_command_handler():

    return CommandHandler(
        "admin",
        admin_command,
    )


# ============================================================
# END
# ============================================================
