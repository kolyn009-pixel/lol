from __future__ import annotations

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import database
from core import admin_roles, minute_balance
from . import exam_plans, mock_tests, renewals, tariffs

# Distinct high-numbered states to avoid clashes with the existing handlers.
MOCK_ACTION = 9301
MOCK_DEADLINE = 9302
MOCK_TITLE = 9303
MOCK_TEST_SCORE = 9304
MOCK_PRIMARY_SCORE = 9305
MOCK_DURATION = 9306
MOCK_RESULT_COMMENT = 9307

PLAN_PROGRAM = 9321
PLAN_DATE = 9322
PLAN_TARGET = 9323
PLAN_WEEKLY_MINUTES = 9324

GOAL_RU = {
    "EGE": "ЕГЭ",
    "OGE": "ОГЭ",
    "OLYMPIAD": "Олимпиада",
    "SCHOOL": "Школьная программа",
}
SUBJECT_RU = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}
STATUS_RU = {
    "ASSIGNED": "назначен",
    "SUBMITTED": "сдан",
    "REVIEWED": "проверен",
}


def _admin(uid: int) -> bool:
    return admin_roles.is_admin_id(uid)


def goal_ru(value) -> str:
    return GOAL_RU.get(str(value or "").upper(), str(value or "—"))


def subject_ru(value) -> str:
    return SUBJECT_RU.get(str(value or "").upper(), str(value or "—"))


def program_label(program) -> str:
    return f"{goal_ru(program['study_goal'])} • {subject_ru(program['subject'])}"


def _parse_date(value: str):
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def _students():
    conn = database.connect()
    try:
        return conn.execute(
            "SELECT id,name FROM users WHERE active=1 ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        conn.close()


def _programs(uid: int):
    return database.get_student_programs(uid, active_only=True, approved_only=True)


def _student_name(uid: int) -> str:
    user = database.get_user(uid)
    return user["name"] if user else f"Ученик #{uid}"


def _student_menu(uid: int):
    # Canonical admin student actions.
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎓 Школа / колледж",
                callback_data=f"edu_profile|{uid}",
            ),
            InlineKeyboardButton(
                "📚 Направления",
                callback_data=f"edu_programs|{uid}",
            ),
        ],
        [
            InlineKeyboardButton("⚡ Следующее действие", callback_data=f"ff_student|{uid}"),
            InlineKeyboardButton("📦 Продление", callback_data=f"ff_renew|{uid}"),
        ],
        [
            InlineKeyboardButton("🧪 Пробники", callback_data=f"ff_mocks|{uid}"),
            InlineKeyboardButton("📜 История", callback_data=f"ff_timeline|{uid}"),
        ],
        [
            InlineKeyboardButton("📈 Прогноз результата", callback_data=f"ff_performance|{uid}"),
            InlineKeyboardButton("🔄 Обмен окнами", callback_data=f"ff_swap|{uid}"),
        ],
        [
            InlineKeyboardButton("📊 Отчёт за месяц", callback_data=f"ff_report|{uid}"),
            InlineKeyboardButton("🎯 План экзамена", callback_data=f"ff_plan|{uid}"),
        ],
        [InlineKeyboardButton("💳 Журнал минут", callback_data=f"ff_ledger|{uid}")],
        [InlineKeyboardButton("🧭 Коммуникация и контроль", callback_data=f"crm_student|{uid}")],
        [InlineKeyboardButton("⬅️ Карточка ученика", callback_data=f"student_view|{uid}")],
    ])


def _mock_actions(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Назначить пробник", callback_data=f"ui_mock_assign|{uid}")],
        [InlineKeyboardButton("✍️ Внести результат", callback_data=f"ui_mock_result|{uid}")],
        [InlineKeyboardButton("📋 История пробников", callback_data=f"ui_mock_history|{uid}")],
        [InlineKeyboardButton("⬅️ Карточка ученика", callback_data=f"ff_student|{uid}")],
    ])


async def _edit(query, text: str, markup=None):
    try:
        await query.edit_message_text(text[:3900], reply_markup=markup)
    except Exception as exc:
        if "Message is not modified" not in str(exc):
            raise


# ---------------------------------------------------------------------------
# Mock tests UI
# ---------------------------------------------------------------------------
async def mock_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _admin(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return ConversationHandler.END

    data = q.data
    if data.startswith("ff_mocks|"):
        uid = int(data.split("|", 1)[1])
        context.user_data["ui_mock_uid"] = uid
        await _edit(
            q,
            f"🧪 ПРОБНИКИ\n\nУченик: {_student_name(uid)}\n\nВыберите действие:",
            _mock_actions(uid),
        )
        return MOCK_ACTION

    rows = _students()
    kb = [[InlineKeyboardButton(f"👤 {r['name']}", callback_data=f"ui_mock_student|{r['id']}")] for r in rows[:80]]
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data="ff_main")])
    await _edit(q, "🧪 ПРОБНИКИ\n\nВыберите ученика:", InlineKeyboardMarkup(kb))
    return MOCK_ACTION


async def mock_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d.startswith("ui_mock_student|"):
        uid = int(d.split("|", 1)[1])
        context.user_data["ui_mock_uid"] = uid
        await _edit(
            q,
            f"🧪 ПРОБНИКИ\n\nУченик: {_student_name(uid)}\n\nВыберите действие:",
            _mock_actions(uid),
        )
        return MOCK_ACTION

    if d.startswith("ui_mock_assign|"):
        uid = int(d.split("|", 1)[1])
        context.user_data["ui_mock_uid"] = uid
        programs = _programs(uid)
        if not programs:
            await _edit(q, "❌ У ученика нет активного подтверждённого направления.", _mock_actions(uid))
            return MOCK_ACTION
        kb = [[InlineKeyboardButton(program_label(p), callback_data=f"ui_mock_program|{p['id']}")] for p in programs]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"ui_mock_student|{uid}")])
        await _edit(q, "🧪 НАЗНАЧИТЬ ПРОБНИК\n\nВыберите направление:", InlineKeyboardMarkup(kb))
        return MOCK_ACTION

    if d.startswith("ui_mock_program|"):
        pid = int(d.split("|", 1)[1])
        context.user_data["ui_mock_pid"] = pid
        await _edit(q, "📅 Введите дедлайн пробника.\n\nНапример: 28.08.2026")
        return MOCK_DEADLINE

    if d.startswith("ui_mock_history|"):
        uid = int(d.split("|", 1)[1])
        rows = mock_tests.list_for_user(uid)
        if not rows:
            text = "🧪 ИСТОРИЯ ПРОБНИКОВ\n\nПока пробников нет."
        else:
            lines = ["🧪 ИСТОРИЯ ПРОБНИКОВ", ""]
            for row in rows[:30]:
                score = f"{row['test_score']} баллов" if row["test_score"] is not None else "без результата"
                lines.append(
                    f"• {row['title']}\n"
                    f"  {goal_ru(row['exam_type'])} • {subject_ru(row['subject'])}\n"
                    f"  Дедлайн: {row['deadline'] or '—'}\n"
                    f"  Статус: {STATUS_RU.get(row['status'], row['status'])} • {score}"
                )
            text = "\n\n".join(lines)
        await _edit(q, text, _mock_actions(uid))
        return MOCK_ACTION

    if d.startswith("ui_mock_result|"):
        uid = int(d.split("|", 1)[1])
        rows = [r for r in mock_tests.list_for_user(uid) if r["status"] != "REVIEWED"]
        if not rows:
            await _edit(q, "✅ Нет пробников, ожидающих результата.", _mock_actions(uid))
            return MOCK_ACTION
        kb = [[InlineKeyboardButton(f"🧪 {r['title']}", callback_data=f"ui_mock_pick|{r['id']}")] for r in rows[:30]]
        kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"ui_mock_student|{uid}")])
        await _edit(q, "✍️ ВНЕСТИ РЕЗУЛЬТАТ\n\nВыберите пробник:", InlineKeyboardMarkup(kb))
        return MOCK_ACTION

    if d.startswith("ui_mock_pick|"):
        mid = int(d.split("|", 1)[1])
        context.user_data["ui_mock_mid"] = mid
        await _edit(q, "📊 Введите тестовый балл.\n\nНапример: 72")
        return MOCK_TEST_SCORE

    return MOCK_ACTION


async def mock_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = _parse_date(update.message.text)
    if not parsed:
        await update.message.reply_text("Я не смогла распознать дату. Введите её, например, так: 28.08.2026")
        return MOCK_DEADLINE
    if parsed < datetime.now().date():
        await update.message.reply_text("Дедлайн должен быть в будущем. Введите другую дату, пожалуйста.")
        return MOCK_DEADLINE
    context.user_data["ui_mock_deadline"] = parsed.isoformat()
    await update.message.reply_text("📝 Напишите название пробника.\n\nНапример: Пробник №3 — механика")
    return MOCK_TITLE


async def mock_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = context.user_data.get("ui_mock_uid")
    pid = context.user_data.get("ui_mock_pid")
    deadline = context.user_data.get("ui_mock_deadline")
    title = update.message.text.strip()
    if not uid or not pid or not deadline or not title:
        await update.message.reply_text("❌ Не удалось сохранить пробник. Откройте раздел «Пробники» заново.")
        return ConversationHandler.END
    mid = mock_tests.assign(uid, pid, title, deadline=deadline, actor=update.effective_user.id)
    user = database.get_user(uid)
    if user and user["telegram_id"]:
        try:
            await context.bot.send_message(
                int(user["telegram_id"]),
                f"🧪 Вам назначен пробник\n\n{title}\n📅 Выполнить до: {datetime.fromisoformat(deadline).strftime('%d.%m.%Y')}\n\nОткройте «🧪 Пробники» в боте.",
            )
        except Exception:
            pass
    await update.message.reply_text(f"✅ Пробник назначен.\n\n{title}\n📅 Дедлайн: {datetime.fromisoformat(deadline).strftime('%d.%m.%Y')}")
    for key in ("ui_mock_pid", "ui_mock_deadline"):
        context.user_data.pop(key, None)
    return ConversationHandler.END


async def mock_test_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        score = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число, например 72.")
        return MOCK_TEST_SCORE
    if score < 0 or score > 100:
        await update.message.reply_text("Тестовый балл должен быть от 0 до 100.")
        return MOCK_TEST_SCORE
    context.user_data["ui_mock_test_score"] = score
    await update.message.reply_text("🧮 Введите первичный балл.\nЕсли не хотите фиксировать — отправьте «-».")
    return MOCK_PRIMARY_SCORE


async def mock_primary_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if raw == "-":
        value = None
    else:
        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            await update.message.reply_text("❌ Введите число или «-».")
            return MOCK_PRIMARY_SCORE
    context.user_data["ui_mock_primary"] = value
    await update.message.reply_text("⏱ Сколько минут заняло выполнение?\nЕсли не фиксируем — отправьте «-».")
    return MOCK_DURATION


async def mock_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    if raw == "-":
        value = None
    else:
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Введите положительное число минут или «-».")
            return MOCK_DURATION
    context.user_data["ui_mock_duration"] = value
    await update.message.reply_text("💬 Добавьте короткий комментарий к результату.\nЕсли комментарий не нужен — отправьте «-».")
    return MOCK_RESULT_COMMENT


async def mock_result_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comment = update.message.text.strip()
    if comment == "-":
        comment = None
    mid = context.user_data.get("ui_mock_mid")
    score = context.user_data.get("ui_mock_test_score")
    primary = context.user_data.get("ui_mock_primary")
    duration = context.user_data.get("ui_mock_duration")
    if not mid:
        await update.message.reply_text("❌ Пробник не найден. Откройте раздел заново.")
        return ConversationHandler.END
    mock_tests.complete(mid, primary_score=primary, test_score=score, duration_minutes=duration, result_comment=comment)
    await update.message.reply_text(
        "✅ Результат пробника сохранён.\n\n"
        f"📊 Тестовый балл: {score:g}\n"
        f"🧮 Первичный: {primary if primary is not None else '—'}\n"
        f"⏱ Время: {str(duration) + ' мин' if duration is not None else '—'}"
        + (f"\n💬 {comment}" if comment else "")
    )
    for key in ("ui_mock_mid", "ui_mock_test_score", "ui_mock_primary", "ui_mock_duration"):
        context.user_data.pop(key, None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Exam plan UI
# ---------------------------------------------------------------------------
async def plan_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _admin(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return ConversationHandler.END
    uid = int(q.data.split("|", 1)[1])
    context.user_data["ui_plan_uid"] = uid
    programs = [p for p in _programs(uid) if str(p["study_goal"]).upper() in ("EGE", "OGE")]
    if not programs:
        await _edit(q, "🎯 ПЛАН ЭКЗАМЕНА\n\nУ ученика нет активного направления ЕГЭ или ОГЭ.", _student_menu(uid))
        return ConversationHandler.END
    kb = [[InlineKeyboardButton(program_label(p), callback_data=f"ui_plan_program|{p['id']}")] for p in programs]
    kb.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"ff_student|{uid}")])
    await _edit(q, f"🎯 ПЛАН ЭКЗАМЕНА\n\nУченик: {_student_name(uid)}\n\nВыберите направление:", InlineKeyboardMarkup(kb))
    return PLAN_PROGRAM


async def plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data.startswith("ui_plan_program|"):
        pid = int(q.data.split("|", 1)[1])
        context.user_data["ui_plan_pid"] = pid
        await _edit(q, "📅 Введите дату экзамена.\n\nНапример: 05.06.2027")
        return PLAN_DATE
    return PLAN_PROGRAM


async def plan_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = _parse_date(update.message.text)
    if not parsed:
        await update.message.reply_text("Я не смогла распознать дату. Введите её, например, так: 05.06.2027")
        return PLAN_DATE
    if parsed <= datetime.now().date():
        await update.message.reply_text("❌ Дата экзамена должна быть в будущем.")
        return PLAN_DATE
    context.user_data["ui_plan_date"] = parsed.isoformat()
    await update.message.reply_text("🎯 Какой целевой тестовый балл?\n\nНапример: 85")
    return PLAN_TARGET


async def plan_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введите число, например: 85")
        return PLAN_TARGET
    if value <= 0 or value > 100:
        await update.message.reply_text("❌ Целевой балл должен быть от 1 до 100.")
        return PLAN_TARGET
    context.user_data["ui_plan_target"] = value
    await update.message.reply_text(
        "⏱ Сколько минут занятий в неделю планируется?\n\n"
        "Например: 180 — это два занятия по 90 минут."
    )
    return PLAN_WEEKLY_MINUTES


async def plan_weekly_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = int(update.message.text.strip())
        if minutes <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введите положительное количество минут, например: 180")
        return PLAN_WEEKLY_MINUTES
    uid = context.user_data.get("ui_plan_uid")
    pid = context.user_data.get("ui_plan_pid")
    exam_date = context.user_data.get("ui_plan_date")
    target = context.user_data.get("ui_plan_target")
    if not uid or not pid or not exam_date or target is None:
        await update.message.reply_text("❌ Данные плана потеряны. Откройте «План экзамена» заново.")
        return ConversationHandler.END
    summary = exam_plans.generate(uid, pid, exam_date, target_score=target, minutes_per_week=minutes)
    await update.message.reply_text("✅ Готово, я создала план подготовки 💜\n\n" + str(summary))
    for key in ("ui_plan_pid", "ui_plan_date", "ui_plan_target"):
        context.user_data.pop(key, None)
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Friendly display for tariffs and renewal center (single-click UI, no commands)
# ---------------------------------------------------------------------------
async def tariffs_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _admin(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return
    rows = tariffs.list_rules()
    groups = {}
    for row in rows:
        groups.setdefault((str(row["study_goal"]), int(row["base_duration_minutes"])), []).append(row)
    lines = [
        "⚙️ ТАРИФЫ И СКИДКИ",
        "",
        "Стоимость минуты рассчитывается из действующей цены ученика. Пакет считается в минутах.",
    ]
    for (goal, base), rules in groups.items():
        lines.append(f"\n{goal_ru(goal)} • стандарт {base} мин")
        for rule in rules:
            count = int(rule["equivalent_lessons"])
            minutes = count * base
            lines.append(f"• {count} зан. = {minutes} мин • скидка {int(rule['discount_percent'])}%")
    await _edit(q, "\n".join(lines), InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="ff_main")]]))


async def renewals_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _admin(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return
    users = _students()
    alerts = []
    buttons = []
    for user in users:
        for program in database.get_student_programs(user["id"], active_only=True, approved_only=True):
            try:
                rec = renewals.recommendation(user["id"], program["id"])
            except Exception:
                continue
            if rec["available_after_bookings"] <= 180:
                quote = rec["quote"]
                alerts.append(
                    f"⚠️ {user['name']} • {program_label(program)}\n"
                    f"Доступно после броней: {rec['available_after_bookings']} мин\n"
                    f"Рекомендация: {quote['minutes']} мин ≈ {quote['equivalent_lessons']} занятий • {quote['total']} ₽"
                )
                buttons.append([InlineKeyboardButton(f"👤 {user['name']} — подробнее", callback_data=f"ff_renew|{user['id']}")])
    if not alerts:
        await _edit(q, "📦 ПРОДЛЕНИЯ МИНУТ\n\n✅ Срочных продлений сейчас нет.", InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="ff_main")]]))
        return
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="ff_main")])
    await _edit(q, "📦 ПРОДЛЕНИЯ МИНУТ\n\n" + "\n\n".join(alerts), InlineKeyboardMarkup(buttons))


async def renewal_student_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _admin(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return
    uid = int(q.data.split("|", 1)[1])
    lines = [f"📦 ПРОДЛЕНИЕ МИНУТ\n\nУченик: {_student_name(uid)}"]
    for program in database.get_student_programs(uid, active_only=True, approved_only=True):
        try:
            rec = renewals.recommendation(uid, program["id"])
        except Exception:
            continue
        quote = rec["quote"]
        lines.append(
            f"\n{program_label(program)}\n"
            f"Баланс: {rec['balance']} мин\n"
            f"Зарезервировано: {rec['reserved']} мин\n"
            f"Доступно после броней: {rec['available_after_bookings']} мин\n"
            f"Рекомендовано: {quote['minutes']} мин ≈ {quote['equivalent_lessons']} занятий\n"
            f"Стоимость: {quote['total']} ₽ • скидка {quote['discount_percent']}%"
        )
    await _edit(q, "\n".join(lines), _student_menu(uid))


def handlers():
    mock_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(mock_entry, pattern=r"^ff_mocks_admin$"),
            CallbackQueryHandler(mock_entry, pattern=r"^ff_mocks\|"),
        ],
        states={
            MOCK_ACTION: [CallbackQueryHandler(mock_callback, pattern=r"^ui_mock_")],
            MOCK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_deadline)],
            MOCK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_title)],
            MOCK_TEST_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_test_score)],
            MOCK_PRIMARY_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_primary_score)],
            MOCK_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_duration)],
            MOCK_RESULT_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, mock_result_comment)],
        },
        fallbacks=[],
        allow_reentry=True,
        name="friendly_mock_ui",
        persistent=False,
    )
    plan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(plan_entry, pattern=r"^ff_plan\|")],
        states={
            PLAN_PROGRAM: [CallbackQueryHandler(plan_callback, pattern=r"^ui_plan_program\|")],
            PLAN_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_date)],
            PLAN_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_target)],
            PLAN_WEEKLY_MINUTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_weekly_minutes)],
        },
        fallbacks=[],
        allow_reentry=True,
        name="friendly_exam_plan_ui",
        persistent=False,
    )
    return [
        mock_conv,
        plan_conv,
        CallbackQueryHandler(tariffs_screen, pattern=r"^ff_tariffs$"),
        CallbackQueryHandler(renewals_screen, pattern=r"^ff_renewals$"),
        CallbackQueryHandler(renewal_student_screen, pattern=r"^ff_renew\|"),
    ]
