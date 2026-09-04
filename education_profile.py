from __future__ import annotations

import database

SCHOOL = "SCHOOL"
COLLEGE = "COLLEGE"


def initialize():
    conn = database.connect()
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "education_type" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN education_type TEXT DEFAULT 'SCHOOL'")
        if "education_level" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN education_level INTEGER")
        if "education_updated_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN education_updated_at TEXT")
        conn.execute("UPDATE users SET education_type='SCHOOL' WHERE education_type IS NULL OR education_type='' ")
        conn.execute("UPDATE users SET education_level=grade WHERE education_level IS NULL AND education_type='SCHOOL'")
        conn.commit()
    finally:
        conn.close()


def get(user_or_id):
    initialize()
    user = database.get_user(int(user_or_id)) if isinstance(user_or_id, int) else user_or_id
    if not user:
        return {"type": SCHOOL, "level": None, "label": "—"}
    keys = set(user.keys()) if hasattr(user, "keys") else set()
    etype = str(user["education_type"] if "education_type" in keys and user["education_type"] else SCHOOL).upper()
    level = user["education_level"] if "education_level" in keys else None
    if level is None:
        level = user["grade"] if "grade" in keys else None
    try:
        level = int(level)
    except Exception:
        level = None
    return {"type": etype, "level": level, "label": label_values(etype, level)}


def label_values(education_type, level):
    if str(education_type).upper() == COLLEGE:
        return f"Колледж · {int(level)} курс" if level else "Колледж"
    return f"{int(level)} класс" if level else "Школа"


def label(user_or_id):
    return get(user_or_id)["label"]


def set_profile(user_id: int, education_type: str, level: int):
    initialize()
    education_type = str(education_type or SCHOOL).upper()
    level = int(level)
    if education_type == SCHOOL and not 5 <= level <= 11:
        raise ValueError("Школьный класс должен быть от 5 до 11.")
    if education_type == COLLEGE and not 1 <= level <= 4:
        raise ValueError("Курс колледжа должен быть от 1 до 4.")

    # grade remains a compatibility field for legacy pricing/schedule code.
    compatibility_grade = level if education_type == SCHOOL else 11
    conn = database.connect()
    try:
        conn.execute(
            """
            UPDATE users
            SET education_type=?, education_level=?, grade=?, education_updated_at=?, updated_at=?
            WHERE id=?
            """,
            (education_type, level, compatibility_grade, database.now_iso(), database.now_iso(), int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()
    return get(int(user_id))


def formula_grades(user_id: int, library):
    profile = get(int(user_id))
    grades = sorted(library.keys(), reverse=(profile["type"] == COLLEGE))
    if profile["type"] == SCHOOL and profile["level"] in grades:
        grades.remove(profile["level"])
        grades.insert(0, profile["level"])
    return grades


def _goal_keyboard(bot, education_type, level):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    if education_type == COLLEGE:
        rows.append([InlineKeyboardButton("📚 Учёба по программе колледжа", callback_data="reggoal|SCHOOL")])
        rows.append([InlineKeyboardButton("🎯 Подготовка к ЕГЭ", callback_data="reggoal|EGE")])
        rows.append([InlineKeyboardButton("🏆 Олимпиадная подготовка", callback_data="reggoal|OLYMPIAD")])
    else:
        rows.append([InlineKeyboardButton("📚 Повышение успеваемости", callback_data="reggoal|SCHOOL")])
        if int(level) == 9:
            rows.append([InlineKeyboardButton("🎯 Подготовка к ОГЭ", callback_data="reggoal|OGE")])
        if int(level) >= 10:
            rows.append([InlineKeyboardButton("🎯 Подготовка к ЕГЭ", callback_data="reggoal|EGE")])
        rows.append([InlineKeyboardButton("🏆 Олимпиадная подготовка", callback_data="reggoal|OLYMPIAD")])
    return InlineKeyboardMarkup(rows)


def install_runtime():
    """Patch registration before the ConversationHandler is constructed in bot.main()."""
    import __main__ as bot
    if not hasattr(bot, "registration_name") or getattr(bot, "_education_profile_installed", False):
        return
    initialize()

    from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ConversationHandler

    async def registration_name(update, context):
        name = (update.message.text or "").strip()
        if len(name) < 2:
            await update.message.reply_text("Кажется, имя получилось слишком коротким. Напиши его ещё раз, пожалуйста 💜")
            return bot.REG_NAME
        context.user_data["reg_name"] = name
        context.user_data.pop("reg_education_type", None)
        context.user_data.pop("reg_education_level", None)
        await update.message.reply_text(
            "Где ты сейчас учишься? 🎓",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("🏫 Школа"), KeyboardButton("🎓 Колледж")]],
                resize_keyboard=True,
                one_time_keyboard=True,
            ),
        )
        return bot.REG_GRADE

    async def registration_grade(update, context):
        value = (update.message.text or "").strip()
        etype = context.user_data.get("reg_education_type")
        if not etype:
            low = value.lower()
            if "колледж" in low:
                etype = COLLEGE
                context.user_data["reg_education_type"] = etype
                await update.message.reply_text(
                    "На каком ты курсе?",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("1"), KeyboardButton("2")], [KeyboardButton("3"), KeyboardButton("4")]],
                        resize_keyboard=True,
                        one_time_keyboard=True,
                    ),
                )
                return bot.REG_GRADE
            if "школ" in low:
                etype = SCHOOL
                context.user_data["reg_education_type"] = etype
                await update.message.reply_text("В каком ты классе? Введи число от 5 до 11.", reply_markup=ReplyKeyboardRemove())
                return bot.REG_GRADE
            await update.message.reply_text("Выбери: 🏫 Школа или 🎓 Колледж.")
            return bot.REG_GRADE

        try:
            level = int(value)
        except ValueError:
            await update.message.reply_text("Напиши номер класса или курса числом 💜")
            return bot.REG_GRADE
        if etype == SCHOOL and not 5 <= level <= 11:
            await update.message.reply_text("Для школы выбери класс от 5 до 11 💜")
            return bot.REG_GRADE
        if etype == COLLEGE and not 1 <= level <= 4:
            await update.message.reply_text("Для колледжа выбери курс от 1 до 4 💜")
            return bot.REG_GRADE

        context.user_data["reg_education_level"] = level
        context.user_data["reg_grade"] = level if etype == SCHOOL else 11
        await update.message.reply_text(
            "Отлично! Теперь выбери цель занятий 👇",
            reply_markup=_goal_keyboard(bot, etype, level),
        )
        return bot.REG_GOAL

    async def registration_phone(update, context):
        phone = None
        if update.message.contact:
            phone = update.message.contact.phone_number
        elif update.message.text and update.message.text.strip().lower() != "пропустить":
            phone = update.message.text.strip()

        tg = update.effective_user
        try:
            user_id = database.add_telegram_user(
                telegram_id=tg.id,
                telegram_username=tg.username,
                name=context.user_data["reg_name"],
                grade=context.user_data["reg_grade"],
                phone=phone,
                study_goal=context.user_data["reg_programs"][0]["study_goal"],
                main_subject=context.user_data["reg_programs"][0]["subject"],
            )
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
                    for index, item in enumerate(context.user_data["reg_programs"])
                ],
            )
            set_profile(
                user_id,
                context.user_data.get("reg_education_type", SCHOOL),
                context.user_data.get("reg_education_level", context.user_data["reg_grade"]),
            )
        except Exception as error:
            print("REG EDUCATION ERROR:", repr(error))
            await update.message.reply_text(
                "❌ Я не смогла создать профиль. Попробуй ещё раз чуть позже или напиши преподавателю 💜",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        user = database.get_user(user_id)
        await update.message.reply_text("✅ Регистрация завершена!", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(
            f"👤 {user['name']}\n🎓 {label(user)}\n\n🎁 Первое пробное занятие доступно бесплатно.",
            reply_markup=bot.student_menu(user["id"]),
        )
        try:
            database.mark_timezone_notified(int(tg.id))
            await update.message.reply_text(
                "💜 И ещё один важный шаг — выбери своё время. Тогда расписание и свободные окна я буду показывать именно по твоему часовому поясу.",
                reply_markup=bot.timezone_handlers.timezone_markup(int(tg.id), include_back=False),
            )
        except Exception as error:
            print("REG TIMEZONE PROMPT ERROR:", repr(error))
        program_lines = [f"Направление: {bot.program_title(x['study_goal'], x['subject'])}" for x in context.user_data.get("reg_programs", [])]
        await bot.notify_admin_registration(
            context,
            "Ученик",
            user["name"],
            tg,
            phone,
            [f"Обучение: {label(user)}"] + program_lines,
        )
        context.user_data.clear()
        return ConversationHandler.END

    original_show_formula_grades = getattr(bot, "show_formula_grades", None)
    async def show_formula_grades(query, user):
        if not original_show_formula_grades:
            return
        profile = get(user)
        if profile["type"] != COLLEGE:
            return await original_show_formula_grades(query, user)
        grades = sorted(bot.FORMULA_LIBRARY.keys(), reverse=True)
        keyboard = [[InlineKeyboardButton(f"{grade} класс", callback_data=f"formula_grade|{grade}")] for grade in grades]
        keyboard.append([InlineKeyboardButton("🎓 Формулы ЕГЭ", callback_data="ege_formulas")])
        keyboard.append([InlineKeyboardButton("🧲 Физические константы", callback_data="reference_physics")])
        keyboard.append([InlineKeyboardButton("🧪 Химические таблицы", callback_data="reference_chemistry")])
        keyboard.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="main")])
        await query.edit_message_text(
            f"📚 Формулы и справочники\n\n🎓 {profile['label']}\n\nДля колледжа доступны все школьные разделы, ЕГЭ, физические константы и химические таблицы.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    bot.registration_name = registration_name
    bot.registration_grade = registration_grade
    bot.registration_phone = registration_phone
    if original_show_formula_grades:
        bot.show_formula_grades = show_formula_grades
    bot._education_profile_installed = True
