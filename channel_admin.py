# ============================================================
# channel_admin.py
# Публикация свободных окон в Telegram-канал
# ============================================================

from datetime import (
    date,
    datetime,
    time,
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
    ChatMemberHandler,
    ContextTypes,
    filters,
)

import database
import admin


# ============================================================
# STATES
# ============================================================

CHANNEL_TARGET = 7000

ANNOUNCEMENT_TEXT = 7010
DAY_OFF_DATE = 7011
SICK_FROM_DATE = 7012
SICK_TO_DATE = 7013


# ============================================================
# SETTINGS KEYS
# ============================================================

SETTING_CHANNEL_ID = "free_slots_channel_id"
SETTING_CHANNEL_TITLE = "free_slots_channel_title"
SETTING_POST_ID = "free_slots_post_id"
SETTING_DURATION = "free_slots_duration"
SETTING_HORIZON = "free_slots_horizon"

SETTING_DISCOVERY_ENABLED = "free_slots_channel_discovery_enabled"
SETTING_CANDIDATE_CHANNEL_ID = "free_slots_candidate_channel_id"
SETTING_CANDIDATE_CHANNEL_TITLE = "free_slots_candidate_channel_title"


# ============================================================
# ACCESS
# ============================================================

def is_admin(
    update: Update
):

    return bool(
        update.effective_user
        and admin.is_admin(update)
    )


# ============================================================
# SETTINGS
# ============================================================

def get_duration():

    try:

        value = int(
            database.get_setting(
                SETTING_DURATION,
                "60",
            )
        )

    except Exception:

        value = 60

    if value not in {
        60,
        90,
        120,
    }:

        value = 60

    return value


def get_horizon_mode():

    value = database.get_setting(
        SETTING_HORIZON,
        "7",
    )

    if value not in {
        "tomorrow",
        "7",
        "14",
    }:

        value = "7"

    return value


def get_horizon_label():

    mode = get_horizon_mode()

    labels = {
        "tomorrow": "на завтра",
        "7": "на неделю",
        "14": "на 2 недели",
    }

    return labels[mode]


def get_channel_id():

    value = database.get_setting(
        SETTING_CHANNEL_ID
    )

    if not value:
        return None

    try:

        return int(value)

    except Exception:

        return value


def get_channel_title():

    return database.get_setting(
        SETTING_CHANNEL_TITLE,
        "не настроен",
    )



# ============================================================
# MAIN MENU
# ============================================================

def channel_menu():

    duration = get_duration()
    horizon_label = get_horizon_label()

    channel_id = get_channel_id()
    channel_title = get_channel_title()

    if channel_id:

        channel_line = (
            f"📍 Канал: {channel_title}"
        )

    else:

        channel_line = (
            "📍 Канал: не настроен"
        )

    text = (
        "📢 СВОБОДНЫЕ ОКНА\n\n"

        f"{channel_line}\n"
        f"⏱ Длительность слота: "
        f"{duration} минут\n"
        f"📆 Публикация: "
        f"{horizon_label}\n"
        "📊 Утренний отчёт по подпискам: 08:30\n"
        "🔕 В канал уведомления о входе/выходе не отправляются.\n\n"

        "Бот сформирует список реально "
        "свободного времени с учётом рабочего "
        "графика, выходных, занятых занятий "
        "и Google Calendar.\n\n"

        "Каждая публикация создаёт новое "
        "сообщение в канале.\n\n"

        "📣 Объявления, выходные и больничные "
        "здесь только публикуются в канал — "
        "они не удаляют, не отменяют и не "
        "переносят занятия в базе."
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "👀 Предпросмотр",
                callback_data=(
                    "channel_preview"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "📤 Опубликовать новым постом",
                callback_data=(
                    "channel_publish"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                f"⏱ Слот: {duration} мин",
                callback_data=(
                    "channel_duration"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                f"📆 Период: {horizon_label}",
                callback_data=(
                    "channel_horizon"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "💜 Подготовить пост с Аделией",
                callback_data="ac_channel_start",
            )
        ],

        [
            InlineKeyboardButton(
                "📣 Важное объявление",
                callback_data=(
                    "channel_announcement"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "🏖 Сообщить о выходном",
                callback_data=(
                    "channel_day_off"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "🤒 Сообщить о больничном",
                callback_data=(
                    "channel_sick_leave"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "📍 Настроить канал",
                callback_data=(
                    "channel_set"
                ),
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Админка",
                callback_data=(
                    "admin_main"
                ),
            )
        ],
    ])

    return text, keyboard


async def show_channel_menu(
    query
):

    text, keyboard = (
        channel_menu()
    )

    await query.edit_message_text(
        text,
        reply_markup=keyboard,
    )


# ============================================================
# BUILD FREE WINDOWS
# ============================================================

def build_free_windows_text():

    # Импортируем лениво, чтобы не получить
    # циклический import при запуске bot.py.
    import bot as tutor_bot

    duration = get_duration()
    horizon_mode = get_horizon_mode()

    today = date.today()

    if horizon_mode == "tomorrow":

        offsets = [1]

    elif horizon_mode == "14":

        offsets = list(
            range(0, 14)
        )

    else:

        offsets = list(
            range(0, 7)
        )

    lines = [
        "📅 СВОБОДНЫЕ ОКНА",
        "",
    ]

    total_slots = 0

    for offset in offsets:

        day = (
            today
            + timedelta(
                days=offset
            )
        )

        slots = tutor_bot.get_free_slots(
            day,
            duration,
        )

        if not slots:
            continue

        total_slots += len(
            slots
        )

        if offset == 0:
            day_title = "Сегодня"

        elif offset == 1:
            day_title = "Завтра"

        else:
            weekdays = {
                0: "Пн",
                1: "Вт",
                2: "Ср",
                3: "Чт",
                4: "Пт",
                5: "Сб",
                6: "Вс",
            }

            day_title = (
                f"{weekdays[day.weekday()]}, "
                f"{day.strftime('%d.%m')}"
            )

        times = [
            item.strftime(
                "%H:%M"
            )
            for item in slots
        ]

        # Чтобы пост не превращался в стену:
        # максимум 14 стартов на один день.
        visible = times[:14]

        line = (
            f"🗓 {day_title}\n"
            f"• "
            + " • ".join(
                visible
            )
        )

        if len(times) > len(visible):

            line += (
                f"\nещё +"
                f"{len(times) - len(visible)}"
                " окон"
            )

        lines.append(
            line
        )

        lines.append(
            ""
        )

    if total_slots == 0:

        lines.extend([
            "На выбранный период "
            "свободных окон пока нет.",
            "",
        ])

    lines.extend([
        f"⏱ Формат занятия: "
        f"{duration} минут",
        "",
        "Записаться можно через бота 👇",
    ])

    return "\n".join(
        lines
    )


# ============================================================
# PREVIEW
# ============================================================

async def preview(
    query
):

    try:

        text = (
            build_free_windows_text()
        )

    except Exception as error:

        await query.edit_message_text(
            "❌ Не удалось сформировать "
            "свободные окна.\n\n"
            f"{error}",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=(
                            "admin_free_windows"
                        ),
                    )
                ]
            ]),
        )

        return

    await query.edit_message_text(
        "👀 ПРЕДПРОСМОТР\n\n"
        + text,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "📤 Опубликовать",
                    callback_data=(
                        "channel_publish"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "🔄 Обновить предпросмотр",
                    callback_data=(
                        "channel_preview"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ],
        ]),
    )


# ============================================================
# PUBLISH
# ============================================================

async def publish(
    query,
    context: ContextTypes.DEFAULT_TYPE
):

    channel_id = get_channel_id()

    if not channel_id:

        await query.answer(
            "Сначала настройте канал.",
            show_alert=True,
        )

        return

    try:

        post_text = (
            build_free_windows_text()
        )

        me = await context.bot.get_me()

        bot_url = (
            f"https://t.me/{me.username}"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📅 Записаться",
                    url=bot_url,
                )
            ]
        ])

        # Каждый раз публикуем НОВОЕ сообщение.
        # Старые публикации не редактируем и не удаляем.
        message = (
            await context.bot.send_message(
                chat_id=channel_id,
                text=post_text,
                reply_markup=keyboard,
                disable_notification=True,
            )
        )

        database.set_setting(
            SETTING_POST_ID,
            message.message_id,
        )

    except Exception as error:

        await query.edit_message_text(
            "❌ Не удалось опубликовать.\n\n"

            f"{error}\n\n"

            "Проверьте, что бот добавлен "
            "администратором канала и имеет "
            "право публиковать сообщения.",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ Назад",
                        callback_data=(
                            "admin_free_windows"
                        ),
                    )
                ]
            ]),
        )

        return

    await query.edit_message_text(
        "✅ Новое сообщение со свободными "
        "окнами опубликовано в канал.",

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "👀 Предпросмотр",
                    callback_data=(
                        "channel_preview"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "📤 Опубликовать ещё раз",
                    callback_data=(
                        "channel_publish"
                    ),
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ В раздел",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ],
        ]),
    )


# ============================================================
# ОБЪЯВЛЕНИЯ В КАНАЛ
# ============================================================

def format_ru_date(
    value
):

    if isinstance(
        value,
        date,
    ):

        return value.strftime(
            "%d.%m.%Y"
        )

    try:

        return (
            datetime.strptime(
                str(value),
                "%Y-%m-%d"
            )
            .strftime(
                "%d.%m.%Y"
            )
        )

    except Exception:

        return str(value)


def parse_ru_date(
    value
):

    return (
        datetime.strptime(
            value.strip(),
            "%d.%m.%Y"
        )
        .date()
    )


def notice_preview_keyboard(sync_available=False):

    keyboard = []

    if sync_available:
        keyboard.append([
            InlineKeyboardButton(
                "📤 Опубликовать + перенести занятия",
                callback_data="channel_notice_publish_sync",
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "📢 Только опубликовать",
                callback_data="channel_notice_publish",
            )
        ])

    else:
        keyboard.append([
            InlineKeyboardButton(
                "📤 Опубликовать новым постом",
                callback_data="channel_notice_publish",
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❌ Отмена",
            callback_data="admin_free_windows",
        )
    ])

    return InlineKeyboardMarkup(keyboard)


async def show_notice_preview(
    message,
    context,
    notice_text
):

    context.user_data[
        "channel_notice_text"
    ] = notice_text

    await message.reply_text(
        "👀 ПРЕДПРОСМОТР\n\n"
        + notice_text
        + "\n\n"
        "ℹ️ Эта публикация не меняет "
        "расписание и статусы занятий.",

        reply_markup=notice_preview_keyboard(
            sync_available=bool(
                context.user_data.get("channel_absence_from")
                and context.user_data.get("channel_absence_to")
            )
        ),
    )


async def announcement_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    await query.edit_message_text(
        "📣 ВАЖНОЕ ОБЪЯВЛЕНИЕ\n\n"

        "Напишите текст, который нужно "
        "опубликовать в канале.\n\n"

        "Например:\n"
        "Завтра занятия начинаются "
        "только после 16:00."
    )

    return ANNOUNCEMENT_TEXT


async def announcement_text_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    raw = (
        update.message.text
        .strip()
    )

    if not raw:

        await update.message.reply_text(
            "❌ Текст не может быть пустым."
        )

        return ANNOUNCEMENT_TEXT

    notice_text = (
        "📣 ВАЖНОЕ ОБЪЯВЛЕНИЕ\n\n"
        + raw
    )

    await show_notice_preview(
        update.message,
        context,
        notice_text,
    )

    return (
        ConversationHandler.END
    )


async def day_off_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    await query.edit_message_text(
        "🏖 ОБЪЯВЛЕНИЕ О ВЫХОДНОМ\n\n"

        "Введите дату выходного.\n\n"

        "Формат:\n"
        "25.08.2026\n\n"

        "Важно: это только сообщение "
        "для канала. Существующие занятия "
        "в БД останутся без изменений."
    )

    return DAY_OFF_DATE


async def day_off_date_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        day = parse_ru_date(
            update.message.text
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверная дата.\n\n"
            "Введите в формате:"
            "\n25.08.2026"
        )

        return DAY_OFF_DATE

    context.user_data["channel_absence_from"] = day.isoformat()
    context.user_data["channel_absence_to"] = day.isoformat()
    context.user_data["channel_absence_reason"] = "DAY_OFF"

    notice_text = (
        "🏖 ВАЖНОЕ ОБЪЯВЛЕНИЕ\n\n"
        f"📅 {format_ru_date(day)} — выходной день.\n\n"
        "Занятия на этот день будут предложены к переносу."
    )

    await show_notice_preview(
        update.message,
        context,
        notice_text,
    )

    return (
        ConversationHandler.END
    )


async def sick_leave_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    await query.edit_message_text(
        "🤒 ОБЪЯВЛЕНИЕ О БОЛЬНИЧНОМ\n\n"

        "Введите первый день больничного.\n\n"

        "Формат:\n"
        "25.08.2026\n\n"

        "Это объявление само по себе "
        "не отменяет занятия в базе."
    )

    return SICK_FROM_DATE


async def sick_from_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        day_from = parse_ru_date(
            update.message.text
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверная дата.\n\n"
            "Например:\n25.08.2026"
        )

        return SICK_FROM_DATE

    context.user_data[
        "channel_sick_from"
    ] = day_from.isoformat()

    await update.message.reply_text(
        "Теперь введите последний день "
        "больничного.\n\n"

        "Например:\n"
        "28.08.2026"
    )

    return SICK_TO_DATE


async def sick_to_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    try:

        day_to = parse_ru_date(
            update.message.text
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Неверная дата.\n\n"
            "Например:\n28.08.2026"
        )

        return SICK_TO_DATE

    raw_from = context.user_data.get(
        "channel_sick_from"
    )

    if not raw_from:

        await update.message.reply_text(
            "❌ Первая дата потеряна. "
            "Начните заново."
        )

        return (
            ConversationHandler.END
        )

    day_from = date.fromisoformat(
        raw_from
    )

    if day_to < day_from:

        await update.message.reply_text(
            "❌ Последняя дата не может быть "
            "раньше первой.\n\n"

            "Введите последнюю дату ещё раз."
        )

        return SICK_TO_DATE

    if day_from == day_to:

        period_text = (
            format_ru_date(
                day_from
            )
        )

    else:

        period_text = (
            f"с {format_ru_date(day_from)} "
            f"по {format_ru_date(day_to)}"
        )

    context.user_data["channel_absence_from"] = day_from.isoformat()
    context.user_data["channel_absence_to"] = day_to.isoformat()
    context.user_data["channel_absence_reason"] = "SICK_LEAVE"

    notice_text = (
        "🤒 ВАЖНОЕ ОБЪЯВЛЕНИЕ\n\n"
        f"Я беру больничный {period_text}.\n\n"
        "Занятия в этот период будут предложены к переносу."
    )

    context.user_data.pop(
        "channel_sick_from",
        None,
    )

    await show_notice_preview(
        update.message,
        context,
        notice_text,
    )

    return (
        ConversationHandler.END
    )


async def publish_notice_and_sync(
    query,
    context: ContextTypes.DEFAULT_TYPE
):

    date_from = context.user_data.get("channel_absence_from")
    date_to = context.user_data.get("channel_absence_to")
    reason = context.user_data.get(
        "channel_absence_reason",
        "ABSENCE",
    )

    if not date_from or not date_to:
        await query.answer(
            "Период потерян. Создайте объявление заново.",
            show_alert=True,
        )
        return

    database.close_date_range(
        date_from,
        date_to,
        comment=reason,
    )

    lessons = database.get_lessons_in_date_range(
        date_from,
        date_to,
    )

    prepared = 0

    for lesson in lessons:

        try:

            database.prepare_lesson_for_forced_reschedule(
                lesson["id"],
                (
                    "ADMIN_SICKNESS_RESCHEDULE"
                    if reason == "SICK_LEAVE"
                    else "ADMIN_DAY_OFF_RESCHEDULE"
                ),
            )

            prepared += 1

            if lesson["telegram_id"]:
                await context.bot.send_message(
                    chat_id=lesson["telegram_id"],
                    text=(
                        "🔁 НУЖНО ПЕРЕНЕСТИ ЗАНЯТИЕ\n\n"
                        f"Исходное время: "
                        f"{lesson['start_time'][:10]} "
                        f"{lesson['start_time'][11:16]}\n\n"
                        "Выберите новое свободное время."
                    ),
                    reply_markup=InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📅 Выбрать новое время",
                                callback_data=(
                                    f"reschedule_free|{lesson['id']}"
                                ),
                            )
                        ]
                    ]),
                )

        except Exception as error:
            print(
                "CHANNEL RESCHEDULE PREP:",
                lesson["id"],
                repr(error),
            )

    await publish_notice(
        query,
        context,
    )

    try:
        await context.bot.send_message(
            chat_id=admin.ADMIN_ID,
            text=(
                "✅ Расписание синхронизировано.\n\n"
                f"Занятий поставлено на перенос: {prepared}"
            ),
        )
    except Exception:
        pass


async def publish_notice(
    query,
    context: ContextTypes.DEFAULT_TYPE
):

    channel_id = get_channel_id()

    if not channel_id:

        await query.answer(
            "Сначала настройте канал.",
            show_alert=True,
        )

        return

    notice_text = (
        context.user_data.get(
            "channel_notice_text"
        )
    )

    if not notice_text:

        await query.answer(
            "Текст объявления потерян. "
            "Создайте объявление заново.",
            show_alert=True,
        )

        return

    try:

        await context.bot.send_message(
            chat_id=channel_id,
            text=notice_text,
        )

    except Exception as error:

        await query.edit_message_text(
            "❌ Не удалось опубликовать "
            "объявление.\n\n"

            f"{error}",

            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "⬅️ В раздел",
                        callback_data=(
                            "admin_free_windows"
                        ),
                    )
                ]
            ]),
        )

        return

    context.user_data.pop(
        "channel_notice_text",
        None,
    )

    await query.edit_message_text(
        "✅ Объявление опубликовано "
        "новым сообщением.\n\n"

        "Расписание и существующие "
        "занятия в базе не изменялись.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 К публикациям",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# CHANNEL SETUP
# ============================================================

async def channel_set_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    # Включаем поиск приватного канала.
    # ВАЖНО: после этого НЕ оставляем ConversationHandler
    # в состоянии ожидания текста, иначе он будет перехватывать
    # ввод цен и любые другие сообщения администратора.
    database.set_setting(
        SETTING_DISCOVERY_ENABLED,
        "1",
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_ID
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE
    )

    await query.edit_message_text(
        "📍 НАСТРОЙКА КАНАЛА\n\n"

        "Для приватного канала:\n"
        "1. Добавьте «Аделия | TutorBot» администратором канала.\n"
        "2. Разрешите ему публиковать сообщения.\n"
        "3. Опубликуйте в канале любое новое сообщение, "
        "например «тест».\n\n"

        "Ничего пересылать не нужно — бот сам определит "
        "канал и пришлёт вам кнопку подключения.\n\n"

        "Если канал публичный или вы знаете его ID, "
        "можно ввести @username / -100... вручную.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✏️ Ввести @username / ID",
                    callback_data="channel_manual_set",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data="admin_free_windows",
                )
            ],
        ]),
    )

    return (
        ConversationHandler.END
    )


async def channel_manual_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        return (
            ConversationHandler.END
        )

    await query.answer()

    await query.edit_message_text(
        "✏️ ВВОД КАНАЛА ВРУЧНУЮ\n\n"

        "Отправьте одним сообщением:\n"
        "• @username публичного канала\n"
        "или\n"
        "• ID приватного канала вида -1001234567890\n\n"

        "Для отмены просто вернитесь в /admin."
    )

    return CHANNEL_TARGET


async def channel_target_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    raw = (
        update.message.text
        .strip()
    )

    target = raw

    if raw.startswith("-100"):

        try:

            target = int(
                raw
            )

        except ValueError:

            pass

    elif (
        not raw.startswith("@")
    ):

        target = (
            "@"
            + raw
        )

    try:

        chat = (
            await context.bot.get_chat(
                target
            )
        )

        me = (
            await context.bot.get_me()
        )

        member = (
            await context.bot.get_chat_member(
                chat.id,
                me.id,
            )
        )

        if member.status not in {
            "administrator",
            "creator",
        }:

            await update.message.reply_text(
                "❌ Бот найден в канале, "
                "но не является администратором.\n\n"

                "Добавьте его в администраторы "
                "и отправьте канал ещё раз."
            )

            return CHANNEL_TARGET

    except Exception as error:

        await update.message.reply_text(
            "❌ Не удалось получить доступ "
            "к этому каналу.\n\n"

            "Проверьте @username/ID и убедитесь, "
            "что бот добавлен администратором.\n\n"

            f"Техническая ошибка: {error}"
        )

        return CHANNEL_TARGET

    database.set_setting(
        SETTING_CHANNEL_ID,
        chat.id,
    )

    title = (
        getattr(
            chat,
            "title",
            None
        )
        or getattr(
            chat,
            "username",
            None
        )
        or str(chat.id)
    )

    database.set_setting(
        SETTING_CHANNEL_TITLE,
        title,
    )

    database.set_setting(
        SETTING_DISCOVERY_ENABLED,
        "0",
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_ID
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE
    )

    # Старый message_id мог относиться
    # к другому каналу.
    database.delete_setting(
        SETTING_POST_ID
    )

    await update.message.reply_text(
        "✅ КАНАЛ ПОДКЛЮЧЕН\n\n"

        f"📢 {title}\n\n"

        "Теперь можно сделать предпросмотр "
        "и опубликовать свободные окна.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 Свободные окна",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ]
        ]),
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# ПРИВАТНЫЙ КАНАЛ — АВТООПРЕДЕЛЕНИЕ ID
# ============================================================

async def detect_channel_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    # Этот обработчик получает новые посты из каналов,
    # где бот присутствует.
    message = (
        update.channel_post
        if update.channel_post
        else None
    )

    if message is None:
        return

    if (
        database.get_setting(
            SETTING_DISCOVERY_ENABLED,
            "0",
        )
        != "1"
    ):
        return

    chat = message.chat

    # Проверяем, что сам бот действительно администратор
    # именно этого канала.
    try:

        me = await context.bot.get_me()

        member = (
            await context.bot.get_chat_member(
                chat.id,
                me.id,
            )
        )

        if member.status not in {
            "administrator",
            "creator",
        }:
            return

    except Exception as error:

        print(
            "CHANNEL DISCOVERY MEMBER CHECK:",
            repr(error),
        )

        return

    title = (
        getattr(
            chat,
            "title",
            None
        )
        or getattr(
            chat,
            "username",
            None
        )
        or str(chat.id)
    )

    database.set_setting(
        SETTING_CANDIDATE_CHANNEL_ID,
        chat.id,
    )

    database.set_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE,
        title,
    )

    try:

        await context.bot.send_message(

            chat_id=admin.ADMIN_ID,

            text=(
                "📢 НАЙДЕН КАНАЛ\n\n"

                f"Название: {title}\n"
                f"ID: {chat.id}\n\n"

                "Подключить этот канал "
                "для публикации свободных окон?"
            ),

            reply_markup=InlineKeyboardMarkup([

                [
                    InlineKeyboardButton(
                        "✅ Подключить этот канал",
                        callback_data=(
                            "channel_accept_candidate"
                        ),
                    )
                ],

                [
                    InlineKeyboardButton(
                        "❌ Не этот канал",
                        callback_data=(
                            "channel_reject_candidate"
                        ),
                    )
                ],
            ]),
        )

    except Exception as error:

        print(
            "CHANNEL DISCOVERY ADMIN NOTIFY:",
            repr(error),
        )


async def accept_candidate_channel(
    query
):

    channel_id = database.get_setting(
        SETTING_CANDIDATE_CHANNEL_ID
    )

    title = database.get_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE,
        "Канал",
    )

    if not channel_id:

        await query.answer(
            "Канал уже не найден. "
            "Запустите настройку ещё раз.",
            show_alert=True,
        )

        return

    database.set_setting(
        SETTING_CHANNEL_ID,
        channel_id,
    )

    database.set_setting(
        SETTING_CHANNEL_TITLE,
        title,
    )

    database.set_setting(
        SETTING_DISCOVERY_ENABLED,
        "0",
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_ID
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE
    )

    # Чтобы случайно не ссылаться на пост
    # из предыдущего канала.
    database.delete_setting(
        SETTING_POST_ID
    )

    await query.edit_message_text(
        "✅ КАНАЛ ПОДКЛЮЧЕН\n\n"

        f"📢 {title}\n"
        f"ID: {channel_id}\n\n"

        "Теперь можно публиковать "
        "свободные окна.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📢 Свободные окна",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ]
        ]),
    )


async def reject_candidate_channel(
    query
):

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_ID
    )

    database.delete_setting(
        SETTING_CANDIDATE_CHANNEL_TITLE
    )

    await query.edit_message_text(
        "Хорошо, этот канал не подключаю.\n\n"

        "Режим поиска остаётся включён. "
        "Опубликуйте новое сообщение "
        "в нужном канале.",

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⬅️ В настройки",
                    callback_data=(
                        "admin_free_windows"
                    ),
                )
            ]
        ]),
    )


# ============================================================
# CALLBACK ROUTER
# ============================================================

async def channel_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not is_admin(
        update
    ):

        await query.answer(
            "Нет доступа.",
            show_alert=True,
        )

        return

    await query.answer()

    data = query.data


    if (
        data
        == "admin_free_windows"
    ):

        await show_channel_menu(
            query
        )

        return


    if (
        data
        == "channel_accept_candidate"
    ):

        await accept_candidate_channel(
            query
        )

        return


    if (
        data
        == "channel_reject_candidate"
    ):

        await reject_candidate_channel(
            query
        )

        return


    if (
        data
        == "channel_notice_publish_sync"
    ):

        await publish_notice_and_sync(
            query,
            context,
        )

        return


    if (
        data
        == "channel_notice_publish"
    ):

        await publish_notice(
            query,
            context,
        )

        return


    if (
        data
        == "channel_preview"
    ):

        await preview(
            query
        )

        return


    if (
        data
        == "channel_publish"
    ):

        await publish(
            query,
            context,
        )

        return



    if (
        data
        == "channel_duration"
    ):

        current = get_duration()

        values = [
            60,
            90,
            120,
        ]

        index = values.index(
            current
        )

        new_value = values[
            (
                index + 1
            )
            % len(values)
        ]

        database.set_setting(
            SETTING_DURATION,
            new_value,
        )

        await show_channel_menu(
            query
        )

        return


    if (
        data
        == "channel_horizon"
    ):

        current = get_horizon_mode()

        values = [
            "tomorrow",
            "7",
            "14",
        ]

        index = values.index(
            current
        )

        new_value = values[
            (
                index + 1
            )
            % len(values)
        ]

        database.set_setting(
            SETTING_HORIZON,
            new_value,
        )

        await show_channel_menu(
            query
        )

        return


# ============================================================
# CHANNEL MEMBERS / DAILY STATS
# ============================================================

CHANNEL_REPORT_TIMEZONE = ZoneInfo("Europe/Samara")
CHANNEL_REPORT_TIME = time(hour=8, minute=30, tzinfo=CHANNEL_REPORT_TIMEZONE)

def _channel_tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try: return ZoneInfo(name)
    except Exception: return ZoneInfo("Europe/Samara")


def _is_member_state(member):
    status = getattr(member, "status", None)
    if status in {"member", "administrator", "creator"}:
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


def _channel_member_event_type(changed):
    was_member = _is_member_state(changed.old_chat_member)
    is_member = _is_member_state(changed.new_chat_member)

    if not was_member and is_member:
        return "JOIN"
    if was_member and not is_member:
        return "LEAVE"
    return None


async def channel_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track joins/leaves silently. Nothing is ever posted to the channel."""

    changed = update.chat_member
    if changed is None:
        return

    configured = get_channel_id()
    if configured is None or str(changed.chat.id) != str(configured):
        return

    event_type = _channel_member_event_type(changed)
    if event_type is None:
        return

    user = changed.new_chat_member.user
    if not user or getattr(user, "is_bot", False):
        return

    try:
        happened_at = datetime.now(_channel_tz()).replace(tzinfo=None).isoformat(timespec="seconds")
        database.record_channel_member_event(
            channel_id=changed.chat.id,
            telegram_id=getattr(user, "id", None),
            username=getattr(user, "username", None),
            full_name=(getattr(user, "full_name", None) or getattr(user, "first_name", None)),
            event_type=event_type,
            happened_at=happened_at,
            telegram_update_id=getattr(update, "update_id", None),
        )
    except Exception as error:
        print("CHANNEL MEMBER STATS ERROR:", repr(error))


def _previous_day_range(now=None):
    now = now or datetime.now(_channel_tz())
    report_day = now.date() - timedelta(days=1)
    start = datetime.combine(report_day, time.min)
    end = start + timedelta(days=1)
    return report_day, start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def _format_channel_daily_report(report_day, joined, left):
    net = int(joined) - int(left)
    if net > 0:
        net_text = f"+{net}"
        net_emoji = "📈"
    elif net < 0:
        net_text = str(net)
        net_emoji = "📉"
    else:
        net_text = "0"
        net_emoji = "➖"

    return (
        "💜 АДЕЛИЯ • КАНАЛ\n\n"
        f"Доброе утро. Я посчитала изменения за {report_day.strftime('%d.%m.%Y')}.\n\n"
        f"👋 Пришло: {int(joined)}\n"
        f"🚪 Ушло: {int(left)}\n"
        f"{net_emoji} Изменение: {net_text}"
    )


async def channel_daily_stats_job(context: ContextTypes.DEFAULT_TYPE):
    if str(database.get_setting("notify_channel", "1")).lower() in ("0","false","off","no"):
        return
    channel_id = get_channel_id()
    if channel_id is None:
        return

    report_day, start_at, end_at = _previous_day_range()

    try:
        stats = database.get_channel_member_stats(
            channel_id=channel_id,
            start_at=start_at,
            end_at=end_at,
        )
        text = _format_channel_daily_report(
            report_day=report_day,
            joined=stats.get("JOIN", 0),
            left=stats.get("LEAVE", 0),
        )
        await context.bot.send_message(chat_id=admin.ADMIN_ID, text=text)
        database.log_automation_delivery("channel_daily", "OK", "ADMIN", admin.ADMIN_ID)
    except Exception as error:
        database.log_automation_delivery("channel_daily", "ERROR", "ADMIN", admin.ADMIN_ID, repr(error))
        print("CHANNEL DAILY STATS ERROR:", repr(error))


async def channel_daily_dispatcher(context: ContextTypes.DEFAULT_TYPE):
    if str(database.get_setting("notify_channel", "1")).lower() in ("0","false","off","no"):
        return
    now = datetime.now(_channel_tz())
    target = database.get_setting("channel_summary_time", "08:30") or "08:30"
    if now.strftime("%H:%M") != target:
        return
    day = now.date().isoformat()
    if (database.get_setting("channel_summary_last_day", "") or "") == day:
        return
    await channel_daily_stats_job(context)
    database.set_setting("channel_summary_last_day", day)

def register_jobs(application):
    if not application.job_queue:
        return
    for job in application.job_queue.get_jobs_by_name("channel_daily_stats"):
        job.schedule_removal()
    application.job_queue.run_repeating(channel_daily_dispatcher, interval=60, first=25, name="channel_daily_stats")


# ============================================================
# HANDLERS
# ============================================================

def get_channel_member_handler():
    return ChatMemberHandler(channel_member_update, ChatMemberHandler.CHAT_MEMBER)


def get_channel_conversation_handler():

    return ConversationHandler(

        entry_points=[

            CallbackQueryHandler(
                channel_set_entry,
                pattern=(
                    r"^channel_set$"
                ),
            ),

            CallbackQueryHandler(
                channel_manual_entry,
                pattern=(
                    r"^channel_manual_set$"
                ),
            ),

            CallbackQueryHandler(
                announcement_entry,
                pattern=(
                    r"^channel_announcement$"
                ),
            ),

            CallbackQueryHandler(
                day_off_entry,
                pattern=(
                    r"^channel_day_off$"
                ),
            ),

            CallbackQueryHandler(
                sick_leave_entry,
                pattern=(
                    r"^channel_sick_leave$"
                ),
            ),
        ],

        states={

            CHANNEL_TARGET: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    channel_target_handler,
                )
            ],

            ANNOUNCEMENT_TEXT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    announcement_text_handler,
                )
            ],

            DAY_OFF_DATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    day_off_date_handler,
                )
            ],

            SICK_FROM_DATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    sick_from_handler,
                )
            ],

            SICK_TO_DATE: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    sick_to_handler,
                )
            ],
        },

        fallbacks=[],

        allow_reentry=True,
    )


def get_channel_callback_handler():

    return CallbackQueryHandler(

        channel_buttons,

        pattern=(
            r"^admin_free_windows$"
            r"|^channel_preview$"
            r"|^channel_publish$"
            r"|^channel_duration$"
            r"|^channel_horizon$"
            r"|^channel_notice_publish$"
            r"|^channel_notice_publish_sync$"
            r"|^channel_accept_candidate$"
            r"|^channel_reject_candidate$"
        ),
    )


def get_channel_post_handler():

    return MessageHandler(
        filters.UpdateType.CHANNEL_POST,
        detect_channel_post,
    )
