from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import database
from core import test_lab as core_test_lab
import admin
from core import minute_balance


# ============================================================
# РЕКВИЗИТЫ
# ============================================================

PAYMENT_DETAILS = (
    "💳 Реквизиты для оплаты\n\n"
    "🏦 Банк: СБЕР\n"
    "📱 Перевод по номеру телефона:\n"
    "+7-917-969-46-13\n\n"
    "👤 Получатель: Николай С.\n\n"
    "После перевода отправьте мне фото, скриншот или PDF чека — я передам его на проверку."
)


def ensure_payment_methods():
    """Keep the legacy requisites as the first/default configurable method."""
    return database.ensure_payment_method(
        "СБЕР • по номеру телефона",
        PAYMENT_DETAILS,
    )


def payment_method_text(method_id=None):
    ensure_payment_methods()
    method = database.get_payment_method(method_id) if method_id else database.get_default_payment_method()
    if method is None or not int(method["active"] or 0):
        method = database.get_default_payment_method()
    if method is None:
        return PAYMENT_DETAILS
    details = str(method["details"] or "").strip()
    title = str(method["title"] or "Способ оплаты").strip()
    # Старый основной способ уже содержит собственный заголовок.
    if details.startswith("💳 Реквизиты для оплаты"):
        return details
    return f"💳 {title}\n\n{details}"


# ============================================================
# СОСТОЯНИЯ
# ============================================================

WAIT_CUSTOM_COUNT = 500
WAIT_PROMO = 501
WAIT_RECEIPT = 502
WAIT_LESSON_PROMO = 503


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


PAYMENT_STATUS_NAMES = {
    "REVERSED": "↩ Подтверждение отменено",
    "WAITING": "⏳ Ожидает оплаты",
    "RECEIPT_SENT": "🧾 Чек проверяется",
    "PAID": "✅ Оплачено",
    "REJECTED": "❌ Отклонено",
    "CANCELLED": "🚫 Отменено",
}


LESSON_PAYMENT_STATUS_NAMES = {
    "UNPAID": "❌ Не оплачено",
    "AWAITING_PAYMENT": "💳 Ожидает оплаты",
    "RESERVED_BALANCE": "🎟 Зарезервировано с баланса",
    "PAID": "✅ Оплачено",
    "FREE": "🎁 Бесплатно",
    "REFUNDED": "↩️ Возвращено",
    "UNPAID_CANCELLED": "❌ Отменено из-за неоплаты",
    "TRANSFERRED": "🔁 Перенесено",
}


# ============================================================
# ДЕНЬГИ
# ============================================================

def money(value):

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


# ============================================================
# УЧЕНИК
# ============================================================


def payment_minutes_label(payment):
    """Human-readable package amount for both migrated and legacy payments."""
    keys = payment.keys() if hasattr(payment, "keys") else []
    minutes = int((payment["minutes_total"] if "minutes_total" in keys else 0) or 0)
    base = int((payment["base_duration_minutes"] if "base_duration_minutes" in keys else 0) or 0)
    count = int((payment["lessons_count"] if "lessons_count" in keys else 0) or 0)
    if minutes <= 0 and count > 0:
        base = base or 60
        minutes = count * base
    if count > 0 and base > 0:
        return f"{minutes} мин (≈ {count} × {base} мин)"
    return f"{minutes} мин"

def get_user_from_telegram(
    telegram_id
):

    return (
        database
        .get_user_by_telegram_id(
            telegram_id
        )
    )


# ============================================================
# ПОСТОЯННОЕ РАСПИСАНИЕ
# ============================================================

def get_regular_schedule(
    user_id
):

    schedules = (
        database
        .get_regular_schedules(
            user_id=user_id,
            approved_only=True
        )
    )

    if not schedules:
        return None

    return schedules[0]


def has_regular_schedule(
    user_id
):

    return (
        get_regular_schedule(
            user_id
        )
        is not None
    )


# ============================================================
# ДЛИТЕЛЬНОСТЬ ЗАНЯТИЯ
# ============================================================

def get_lesson_duration(user):
    # Prefer the primary active programme's individual default duration.
    try:
        programs=database.get_student_programs(user["id"],active_only=True,approved_only=True)
        primary=next((p for p in programs if p["is_primary"]), programs[0] if programs else None)
        if primary is not None:
            return int(minute_balance.get_program_duration(primary["id"]))
    except Exception:
        pass
    return minute_balance.default_duration_for_goal(user["study_goal"])


# ============================================================
# ЦЕНА ОДНОГО ЗАНЯТИЯ
# ============================================================

def get_price_per_lesson(
    user
):

    hourly_rate = (
        database
        .get_student_rate(
            user["id"]
        )
    )

    duration = (
        get_lesson_duration(
            user
        )
    )

    price = (
        database
        .calculate_lesson_price(
            hourly_rate,
            duration
        )
    )

    return {
        "hourly_rate":
            hourly_rate,

        "duration":
            duration,

        "price":
            price,
    }


# ============================================================
# БАЛАНС
# ============================================================

def get_balance_breakdown(user):
    try:
        programs=database.get_student_programs(user["id"],active_only=True,approved_only=True)
        primary=next((p for p in programs if p["is_primary"]), programs[0] if programs else None)
        rate=minute_balance.effective_hourly_rate(primary["id"]) if primary else int(database.get_student_rate(user["id"]))
    except Exception:
        rate=None
    return minute_balance.get_balance(user["id"],hourly_rate=rate)


def get_remaining_lessons(user):
    # Legacy name retained; value is now minutes.
    return get_balance_breakdown(user)["total"]


# ============================================================
# НОМИНАЛЫ ДЛЯ ПОКУПКИ
# ============================================================

def get_purchase_nominals(user):
    """Purchase choices by programme. Balance itself is stored in minutes by hourly tariff."""
    minute_balance.ensure_schema()
    programs = database.get_student_programs(
        user["id"], active_only=True, approved_only=True
    )
    result = {}
    for program in programs:
        rate = int(database.get_program_rate_info(program["id"])["effective_rate"])
        duration = int(minute_balance.get_program_duration(program["id"]))
        base_price = int(round(rate * duration / 60))
        result[int(program["id"])] = {
            "program_id": int(program["id"]),
            "study_goal": program["study_goal"],
            "subject": program["subject"],
            "hourly_rate": rate,
            "duration": duration,
            "nominal": base_price,
            "programs": [(program["study_goal"], program["subject"])],
        }
    if not result:
        duration = minute_balance.default_duration_for_goal(user["study_goal"])
        hourly = int(database.get_student_rate(user["id"]))
        result[0] = {
            "program_id": None, "study_goal": user["study_goal"],
            "subject": user["main_subject"], "hourly_rate": hourly,
            "duration": duration, "nominal": int(round(hourly*duration/60)),
            "programs": [(user["study_goal"], user["main_subject"])],
        }
    return result


def nominal_programs_text(item):
    return ", ".join(
        f"{GOAL_NAMES.get(g,g)} — {SUBJECT_NAMES.get(s,s)}"
        for g,s in item.get("programs",[])
    )


def nominal_selection_keyboard(user, mode):
    keyboard=[]
    for key,item in get_purchase_nominals(user).items():
        title = nominal_programs_text(item)
        keyboard.append([InlineKeyboardButton(
            f"🎟 {title} • {money(item['hourly_rate'])}/60 мин • {item['duration']} мин",
            callback_data=f"payment_nominal|{key}|{mode}",
        )])
    keyboard.append([InlineKeyboardButton("⬅️ К оплате",callback_data="payments")])
    return InlineKeyboardMarkup(keyboard)


def set_selected_nominal(context, user, selection_key):
    options=get_purchase_nominals(user)
    item=options.get(int(selection_key))
    if item is None:
        raise ValueError("Этот тариф больше недоступен. Открой раздел оплаты заново — я покажу актуальные варианты.")
    context.user_data["payment_selection_key"] = int(selection_key)
    context.user_data["payment_nominal"] = int(item["nominal"])  # legacy/base-lesson price
    context.user_data["payment_program_id"] = item.get("program_id")
    context.user_data["payment_study_goal"] = item["study_goal"]
    context.user_data["payment_subject"] = item["subject"]
    context.user_data["payment_nominal_programs"] = nominal_programs_text(item)
    context.user_data["payment_hourly_rate"] = int(item["hourly_rate"])
    context.user_data["payment_base_duration"] = int(item["duration"])
    return item


def clear_payment_selection(context):
    for key in (
        "payment_selection_key","payment_nominal","payment_program_id",
        "payment_study_goal","payment_subject","payment_nominal_programs",
        "payment_hourly_rate","payment_base_duration",
    ):
        context.user_data.pop(key,None)


# ============================================================
# ОПЛАТА КОНКРЕТНОГО НАЗНАЧЕННОГО ЗАНЯТИЯ
# ============================================================

def get_lesson_for_payment(
    lesson_id,
    user_id
):

    lesson = database.get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson["user_id"] != user_id:

        raise PermissionError(
            "Это занятие другого ученика."
        )

    if lesson["lesson_status"] != "CONFIRMED":

        raise ValueError(
            "Сейчас я не могу принять оплату за это занятие."
        )

    if lesson["payment_status"] == "PAID":

        raise ValueError(
            "Занятие уже оплачено."
        )

    if lesson["payment_status"] != "AWAITING_PAYMENT":

        raise ValueError(
            "Для этого занятия отдельная оплата не нужна 💜"
        )

    return lesson


def build_lesson_payment_text(
    lesson,
    promo_code=None
):

    amount = int(
        lesson["price"]
    )

    promo = None
    promo_discount = 0

    if promo_code:

        validation = database.validate_promo_code(
            promo_code,
            lesson["user_id"]
        )

        if not validation["valid"]:

            raise ValueError(
                validation["reason"]
            )

        promo = validation["promo"]

        promo_discount = (
            database.calculate_promo_discount(
                amount,
                promo
            )
        )

    final_total = max(
        amount - promo_discount,
        0
    )

    text = (
        "💳 Оплата занятия\n\n"

        f"📅 {lesson['start_time'][:10]} "
        f"в {lesson['start_time'][11:16]}\n"

        f"📚 "
        f"{SUBJECT_NAMES.get(lesson['subject'], lesson['subject'])}\n"

        f"⏱ "
        f"{lesson['duration_minutes']} минут\n\n"

        f"💰 Стоимость: "
        f"{money(amount)}\n"
    )

    if promo is not None:

        text += (
            f"🎁 Промокод: "
            f"{promo['code']}\n"

            f"💸 Скидка: −"
            f"{money(promo_discount)}\n"
        )

    text += (
        "\n🔥 К ОПЛАТЕ: "
        f"{money(final_total)}"
    )

    return text


def lesson_payment_keyboard(
    lesson_id,
    promo_applied=False
):

    keyboard = []

    if promo_applied:

        keyboard.append([
            InlineKeyboardButton(
                "❌ Убрать промокод",
                callback_data=(
                    f"payment_lesson_remove_promo|"
                    f"{lesson_id}"
                )
            )
        ])

    else:

        keyboard.append([
            InlineKeyboardButton(
                "🎁 Ввести промокод",
                callback_data=(
                    f"payment_lesson_promo|"
                    f"{lesson_id}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ Перейти к оплате",
            callback_data=(
                f"payment_lesson_confirm|"
                f"{lesson_id}"
            )
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Назад",
            callback_data="profile"
        )
    ])

    return InlineKeyboardMarkup(
        keyboard
    )


# ============================================================
# МЕНЮ ОПЛАТЫ
# ============================================================

def payment_menu():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "💳 Оплатить 1 занятие",
                callback_data=(
                    "payment_single"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🎟 Абонемент",
                callback_data=(
                    "payment_subscription"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "📊 История оплат",
                callback_data=(
                    "payment_history"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ Главное меню",
                callback_data="main"
            )
        ],
    ])


# ============================================================
# АБОНЕМЕНТЫ
# ============================================================

def subscription_menu(base_duration=60, program_id=None):
    base_duration=int(base_duration or 60)
    def discount_for(count):
        if program_id is not None:
            try:
                from final_features.tariffs import package_quote
                return int(package_quote(int(program_id),int(count))["discount_percent"])
            except Exception:
                pass
        return int(database.calculate_package_discount_percent(int(count)))
    def label(count):
        minutes=count*base_duration; disc=discount_for(count)
        return f"{count} занятий • {minutes} мин" + (f" • −{disc}%" if disc else "")
    counts=(2,3,4,5,6,8,10)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label(2),callback_data="paycount|2"), InlineKeyboardButton(label(3),callback_data="paycount|3")],
        [InlineKeyboardButton(label(4),callback_data="paycount|4"), InlineKeyboardButton(label(5),callback_data="paycount|5")],
        [InlineKeyboardButton(label(6),callback_data="paycount|6"), InlineKeyboardButton(label(8),callback_data="paycount|8")],
        [InlineKeyboardButton(label(10),callback_data="paycount|10")],
        [InlineKeyboardButton("✏️ Другое количество",callback_data="paycount_custom")],
        [InlineKeyboardButton("⬅️ Назад",callback_data="payments")],
    ])


# ============================================================
# РАСЧЁТ
# ============================================================

def build_calculation(
    user,
    lessons_count,
    promo_code=None,
    price_per_lesson=None,
    hourly_rate=None,
    base_duration=None,
    program_id=None
):

    lessons_count = int(
        lessons_count
    )

    if price_per_lesson is None:
        price_info = get_price_per_lesson(user)
    else:
        # Selected programme metadata is passed separately by callers when available;
        # infer safely for legacy calls.
        duration = minute_balance.default_duration_for_goal(user["study_goal"])
        price_info = {
            "hourly_rate": round(int(price_per_lesson) * 60 / max(duration,1)),
            "duration": duration,
            "price": int(price_per_lesson),
        }

    if base_duration is not None:
        price_info["duration"] = int(base_duration)
    if hourly_rate is not None:
        price_info["hourly_rate"] = int(hourly_rate)
        price_info["price"] = int(round(int(hourly_rate) * int(price_info["duration"] or 60) / 60))

    if program_id is not None:
        try:
            from final_features.tariffs import package_quote
            _q = package_quote(int(program_id), lessons_count)
            package = {
                "lessons_count": lessons_count,
                "subtotal": int(_q["subtotal"]),
                "discount_percent": int(_q["discount_percent"]),
                "discount_amount": int(_q["subtotal"] - _q["total"]),
                "total": int(_q["total"]),
            }
        except Exception:
            package = database.calculate_package(price_info["price"], lessons_count)
    else:
        package = database.calculate_package(price_info["price"], lessons_count)

    promo = None
    promo_discount = 0

    if promo_code:

        validation = (
            database
            .validate_promo_code(

                promo_code,
                user["id"]
            )
        )

        if not validation[
            "valid"
        ]:

            raise ValueError(
                validation[
                    "reason"
                ]
            )

        promo = (
            validation[
                "promo"
            ]
        )

        promo_discount = (
            database
            .calculate_promo_discount(

                package["total"],
                promo
            )
        )

    final_total = (
        package["total"]
        - promo_discount
    )

    final_total = max(
        final_total,
        0
    )

    return {

        "price_info":
            price_info,

        "package":
            package,

        "promo":
            promo,

        "promo_discount":
            promo_discount,

        "final_total":
            final_total,
    }


# ============================================================
# ТЕКСТ РАСЧЁТА
# ============================================================

def build_calculation_text(
    user,
    lessons_count,
    promo_code=None,
    price_per_lesson=None,
    programs_text=None,
    hourly_rate=None,
    base_duration=None,
    program_id=None
):

    result = (
        build_calculation(

            user,
            lessons_count,
            promo_code,
            price_per_lesson=price_per_lesson,
            hourly_rate=hourly_rate,
            base_duration=base_duration,
            program_id=program_id
        )
    )

    price_info = (
        result[
            "price_info"
        ]
    )

    package = (
        result[
            "package"
        ]
    )

    promo = (
        result[
            "promo"
        ]
    )

    text = (
        "💳 Я рассчитала оплату\n\n"

        f"💰 Тариф: {money(int(price_info.get('hourly_rate') or 0))} / 60 мин\n"
    )

    if programs_text:
        text += f"📚 Можно использовать: {programs_text}\n"

    if price_info.get("duration"):
        text += f"⏱ Основное занятие: {price_info['duration']} минут\n"

    text += (
        "\n"

        f"🎟 Эквивалент: {lessons_count} занятий × {price_info.get('duration') or 60} мин\n"
        f"⏱ Всего в абонементе: {lessons_count * int(price_info.get('duration') or 60)} минут\n"

        f"Без скидки: "
        f"{money(package['subtotal'])}\n"
    )

    if (
        package[
            "discount_percent"
        ] > 0
    ):

        text += (
            f"🎁 Скидка за количество: "
            f"{package['discount_percent']}%\n"

            f"💸 Экономия: −"
            f"{money(package['discount_amount'])}\n"
        )

    else:

        text += (
            "🎁 Скидка за количество: 0%\n"
        )

    if promo is not None:

        if (
            promo[
                "discount_type"
            ]
            == "PERCENT"
        ):

            promo_value = (
                f"{promo['discount_value']}%"
            )

        else:

            promo_value = (
                money(
                    promo[
                        "discount_value"
                    ]
                )
            )

        text += (
            "\n🎁 ПРОМОКОД\n"

            f"Код: "
            f"{promo['code']}\n"

            f"Скидка: "
            f"{promo_value}\n"

            f"Экономия: −"
            f"{money(result['promo_discount'])}\n"
        )

    text += (
        "\n🔥 ИТОГО: "
        f"{money(result['final_total'])}"
    )

    return (
        text,
        result
    )


# ============================================================
# КНОПКИ РАСЧЁТА
# ============================================================

def calculation_keyboard(
    lessons_count,
    promo_applied=False
):

    keyboard = []

    if promo_applied:

        keyboard.append([
            InlineKeyboardButton(
                "❌ Убрать промокод",

                callback_data=(
                    f"payment_remove_promo|"
                    f"{lessons_count}"
                )
            )
        ])

    else:

        keyboard.append([
            InlineKeyboardButton(
                "🎁 Ввести промокод",

                callback_data=(
                    f"payment_promo|"
                    f"{lessons_count}"
                )
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "✅ Перейти к оплате",

            callback_data=(
                f"payment_confirm|"
                f"{lessons_count}"
            )
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "⬅️ Изменить количество",

            callback_data=(
                "payment_subscription"
                if lessons_count > 1
                else "payments"
            )
        )
    ])

    return (
        InlineKeyboardMarkup(
            keyboard
        )
    )


# ============================================================
# ПОКАЗ РАСЧЁТА
# ============================================================

async def show_calculation(
    query,
    context,
    user,
    lessons_count
):

    promo_code = (
        context.user_data.get(
            "payment_promo_code"
        )
    )

    try:

        text, result = (
            build_calculation_text(

                user,
                lessons_count,
                promo_code,
                price_per_lesson=context.user_data.get("payment_nominal"),
                programs_text=context.user_data.get("payment_nominal_programs"),
                hourly_rate=context.user_data.get("payment_hourly_rate"),
                base_duration=context.user_data.get("payment_base_duration"),
                program_id=context.user_data.get("payment_program_id"),
            )
        )

    except Exception as error:

        context.user_data.pop(
            "payment_promo_code",
            None
        )

        await query.edit_message_text(
            f"❌ {error}",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ К оплате",
                            callback_data="payments"
                        )
                    ]
                ])
            )
        )

        return

    context.user_data[
        "payment_lessons_count"
    ] = lessons_count

    await query.edit_message_text(
        text,

        reply_markup=(
            calculation_keyboard(

                lessons_count,

                promo_applied=(
                    result["promo"]
                    is not None
                )
            )
        )
    )


# ============================================================
# ОЖИДАЮЩИЙ ПЛАТЁЖ
# ============================================================

def get_waiting_payment(
    user_id
):

    conn = (
        database.connect()
    )

    row = conn.execute("""
        SELECT *
        FROM payments

        WHERE
            user_id = ?

            AND status IN (
                'WAITING',
                'RECEIPT_SENT'
            )

        ORDER BY id DESC
        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return row


# ============================================================
# МЕНЮ
# ============================================================

async def show_payment_menu(
    query,
    user
):

    nominal_options = get_purchase_nominals(user)
    balances = database.get_balance_by_nominal(user["id"])

    lines = ["💳 Оплата и баланс", "", "Здесь я собрала ваш баланс и доступные варианты оплаты.", "", "🏷 Ваши тарифы:"]
    for nominal, item in nominal_options.items():
        balance = balances.get(nominal, {"paid": 0, "bonus": 0, "total": 0})
        labels = []
        for _, subject in item.get("programs", []):
            name = SUBJECT_NAMES.get(subject, subject)
            if name not in labels:
                labels.append(name)
        subjects = ", ".join(labels) if labels else "занятия"
        lines.append(
            f"• {money(nominal)} — {subjects}; баланс: {balance['total']}"
        )

    # Показываем и старые номиналы, которых уже нет в актуальном прайсе.
    for nominal, balance in balances.items():
        if nominal and nominal not in nominal_options and balance["total"] > 0:
            lines.append(
                f"• {money(nominal)} — старый номинал; баланс: {balance['total']}"
            )

    lines.extend([
        "",
        "Скидки за количество:",
        "",

        "• 1–3 занятия — без скидки",
        "• 4–5 занятий — −5%",
        "• 6–9 занятий — −10%",
        "• 10+ занятий — −15%",
        "",
        "🎁 Промокод применяется после скидки за количество.",
    ])

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=payment_menu(),
    )


# ============================================================
# CALLBACK УЧЕНИКА
# ============================================================

async def payment_buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = (
        update.callback_query
    )

    await query.answer()

    telegram_id = (
        update.effective_user.id
    )

    test_student_mode = (
        core_test_lab.active(telegram_id)
        and core_test_lab.get_test_role(telegram_id) == "STUDENT"
    )

    # Реального администратора не пускаем в ученические оплаты,
    # кроме Test Lab, когда явно выбрана роль STUDENT.
    if admin.is_admin(update) and not test_student_mode:

        return (
            ConversationHandler.END
        )

    user = (
        get_user_from_telegram(
            telegram_id
        )
    )

    if user is None:

        await query.edit_message_text(
            "Сначала откройте /start и завершите регистрацию — после этого я смогу показать оплату 💜"
        )

        return (
            ConversationHandler.END
        )

    data = (
        query.data
    )


    # ========================================================
    # ОПЛАТА НАЗНАЧЕННОГО ЗАНЯТИЯ
    # ========================================================

    if data.startswith(
        "payment_lesson|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        try:

            lesson = get_lesson_for_payment(
                lesson_id,
                user["id"]
            )

            text = build_lesson_payment_text(
                lesson
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ {error}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ В профиль",
                            callback_data="profile"
                        )
                    ]
                ])
            )

            return ConversationHandler.END

        context.user_data[
            "lesson_payment_id"
        ] = lesson_id

        context.user_data.pop(
            "lesson_payment_promo_code",
            None
        )

        await query.edit_message_text(
            text,
            reply_markup=lesson_payment_keyboard(
                lesson_id,
                promo_applied=False
            )
        )

        return ConversationHandler.END


    if data.startswith(
        "payment_lesson_promo|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        try:
            get_lesson_for_payment(
                lesson_id,
                user["id"]
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ {error}"
            )
            return ConversationHandler.END

        context.user_data[
            "lesson_payment_id"
        ] = lesson_id

        await query.edit_message_text(
            "🎁 Введите промокод\n\n"
            "Отправьте код одним сообщением — я сразу проверю его."
        )

        return WAIT_LESSON_PROMO


    if data.startswith(
        "payment_lesson_remove_promo|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        context.user_data.pop(
            "lesson_payment_promo_code",
            None
        )

        lesson = get_lesson_for_payment(
            lesson_id,
            user["id"]
        )

        await query.edit_message_text(
            build_lesson_payment_text(
                lesson
            ),
            reply_markup=lesson_payment_keyboard(
                lesson_id,
                promo_applied=False
            )
        )

        return ConversationHandler.END


    if data.startswith(
        "payment_lesson_confirm|"
    ):

        lesson_id = int(
            data.split("|")[1]
        )

        promo_code = context.user_data.get(
            "lesson_payment_promo_code"
        )

        try:

            lesson = get_lesson_for_payment(
                lesson_id,
                user["id"]
            )

            existing = (
                database.get_payment_for_lesson(
                    lesson_id
                )
            )

            if existing is not None:

                payment_id = existing["id"]

            else:

                payment_id = (
                    database.create_lesson_payment(
                        lesson_id,
                        promo_code=promo_code
                    )
                )

            payment = database.get_payment(
                payment_id
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ Я не смогла создать оплату.\n\n"
                f"{error}",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "⬅️ Назад",
                            callback_data=(
                                f"payment_lesson|{lesson_id}"
                            )
                        )
                    ]
                ])
            )

            return ConversationHandler.END

        context.user_data[
            "awaiting_payment_id"
        ] = payment_id

        text = (
            "💳 Оплата занятия\n\n"

            f"📅 {lesson['start_time'][:10]} "
            f"в {lesson['start_time'][11:16]}\n"

            f"💰 К оплате: "
            f"{money(payment['total_amount'])}\n"
        )

        if payment["promo_code"]:

            text += (
                f"🎁 Промокод: "
                f"{payment['promo_code']}\n"

                f"💸 Скидка: −"
                f"{money(payment['promo_discount_amount'])}\n"
            )

        text += (
            "\n"
            + payment_method_text()
            + "\n\n"
            "После перевода нажмите «📎 Отправить чек» — я передам его на проверку."
        )

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "📎 Отправить чек",
                        callback_data=(
                            f"payment_receipt|{payment_id}"
                        )
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ К занятию",
                        callback_data=(
                            f"payment_lesson|{lesson_id}"
                        )
                    )
                ]
            ])
        )

        return ConversationHandler.END


    # ========================================================
    # МЕНЮ
    # ========================================================

    if data == "payments":

        context.user_data.pop(
            "payment_promo_code",
            None
        )
        clear_payment_selection(context)

        await show_payment_menu(
            query,
            user
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # ОДНО ЗАНЯТИЕ
    # ========================================================

    if data == "payment_single":

        context.user_data.pop("payment_promo_code", None)
        clear_payment_selection(context)
        options = get_purchase_nominals(user)

        if len(options) == 1:
            nominal = next(iter(options))
            set_selected_nominal(context, user, nominal)
            await show_calculation(query, context, user, 1)
        else:
            await query.edit_message_text(
                "💳 Оплата одного занятия\n\n"
                "Выберите подходящий тариф — я рассчитаю сумму автоматически.\n\n"
                "Если несколько предметов стоят одинаково, один номинал "
                "можно использовать на любой из них.",
                reply_markup=nominal_selection_keyboard(user, "single"),
            )

        return ConversationHandler.END


    # ========================================================
    # АБОНЕМЕНТ
    # ========================================================

    if data == "payment_subscription":

        context.user_data.pop("payment_promo_code", None)
        clear_payment_selection(context)
        options = get_purchase_nominals(user)

        if len(options) == 1:
            selection = next(iter(options))
            item = set_selected_nominal(context, user, selection)
            await query.edit_message_text(
                "🎟 Абонемент\n\n"
                f"Тариф: {money(item['hourly_rate'])} / 60 мин\n"
                f"Основное занятие: {item['duration']} минут\n"
                f"Направление: {nominal_programs_text(item)}\n\n"
                "Скидка рассчитывается автоматически по выбранному объёму минут.\n\n"
                "Выберите количество занятий 👇",
                reply_markup=subscription_menu(item["duration"],item.get("program_id")),
            )
        else:
            await query.edit_message_text(
                "🎟 Абонемент\n\n"
                "Сначала выберите направление и тариф.\n\n"
                "Баланс будет начислен в минутах. Минуты можно использовать на занятие "
                "не короче вашего основного времени.",
                reply_markup=nominal_selection_keyboard(user, "subscription"),
            )

        return ConversationHandler.END


    if data.startswith("payment_nominal|"):
        try:
            _, selection_raw, mode = data.split("|", 2)
            selection = int(selection_raw)
            item = set_selected_nominal(context, user, selection)
        except Exception as error:
            await query.edit_message_text(
                f"❌ {error}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ К оплате", callback_data="payments")
                ]]),
            )
            return ConversationHandler.END

        context.user_data.pop("payment_promo_code", None)

        if mode == "single":
            await show_calculation(query, context, user, 1)
        else:
            await query.edit_message_text(
                "🎟 Абонемент\n\n"
                f"Тариф: {money(item['hourly_rate'])} / 60 мин\n"
                f"Основное занятие: {item['duration']} минут\n"
                f"Направление: {nominal_programs_text(item)}\n\n"
                "Скидка рассчитывается автоматически по выбранному объёму минут.\n\n"
                "Выберите количество занятий 👇",
                reply_markup=subscription_menu(context.user_data.get("payment_base_duration", 60),context.user_data.get("payment_program_id")),
            )

        return ConversationHandler.END


    # ========================================================
    # КОЛИЧЕСТВО
    # ========================================================

    if data.startswith(
        "paycount|"
    ):

        try:
            lessons_count = int(
                data.split("|")[1]
            )

        except (IndexError, ValueError):
            lessons_count = 0

        if not 1 <= lessons_count <= 50:

            await query.edit_message_text(
                "❌ Количество занятий должно быть от 1 до 50.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад", callback_data="payments")]
                ])
            )

            return ConversationHandler.END

        context.user_data.pop(
            "payment_promo_code",
            None
        )

        await show_calculation(
            query,
            context,
            user,
            lessons_count
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # ДРУГОЕ КОЛИЧЕСТВО
    # ========================================================

    if (
        data
        == "paycount_custom"
    ):

        context.user_data.pop(
            "payment_promo_code",
            None
        )

        await query.edit_message_text(
            "✏️ Сколько занятий добавить в абонемент?\n\n"

            "Например:\n"
            "7\n\n"

            "Минимум для абонемента — "
            "2 занятия."
        )

        return WAIT_CUSTOM_COUNT


    # ========================================================
    # ПРОМОКОД
    # ========================================================

    if data.startswith(
        "payment_promo|"
    ):

        lessons_count = int(
            data.split("|")[1]
        )

        context.user_data[
            "payment_lessons_count"
        ] = lessons_count

        await query.edit_message_text(
            "🎁 Введите промокод\n\n"

            "Отправьте код одним сообщением — я сразу проверю его."
        )

        return WAIT_PROMO


    # ========================================================
    # УБРАТЬ ПРОМОКОД
    # ========================================================

    if data.startswith(
        "payment_remove_promo|"
    ):

        lessons_count = int(
            data.split("|")[1]
        )

        context.user_data.pop(
            "payment_promo_code",
            None
        )

        await show_calculation(
            query,
            context,
            user,
            lessons_count
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # СОЗДАНИЕ ПЛАТЕЖА
    # ========================================================

    if data.startswith(
        "payment_confirm|"
    ):

        try:
            lessons_count = int(
                data.split("|")[1]
            )

        except (IndexError, ValueError):
            lessons_count = 0

        if not 1 <= lessons_count <= 50:

            await query.edit_message_text(
                "❌ Количество занятий должно быть от 1 до 50.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад", callback_data="payments")]
                ])
            )

            return ConversationHandler.END

        promo_code = (
            context.user_data.get(
                "payment_promo_code"
            )
        )

        waiting = (
            get_waiting_payment(
                user["id"]
            )
        )

        if (
            waiting is not None
            and waiting["status"]
            == "RECEIPT_SENT"
        ):

            await query.edit_message_text(
                "🧾 Один чек уже находится на проверке.\n\n"
                "Я сообщу вам, как только преподаватель его проверит 💜",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "📊 История оплат",
                                callback_data=(
                                    "payment_history"
                                )
                            )
                        ],

                        [
                            InlineKeyboardButton(
                                "⬅️ Главное меню",
                                callback_data="main"
                            )
                        ]
                    ])
                )
            )

            return (
                ConversationHandler.END
            )

        selected_selection = context.user_data.get("payment_selection_key")

        if selected_selection is None:
            # Совместимость со старым callback: если номинал единственный,
            # выбираем его автоматически.
            options = get_purchase_nominals(user)
            if len(options) == 1:
                selected_selection = next(iter(options))
                set_selected_nominal(context, user, selected_selection)
            else:
                await query.edit_message_text(
                    "❌ Сначала выбери номинал занятия — я посчитаю итоговую сумму.",
                    reply_markup=nominal_selection_keyboard(
                        user,
                        "single" if lessons_count == 1 else "subscription",
                    ),
                )
                return ConversationHandler.END

        try:

            # Повторно валидируем номинал перед созданием платежа, чтобы
            # изменение цены между открытием меню и подтверждением не создало
            # пакет по устаревшей цене.
            item = set_selected_nominal(context, user, selected_selection)

            payment_id = (
                database
                .create_payment(

                    user_id=(
                        user["id"]
                    ),

                    study_goal=(
                        item["study_goal"]
                    ),

                    subject=(
                        item["subject"]
                    ),

                    lessons_count=(
                        lessons_count
                    ),

                    price_per_lesson=(
                        int(item["nominal"])
                    ),

                    promo_code=(
                        promo_code
                    ),
                    minutes_total=int(lessons_count) * int(item["duration"]),
                    base_duration_minutes=int(item["duration"]),
                    hourly_rate=int(item["hourly_rate"]),
                    program_id=item.get("program_id")
                )
            )

        except Exception as error:

            await query.edit_message_text(
                f"❌ Я не смогла создать оплату.\n\n"
                f"{error}",

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "⬅️ Назад",
                                callback_data="payments"
                            )
                        ]
                    ])
                )
            )

            return (
                ConversationHandler.END
            )

        payment = (
            database
            .get_payment(
                payment_id
            )
        )

        context.user_data[
            "awaiting_payment_id"
        ] = payment_id

        text = (
            "💳 Всё готово к оплате\n\n"

            f"⏱ Оплачено времени: {int(payment['minutes_total'] or 0)} минут\n"
            f"🎟 Эквивалент: {payment['lessons_count']} × {int(payment['base_duration_minutes'] or 60)} мин\n"
            f"💰 Тариф: {money(int(payment['hourly_rate'] or 0))} / 60 мин\n"

            f"💰 К оплате: "
            f"{money(payment['total_amount'])}\n"
        )

        if (
            payment[
                "discount_percent"
            ]
        ):

            text += (
                f"🎁 Скидка за количество: "
                f"{payment['discount_percent']}%\n"
            )

        if (
            payment[
                "promo_code"
            ]
        ):

            text += (
                f"🎁 Промокод: "
                f"{payment['promo_code']}\n"

                f"💸 Скидка промокода: −"
                f"{money(payment['promo_discount_amount'])}\n"
            )

        text += (
            "\n"
            + payment_method_text()
            + "\n\n"
            "После перевода нажмите «📎 Отправить чек» — я передам его на проверку."
        )

        await query.edit_message_text(
            text,

            reply_markup=(
                InlineKeyboardMarkup([

                    [
                        InlineKeyboardButton(
                            "📎 Отправить чек",

                            callback_data=(
                                f"payment_receipt|"
                                f"{payment_id}"
                            )
                        )
                    ],

                    [
                        InlineKeyboardButton(
                            "⬅️ К оплате",
                            callback_data="payments"
                        )
                    ]
                ])
            )
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # ЧЕК ДЛЯ ЧЕРНОВИКА РАЗОВОГО ЗАНЯТИЯ
    # ========================================================

    if data.startswith("single_draft_receipt|"):
        payment_id = int(data.split("|", 1)[1])

        payment = database.get_payment(payment_id)

        if (
            payment is None
            or int(payment["user_id"]) != int(user["id"])
        ):
            await query.edit_message_text(
                "Я не нашла эту оплату. Вернись к заявке и открой оплату ещё раз."
            )
            return ConversationHandler.END

        draft = database.get_active_booking_draft(user["id"])

        if (
            draft is None
            or not draft["payment_id"]
            or int(draft["payment_id"]) != int(payment_id)
        ):
            await query.edit_message_text(
                "Я не нашла связанную заявку. Вернись к записи и выбери занятие ещё раз."
            )
            return ConversationHandler.END

        context.user_data["awaiting_payment_id"] = payment_id
        context.user_data["single_booking_draft_id"] = draft["id"]
        context.user_data["awaiting_single_draft_receipt"] = True

        await query.edit_message_text(
            "📎 Прикрепи чек\n\n"
            "Отправь одним сообщением:\n"
            "• фото\n"
            "• скриншот\n"
            "• PDF\n"
            "• документ\n\n"
            "Чек пока не будет отправлен преподавателю — "
            "я сначала прикреплю его к заявке."
        )

        return WAIT_RECEIPT






    # ========================================================
    # ОТПРАВКА ЧЕКА
    # ========================================================

    if data.startswith(
        "payment_receipt|"
    ):

        payment_id = int(
            data.split("|")[1]
        )

        payment = (
            database
            .get_payment(
                payment_id
            )
        )

        if (
            payment is None
            or payment["user_id"]
            != user["id"]
        ):

            await query.edit_message_text(
                "Я не нашла этот платёж. Возможно, он уже изменился — откройте историю оплат ещё раз."
            )

            return (
                ConversationHandler.END
            )

        if (
            payment["status"]
            == "PAID"
        ):

            await query.edit_message_text(
                "✅ Эта оплата уже "
                "подтверждена."
            )

            return (
                ConversationHandler.END
            )

        context.user_data[
            "awaiting_payment_id"
        ] = payment_id

        await query.edit_message_text(
            "📎 Отправьте чек\n\n"

            "Пришлите его одним сообщением — я передам файл преподавателю.\n\n"

            "Можно отправить:\n"
            "• фото\n"
            "• скриншот\n"
            "• PDF\n"
            "• документ"
        )

        return WAIT_RECEIPT


    # ========================================================
    # ИСТОРИЯ
    # ========================================================

    if data == "payment_history":

        rows = (
            database
            .get_user_payments(
                user["id"],
                10
            )
        )

        if not rows:

            text = (
                "📊 История оплат\n\nПока здесь пусто. После первой оплаты я сохраню её в истории 💜"
            )

        else:

            statuses = {
                "REVERSED": "↩ подтверждение отменено",

                "WAITING":
                    "⏳ ожидает оплаты",

                "RECEIPT_SENT":
                    "🧾 чек проверяется",

                "PAID":
                    "✅ подтверждено",

                "REJECTED":
                    "❌ отклонено",

                "CANCELLED":
                    "🚫 отменено",
            }

            lines = [
                "📊 История оплат",
                ""
            ]

            for payment in rows:

                # Бонусные технические
                # платежи ученику как оплату
                # не показываем

                if (
                    payment[
                        "payment_type"
                    ]
                    == "BONUS"
                ):

                    continue

                status = (
                    statuses.get(
                        payment["status"],
                        "⚪ Неизвестный статус"
                    )
                )

                line = (
                    f"💳 #{payment['id']}\n"

                    f"🎟 {payment_minutes_label(payment)}\n"

                    f"💰 "
                    f"{money(payment['total_amount'])}\n"

                    f"{status}"
                )

                if (
                    payment[
                        "promo_code"
                    ]
                ):

                    line += (
                        f"\n🎁 "
                        f"{payment['promo_code']}"
                    )

                lines.append(
                    line
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
                            "⬅️ Назад",
                            callback_data="payments"
                        )
                    ]
                ])
            )
        )

        return (
            ConversationHandler.END
        )

    return (
        ConversationHandler.END
    )


# ============================================================
# СВОЁ КОЛИЧЕСТВО
# ============================================================

async def custom_count_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = (
        get_user_from_telegram(
            update.effective_user.id
        )
    )

    if user is None:

        return (
            ConversationHandler.END
        )

    try:

        count = int(
            update.message.text
            .strip()
        )

    except ValueError:

        await update.message.reply_text(
            "Напишите количество числом, например 7 💜"
        )

        return WAIT_CUSTOM_COUNT

    if count < 2:

        await update.message.reply_text(
            "Для одного занятия "
            "используйте кнопку "
            "«Оплатить 1 занятие»."
        )

        return WAIT_CUSTOM_COUNT

    if count > 50:

        await update.message.reply_text(
            "За один раз можно выбрать не больше 50 занятий."
        )

        return WAIT_CUSTOM_COUNT

    context.user_data[
        "payment_lessons_count"
    ] = count

    context.user_data.pop(
        "payment_promo_code",
        None
    )

    text, result = (
        build_calculation_text(
            user,
            count,
            price_per_lesson=context.user_data.get("payment_nominal"),
            programs_text=context.user_data.get("payment_nominal_programs"),
            hourly_rate=context.user_data.get("payment_hourly_rate"),
            base_duration=context.user_data.get("payment_base_duration"),
        )
    )

    await update.message.reply_text(
        text,

        reply_markup=(
            calculation_keyboard(
                count,
                False
            )
        )
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# ПРОМОКОД
# ============================================================

async def promo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = (
        get_user_from_telegram(
            update.effective_user.id
        )
    )

    if user is None:

        return (
            ConversationHandler.END
        )

    promo_code = (
        database
        .normalize_promo_code(
            update.message.text
        )
    )

    lessons_count = (
        context.user_data.get(
            "payment_lessons_count"
        )
    )

    if lessons_count is None:

        await update.message.reply_text(
            "❌ Не удалось определить "
            "количество занятий.",

            reply_markup=(
                InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "💳 К оплате",
                            callback_data="payments"
                        )
                    ]
                ])
            )
        )

        return (
            ConversationHandler.END
        )

    validation = (
        database
        .validate_promo_code(

            promo_code,
            user["id"]
        )
    )

    if not validation[
        "valid"
    ]:

        await update.message.reply_text(
            f"❌ {validation['reason']}\n\n"
            "Введите другой промокод."
        )

        return WAIT_PROMO

    context.user_data[
        "payment_promo_code"
    ] = promo_code

    text, result = (
        build_calculation_text(

            user,
            lessons_count,
            promo_code,
            price_per_lesson=context.user_data.get("payment_nominal"),
            programs_text=context.user_data.get("payment_nominal_programs"),
            hourly_rate=context.user_data.get("payment_hourly_rate"),
            base_duration=context.user_data.get("payment_base_duration"),
        )
    )

    await update.message.reply_text(
        "✅ Готово, промокод применён 💜\n\n"
        + text,

        reply_markup=(
            calculation_keyboard(
                lessons_count,
                True
            )
        )
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# ПРОМОКОД ДЛЯ КОНКРЕТНОГО ЗАНЯТИЯ
# ============================================================

async def lesson_promo_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = get_user_from_telegram(
        update.effective_user.id
    )

    if user is None:
        return ConversationHandler.END

    lesson_id = context.user_data.get(
        "lesson_payment_id"
    )

    if lesson_id is None:

        await update.message.reply_text(
            "❌ Не удалось определить занятие."
        )

        return ConversationHandler.END

    try:

        lesson = get_lesson_for_payment(
            lesson_id,
            user["id"]
        )

        promo_code = (
            database.normalize_promo_code(
                update.message.text
            )
        )

        validation = database.validate_promo_code(
            promo_code,
            user["id"]
        )

        if not validation["valid"]:

            await update.message.reply_text(
                f"❌ {validation['reason']}\n\n"
                "Введите другой промокод."
            )

            return WAIT_LESSON_PROMO

        context.user_data[
            "lesson_payment_promo_code"
        ] = promo_code

        text = build_lesson_payment_text(
            lesson,
            promo_code=promo_code
        )

    except Exception as error:

        await update.message.reply_text(
            f"❌ {error}"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "✅ Готово, промокод применён 💜\n\n"
        + text,

        reply_markup=lesson_payment_keyboard(
            lesson_id,
            promo_applied=True
        )
    )

    return ConversationHandler.END


# ============================================================
# ПРИЁМ ЧЕКА
# ============================================================

async def receipt_cancel_to_home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Завершает ожидание чека при уходе пользователя на главную."""
    context.user_data.pop("awaiting_payment_id", None)
    return ConversationHandler.END


async def receipt_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = (
        get_user_from_telegram(
            update.effective_user.id
        )
    )

    if user is None:

        return (
            ConversationHandler.END
        )

    payment_id = (
        context.user_data.get(
            "awaiting_payment_id"
        )
    )

    if payment_id is None:

        waiting = (
            get_waiting_payment(
                user["id"]
            )
        )

        if waiting is not None:

            payment_id = (
                waiting["id"]
            )

    if payment_id is None:

        await update.message.reply_text(
            "Я не нашла активную оплату. Откройте раздел оплаты ещё раз — я покажу актуальные варианты."
        )

        return (
            ConversationHandler.END
        )

    payment = (
        database
        .get_payment(
            payment_id
        )
    )

    if (
        payment is None
        or payment["user_id"]
        != user["id"]
    ):

        await update.message.reply_text(
            "Я не нашла этот платёж. Возможно, он уже изменился — откройте историю оплат ещё раз."
        )

        return (
            ConversationHandler.END
        )

    if payment["status"] in ("PAID", "REVERSED", "CANCELLED"):

        await update.message.reply_text(
            "✅ Этот платёж уже подтверждён — чек больше не нужен."
            if payment["status"] == "PAID"
            else "🚫 Этот платёж отменён — чек к нему прикрепить нельзя. "
                 "Создайте новую оплату в разделе «Оплата»."
        )

        return (
            ConversationHandler.END
        )


    # ========================================================
    # ФОТО
    # ========================================================

    if update.message.photo:

        file_id = (
            update.message
            .photo[-1]
            .file_id
        )

        file_type = "PHOTO"


    # ========================================================
    # ДОКУМЕНТ
    # ========================================================

    elif update.message.document:

        file_id = (
            update.message
            .document
            .file_id
        )

        file_type = "DOCUMENT"


    else:

        await update.message.reply_text(
            "Пришлите фото, скриншот, PDF или другой документ с чеком 💜"
        )

        return WAIT_RECEIPT


    # ========================================================
    # БД
    # ========================================================

    try:
        receipt_id = database.add_receipt(

            payment_id=(
                payment_id
            ),

            user_id=(
                user["id"]
            ),

            file_id=(
                file_id
            ),

            file_type=(
                file_type
            ),

            source_platform=(
                "TELEGRAM"
            )
        )

    except ValueError as error:

        # Платёж закрыт (PAID/REVERSED/CANCELLED) или не найден —
        # статус мог смениться между проверкой и записью.
        await update.message.reply_text(
            f"❌ {error} Откройте историю оплат, чтобы проверить статус."
        )

        return (
            ConversationHandler.END
        )

    payment = (
        database
        .get_payment(
            payment_id
        )
    )

    # Если чек относится к разовой записи — фиксируем это
    # отдельно от обычной покупки абонемента.
    if context.user_data.get("awaiting_single_draft_receipt"):
        draft = database.get_active_booking_draft(
            user["id"]
        )

        if (
            draft is not None
            and draft["payment_id"]
            and int(draft["payment_id"]) == int(payment_id)
        ):
            database.update_booking_draft(
                draft["id"],
                status="PAYMENT_ATTACHED",
            )


    # ========================================================
    # УЧЕНИКУ
    # ========================================================

    await update.message.reply_text(
        "✅ Чек получила 💜\n\n"

        "Я передала его преподавателю на проверку.\n\n"

        "После подтверждения я сразу зачислю оплаченные минуты на ваш баланс.\n\n"

        "До подтверждения эти минуты ещё нельзя использовать для новых записей. Я сообщу, когда всё будет готово."
    )


    # ========================================================
    # ТЕБЕ
    # ========================================================

    caption = (
        "💳 НОВЫЙ ЧЕК\n\n"

        f"👤 "
        f"{user['name']}\n"

        f"🎓 "
        f"{user['grade']} класс\n"

        f"📚 "
        f"{GOAL_NAMES.get(user['study_goal'], user['study_goal'])}\n"

        f"📖 "
        f"{SUBJECT_NAMES.get(user['main_subject'], user['main_subject'])}\n\n"

        f"🎟 Занятий: "
        f"{payment['lessons_count']}\n"

        f"💰 Сумма: "
        f"{money(payment['total_amount'])}\n"
    )

    if (
        payment[
            "discount_percent"
        ]
    ):

        caption += (
            f"🎁 Скидка за количество: "
            f"{payment['discount_percent']}%\n"
        )

    if (
        payment[
            "promo_code"
        ]
    ):

        caption += (
            f"🎁 Промокод: "
            f"{payment['promo_code']}\n"

            f"💸 Скидка промокода: "
            f"−{money(payment['promo_discount_amount'])}\n"
        )

    caption += (
        f"\n💳 Платёж #{payment_id}"
    )

    keyboard = (
        InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "✅ Подтвердить оплату",

                    callback_data=(
                        f"payment_admin_approve|"
                        f"{payment_id}"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "❌ Отклонить",

                    callback_data=(
                        f"payment_admin_reject|"
                        f"{payment_id}"
                    )
                )
            ]
        ])
    )

    if file_type == "PHOTO":

        await context.bot.send_photo(

            chat_id=(
                admin.ADMIN_ID
            ),

            photo=file_id,

            caption=caption,

            reply_markup=keyboard
        )

    else:

        await context.bot.send_document(

            chat_id=(
                admin.ADMIN_ID
            ),

            document=file_id,

            caption=caption,

            reply_markup=keyboard
        )

    context.user_data.pop(
        "awaiting_payment_id",
        None
    )

    return (
        ConversationHandler.END
    )


# ============================================================
# РЕДАКТИРОВАНИЕ СООБЩЕНИЯ С ЧЕКОМ
# ============================================================

async def edit_receipt_message(
    query,
    text,
    reply_markup=None
):

    try:

        if (
            query.message.photo
            or query.message.document
        ):

            await query.edit_message_caption(
                caption=text,
                reply_markup=reply_markup
            )

        else:

            await query.edit_message_text(
                text,
                reply_markup=reply_markup
            )

    except Exception:

        await query.message.reply_text(
            text,
            reply_markup=reply_markup
        )


# ============================================================
# АДМИН — ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ============================================================

async def admin_payment_buttons(
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

    if data.startswith(("payment_admin_reverse|", "payment_admin_reverse_yes|", "payment_admin_history|")):
        from handlers.payment_reversal import handle
        return await handle(update, context)


    # ========================================================
    # ПОДТВЕРДИТЬ
    # ========================================================

    if data.startswith(
        "payment_admin_approve|"
    ):

        payment_id = int(
            data.split("|")[1]
        )

        try:

            draft_result = (
                database
                .approve_paid_booking_draft_payment(
                    payment_id
                )
            )

            if draft_result is not None:
                package_id, draft_lesson_id = draft_result
            else:
                package_id = (
                    database
                    .approve_payment(
                        payment_id
                    )
                )
                draft_lesson_id = None

        except Exception as error:

            await query.answer(
                str(error),
                show_alert=True
            )

            return

        payment = (
            database
            .get_payment(
                payment_id
            )
        )

        user = (
            database
            .get_user(
                payment["user_id"]
            )
        )

        # A package payment may cover regular lessons that were already
        # waiting for payment.  Reserve newly credited minutes for the
        # nearest suitable lessons first.
        covered_lesson_ids = []
        autocover_warning = None

        if not (
            "lesson_id" in payment.keys()
            and payment["lesson_id"]
        ):
            conn = database.connect()
            try:
                awaiting_rows = conn.execute(
                    """
                    SELECT id
                    FROM lessons
                    WHERE user_id = ?
                      AND lesson_status = 'CONFIRMED'
                      AND payment_status = 'AWAITING_PAYMENT'
                      AND start_time > ?
                    ORDER BY start_time ASC, id ASC
                    """,
                    (
                        int(user["id"]),
                        database.now_iso(),
                    ),
                ).fetchall()
            finally:
                conn.close()

            for awaiting_row in awaiting_rows:
                lesson_id = int(awaiting_row["id"])
                try:
                    database.charge_reserved_lesson(
                        lesson_id
                    )
                except ValueError as error:
                    # Payment itself is confirmed, but the nearest lesson could
                    # not be covered by compatible minutes. Do not hide this:
                    # keep the payment PAID and surface the mismatch to admin.
                    autocover_warning = (
                        f"⚠️ Платёж подтверждён, но занятие #{lesson_id} "
                        f"не удалось автоматически покрыть: {error}"
                    )
                    print("AUTO COVER AWAITING:", lesson_id, repr(error))
                    break
                except Exception as error:
                    print(
                        "AUTO COVER AWAITING:",
                        lesson_id,
                        repr(error),
                    )
                    break
                else:
                    covered_lesson_ids.append(
                        lesson_id
                    )

        balance = minute_balance.get_balance(
            user["id"],
            hourly_rate=int(payment["hourly_rate"] or 0) if "hourly_rate" in payment.keys() else None,
        )


        # ====================================================
        # ТЕБЕ
        # ====================================================

        admin_text = (
            "✅ Оплата подтверждена 💜\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"🎟 Зачислено: {payment_minutes_label(payment)}\n"

            f"💰 Получено: "
            f"{money(payment['total_amount'])}\n"
        )

        if (
            payment[
                "discount_percent"
            ]
        ):

            admin_text += (
                f"🎁 Скидка: "
                f"{payment['discount_percent']}%\n"
            )

        if (
            payment[
                "promo_code"
            ]
        ):

            admin_text += (
                f"🎁 Промокод: "
                f"{payment['promo_code']}\n"
            )

        if autocover_warning:
            admin_text += "\n\n" + autocover_warning + "\n"

        admin_text += (
            "\n🎟 БАЛАНС\n"

            f"💳 Оплачено минут: {balance['paid']}\n"
            f"🎁 Бонусных минут: {balance['bonus']}\n"
            f"Всего минут: {balance['total']}\n\n"

            f"📦 Пакет #{package_id}\n"
            f"💳 Платёж #{payment_id}"
        )

        await edit_receipt_message(
            query,
            admin_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Отменить ошибочное подтверждение", callback_data=f"payment_admin_reverse|{payment_id}")]
            ])
        )


        # ====================================================
        # УЧЕНИКУ
        # ====================================================

        if (
            user[
                "telegram_id"
            ]
        ):

            if (
                "lesson_id" in payment.keys()
                and payment["lesson_id"]
            ):

                lesson = database.get_lesson(
                    payment["lesson_id"]
                )

                student_text = (
                    "✅ Оплата занятия подтверждена 💜\n\n"

                    f"📅 "
                    f"{lesson['start_time'][:10]} "
                    f"в {lesson['start_time'][11:16]}\n"

                    f"💰 Оплачено: "
                    f"{money(payment['total_amount'])}\n\n"

                    "Всё готово — занятие остаётся в вашем расписании."
                )

            else:

                student_text = (
                    "✅ Оплата подтверждена 💜\n\n"

                    f"🎟 Зачислено: {payment_minutes_label(payment)}\n"

                    f"💰 Оплачено: "
                    f"{money(payment['total_amount'])}\n"
                )

            if (
                payment[
                    "promo_code"
                ]
            ):

                student_text += (
                    f"\n🎁 Промокод: "
                    f"{payment['promo_code']}"
                )

            if not (
                "lesson_id" in payment.keys()
                and payment["lesson_id"]
            ):

                student_text += (
                    "\n\n🎟 Ваш баланс\n"

                    f"💳 Оплаченных минут: {balance['paid']}\n"
                    f"🎁 Бонусных минут: {balance['bonus']}\n"
                    f"Всего доступно: {balance['total']} минут\n\n"

                    "Теперь оплачивать каждую запись отдельно не нужно.\n\n"

                    "Пока на балансе достаточно минут, я буду сразу показывать доступное время для записи."
                )

            await context.bot.send_message(

                chat_id=(
                    user[
                        "telegram_id"
                    ]
                ),

                text=(
                    student_text
                ),

                reply_markup=(
                    InlineKeyboardMarkup([

                        [
                            InlineKeyboardButton(
                                "📅 Записаться",
                                callback_data="booking"
                            )
                        ],

                        [
                            InlineKeyboardButton(
                                "👤 Мой профиль",
                                callback_data="profile"
                            )
                        ]
                    ])
                )
            )

        return


    # ========================================================
    # ОТКЛОНИТЬ
    # ========================================================

    if data.startswith(
        "payment_admin_reject|"
    ):

        payment_id = int(
            data.split("|")[1]
        )

        try:

            database.reject_payment(
                payment_id
            )

        except Exception as error:

            await query.answer(
                str(error),
                show_alert=True
            )

            return

        payment = (
            database
            .get_payment(
                payment_id
            )
        )

        user = (
            database
            .get_user(
                payment["user_id"]
            )
        )

        admin_text = (
            "❌ ОПЛАТА ОТКЛОНЕНА\n\n"

            f"👤 "
            f"{user['name']}\n"

            f"🎟 {payment_minutes_label(payment)}\n"

            f"💰 "
            f"{money(payment['total_amount'])}\n\n"

            f"💳 Платёж #{payment_id}"
        )

        await edit_receipt_message(
            query,
            admin_text
        )

        if (
            user[
                "telegram_id"
            ]
        ):

            await context.bot.send_message(

                chat_id=(
                    user[
                        "telegram_id"
                    ]
                ),

                text=(
                    "❌ Оплату пока не удалось подтвердить.\n\n"

                    "Проверьте перевод и чек. После этого откройте оплату ещё раз — я помогу создать новую заявку."
                ),

                reply_markup=(
                    InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                "💳 Перейти к оплате",
                                callback_data="payments"
                            )
                        ]
                    ])
                )
            )

        return


# ============================================================
# PAYMENT HANDLER
# ============================================================

def get_payment_handler():

    return ConversationHandler(

        entry_points=[

            CallbackQueryHandler(
                payment_buttons,

                pattern=(
                    r"^payments$"
                    r"|^payment_single$"
                    r"|^payment_subscription$"
                    r"|^payment_nominal\|"
                    r"|^paycount\|"
                    r"|^paycount_custom$"
                    r"|^payment_promo\|"
                    r"|^payment_remove_promo\|"
                    r"|^payment_confirm\|"
                    r"|^payment_lesson\|"
                    r"|^payment_lesson_promo\|"
                    r"|^payment_lesson_remove_promo\|"
                    r"|^payment_lesson_confirm\|"
                    r"|^payment_receipt\|"
                    r"|^single_draft_receipt\|"
                    r"|^payment_history$"
                )
            )
        ],

        states={

            WAIT_CUSTOM_COUNT: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    custom_count_handler
                )
            ],

            WAIT_PROMO: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    promo_handler
                )
            ],

            WAIT_RECEIPT: [

                # Чек: фото или документ
                MessageHandler(
                    (
                        filters.PHOTO
                        | filters.Document.ALL
                    ),
                    receipt_handler
                ),

                # Если вместо файла прислали текст —
                # receipt_handler объяснит, что нужен файл.
                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,
                    receipt_handler
                ),

                # Не держим пользователя внутри сценария оплаты,
                # если он ушёл на главную.
                CallbackQueryHandler(
                    receipt_cancel_to_home,
                    pattern=r"^main$"
                ),
            ],

            WAIT_LESSON_PROMO: [

                MessageHandler(
                    filters.TEXT
                    & ~filters.COMMAND,

                    lesson_promo_handler
                )
            ],
        },

        fallbacks=[],

        allow_reentry=True
    )


# ============================================================
# ADMIN PAYMENT HANDLER
# ============================================================

def get_admin_payment_handler():

    return CallbackQueryHandler(

        admin_payment_buttons,

        pattern=(
            r"^payment_admin_"
        )
    )
