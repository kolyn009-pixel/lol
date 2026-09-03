from __future__ import annotations

import random
import re
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from formula_library import FORMULA_LIBRARY

SEARCH = 781

SUBJECT_LABELS = {"PHYSICS": "📘 Физика", "CHEMISTRY": "🧪 Химия"}

# Short human explanations for the most common school topics. The original
# formula library remains the source of truth; these notes only make cards
# easier to understand.
TOPIC_GUIDANCE = {
    ("PHYSICS", "MOTION"): ("Связывает путь, время и скорость движения.", "Используй, когда в задаче известны любые две из величин s, v, t."),
    ("PHYSICS", "FORCES"): ("Формулы описывают основные силы: тяжести, упругости и трения.", "Сначала нарисуй силы, затем выбери зависимость для нужной силы."),
    ("PHYSICS", "PRESSURE"): ("Связывает давление с силой, площадью и глубиной в жидкости.", "Проверь, о твёрдом теле или жидкости идёт речь."),
    ("PHYSICS", "WORK_ENERGY"): ("Работа показывает передачу энергии, а мощность — скорость этой передачи.", "Следи за единицами: работа и энергия в джоулях, мощность в ваттах."),
    ("PHYSICS", "HEAT"): ("Формулы тепловых процессов: нагрев, плавление, парообразование и сгорание.", "Сначала определи процесс: температура меняется или агрегатное состояние меняется."),
    ("PHYSICS", "CURRENT"): ("Основные зависимости электрической цепи: ток, напряжение и сопротивление.", "Для участка цепи чаще всего начинай с закона Ома I = U/R."),
    ("PHYSICS", "POWER_CURRENT"): ("Работа и мощность электрического тока.", "Выбирай форму P = UI, I²R или U²/R по тем величинам, которые даны."),
    ("PHYSICS", "OPTICS"): ("Формулы отражения, преломления и тонкой линзы.", "Для линзы аккуратно различай расстояние до предмета d и до изображения f."),
    ("PHYSICS", "KINEMATICS"): ("Описывает положение, скорость и ускорение тела во времени.", "Сначала выбери ось и знаки проекций, затем подставляй в формулы."),
    ("PHYSICS", "DYNAMICS"): ("Связывает движение тела с силами, которые на него действуют.", "Начни с рисунка сил и записи ΣF = ma по выбранной оси."),
    ("PHYSICS", "STATICS"): ("Условия равновесия тела по силам и моментам.", "Для равновесия одновременно проверяй сумму сил и сумму моментов."),
    ("PHYSICS", "THERMO"): ("Тепловые процессы и первое начало термодинамики.", "Определи, получает или отдаёт система тепло и совершает ли газ работу."),
    ("PHYSICS", "ELECTROSTATICS"): ("Заряды, электрическое поле, потенциал и конденсаторы.", "Разделяй векторные величины (E, F) и скалярные (φ, U)."),
    ("CHEMISTRY", "AR_MR"): ("Помогает находить относительные и молярные массы веществ.", "Сначала правильно прочитай индексы в формуле вещества."),
    ("CHEMISTRY", "AMOUNT"): ("Связывает массу, молярную массу, число частиц и количество вещества.", "Количество вещества ν обычно удобно находить первым шагом расчёта."),
}

STOPWORDS = {"как", "найти", "формула", "формулу", "для", "что", "это", "по", "из", "и", "в", "на"}


def _connect():
    return database.connect()


def initialize():
    c = _connect()
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS formula_favorites (
                user_id INTEGER NOT NULL,
                grade INTEGER NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, grade, subject, topic)
            );
            CREATE TABLE IF NOT EXISTS formula_recent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                grade INTEGER NOT NULL,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_formula_recent_user ON formula_recent(user_id, opened_at DESC);
            CREATE TABLE IF NOT EXISTS formula_quiz_stats (
                user_id INTEGER PRIMARY KEY,
                correct INTEGER NOT NULL DEFAULT 0,
                total INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        c.commit()
    finally:
        c.close()


def _user_from_update(update: Update):
    if not update.effective_user:
        return None
    return database.get_user_by_telegram_id(update.effective_user.id)


def _grade(user) -> int | None:
    try:
        return int(str(user["grade"]).split()[0])
    except Exception:
        return None


def _norm(text: str) -> str:
    return re.sub(r"[^a-zа-яё0-9=+\-*/ρνμωφΔ]+", " ", (text or "").lower()).strip()


def _query_tokens(text: str):
    return [x for x in _norm(text).split() if x not in STOPWORDS and len(x) > 1]


def _topic_rows() -> Iterable[tuple[int, str, str, dict]]:
    for grade, subjects in FORMULA_LIBRARY.items():
        for subject, topics in subjects.items():
            for key, item in topics.items():
                yield grade, subject, key, item


def _score(query: str, grade: int, subject: str, key: str, item: dict) -> int:
    q = _norm(query)
    tokens = _query_tokens(query)
    hay = _norm(f"{item.get('title','')} {item.get('text','')} {grade} {subject} {key}")
    if not tokens:
        return 0
    score = 0
    if q and q in hay:
        score += 20
    title = _norm(item.get("title", ""))
    for token in tokens:
        if token in title:
            score += 8
        elif token in hay:
            score += 3
    # Common Russian intent aliases.
    aliases = {
        "сопротивлен": ["сопротивление", "r =", "закон ома"],
        "скорост": ["скорость", "v ="],
        "плотност": ["плотность", "ρ ="],
        "давлен": ["давление", "p ="],
        "ток": ["сила тока", "i ="],
        "моляр": ["молярная", "моль"],
        "количеств веществ": ["количество вещества", "ν ="],
    }
    for needle, hints in aliases.items():
        if needle in q and any(h in hay for h in hints):
            score += 12
    return score


def _formula_lines(text: str) -> list[str]:
    out = []
    for raw in (text or "").splitlines():
        line = raw.strip(" •\t")
        if "=" not in line or len(line) > 100:
            continue
        if line.startswith(("Для ", "Если ", "Условие", "Последовательно", "Параллельно")):
            continue
        out.append(line)
    return out[:8]


def _is_favorite(user_id: int, grade: int, subject: str, topic: str) -> bool:
    c = _connect()
    try:
        row = c.execute(
            "SELECT 1 FROM formula_favorites WHERE user_id=? AND grade=? AND subject=? AND topic=?",
            (user_id, grade, subject, topic),
        ).fetchone()
        return bool(row)
    finally:
        c.close()


def _toggle_favorite(user_id: int, grade: int, subject: str, topic: str) -> bool:
    c = _connect()
    try:
        row = c.execute(
            "SELECT 1 FROM formula_favorites WHERE user_id=? AND grade=? AND subject=? AND topic=?",
            (user_id, grade, subject, topic),
        ).fetchone()
        if row:
            c.execute(
                "DELETE FROM formula_favorites WHERE user_id=? AND grade=? AND subject=? AND topic=?",
                (user_id, grade, subject, topic),
            )
            state = False
        else:
            c.execute(
                "INSERT OR IGNORE INTO formula_favorites(user_id,grade,subject,topic) VALUES(?,?,?,?)",
                (user_id, grade, subject, topic),
            )
            state = True
        c.commit()
        return state
    finally:
        c.close()


def _remember(user_id: int, grade: int, subject: str, topic: str):
    c = _connect()
    try:
        c.execute("INSERT INTO formula_recent(user_id,grade,subject,topic) VALUES(?,?,?,?)", (user_id, grade, subject, topic))
        c.execute(
            "DELETE FROM formula_recent WHERE user_id=? AND id NOT IN (SELECT id FROM formula_recent WHERE user_id=? ORDER BY id DESC LIMIT 30)",
            (user_id, user_id),
        )
        c.commit()
    finally:
        c.close()


def _quiz_stats(user_id: int):
    c = _connect()
    try:
        row = c.execute("SELECT correct,total FROM formula_quiz_stats WHERE user_id=?", (user_id,)).fetchone()
        return (int(row[0]), int(row[1])) if row else (0, 0)
    finally:
        c.close()


def _record_quiz(user_id: int, correct: bool):
    c = _connect()
    try:
        c.execute(
            "INSERT INTO formula_quiz_stats(user_id,correct,total) VALUES(?,?,1) "
            "ON CONFLICT(user_id) DO UPDATE SET correct=correct+excluded.correct,total=total+1,updated_at=CURRENT_TIMESTAMP",
            (user_id, 1 if correct else 0),
        )
        c.commit()
    finally:
        c.close()


def _home_markup(user):
    g = _grade(user)
    rows = []
    if g in FORMULA_LIBRARY:
        rows.append([InlineKeyboardButton(f"🎓 {g} класс • мой", callback_data=f"fh_grade|{g}")])
    rows += [
        [InlineKeyboardButton("🔎 Найти формулу", callback_data="fh_search")],
        [InlineKeyboardButton("⭐ Избранные", callback_data="fh_favorites"), InlineKeyboardButton("🕘 Недавние", callback_data="fh_recent")],
        [InlineKeyboardButton("🎓 Выбрать другой класс", callback_data="fh_grades")],
        [InlineKeyboardButton("🧠 Проверить себя", callback_data="fh_quiz")],
        [InlineKeyboardButton("🎓 Формулы ЕГЭ", callback_data="ege_formulas")],
        [InlineKeyboardButton("🧲 Физический справочник", callback_data="reference_physics"), InlineKeyboardButton("🧪 Химический справочник", callback_data="reference_chemistry")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="global_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ]
    return InlineKeyboardMarkup(rows)


async def show_home(query, user):
    g = _grade(user)
    correct, total = _quiz_stats(int(user["id"]))
    progress = f"\n🧠 Самопроверка: {correct}/{total} правильных" if total else ""
    class_line = f"🎓 Сначала показываю материалы {g} класса." if g in FORMULA_LIBRARY else "🎓 Выберите нужный класс."
    await query.edit_message_text(
        "🧮 ФОРМУЛЫ И СПРАВОЧНИК\n\n"
        f"{class_line}\n"
        "Можно открыть любой другой класс или найти формулу по названию, величине, теме или самой записи формулы.\n\n"
        "Физика и химия — без жёсткого ограничения по вашему классу."
        f"{progress}",
        reply_markup=_home_markup(user),
    )


async def _show_grades(q, user):
    current = _grade(user)
    rows = []
    grades = sorted(FORMULA_LIBRARY)
    for i in range(0, len(grades), 2):
        row = []
        for g in grades[i:i+2]:
            label = f"✓ {g} класс" if g == current else f"{g} класс"
            row.append(InlineKeyboardButton(label, callback_data=f"fh_grade|{g}"))
        rows.append(row)
    rows += [[InlineKeyboardButton("🔎 Найти формулу", callback_data="fh_search")], [InlineKeyboardButton("⬅️ Назад", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    await q.edit_message_text("🎓 ФОРМУЛЫ ПО КЛАССАМ\n\nТекущий класс — только удобный старт. Можно смотреть материалы любого года.", reply_markup=InlineKeyboardMarkup(rows))


async def _show_grade(q, user, grade: int):
    subjects = FORMULA_LIBRARY.get(grade, {})
    rows = [[InlineKeyboardButton(SUBJECT_LABELS.get(s, s), callback_data=f"fh_subject|{grade}|{s}")] for s in subjects]
    rows += [[InlineKeyboardButton("🔎 Поиск по всем классам", callback_data="fh_search")], [InlineKeyboardButton("⬅️ К классам", callback_data="fh_grades"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    marker = " • ваш класс" if grade == _grade(user) else ""
    await q.edit_message_text(f"🧮 ФОРМУЛЫ • {grade} КЛАСС{marker}\n\nВыберите предмет. Все карточки содержат формулы, пояснение и подсказку по применению.", reply_markup=InlineKeyboardMarkup(rows))


async def _show_subject(q, grade: int, subject: str):
    topics = FORMULA_LIBRARY.get(grade, {}).get(subject, {})
    rows = [[InlineKeyboardButton(item["title"], callback_data=f"fh_topic|{grade}|{subject}|{key}")] for key, item in topics.items()]
    rows += [[InlineKeyboardButton("🔎 Найти формулу", callback_data="fh_search")], [InlineKeyboardButton("⬅️ Назад", callback_data=f"fh_grade|{grade}"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    await q.edit_message_text(f"{SUBJECT_LABELS.get(subject, subject)} • {grade} КЛАСС\n\nВыберите тему 👇", reply_markup=InlineKeyboardMarkup(rows))


def _topic_text(grade: int, subject: str, topic: str, item: dict) -> str:
    explain, usage = TOPIC_GUIDANCE.get((subject, topic), (
        f"Эта карточка собирает основные зависимости темы «{item.get('title','')}» в одном месте.",
        "Сначала определите, какие величины известны, приведите их к единицам СИ и выберите формулу с нужной неизвестной.",
    ))
    lines = _formula_lines(item.get("text", ""))
    formula_block = "\n".join(f"• {x}" for x in lines) if lines else "• Основные зависимости приведены ниже в исходной памятке."
    original = item.get("text", "").strip()
    # Avoid duplicating huge topic text; keep the authoritative sheet after the explanation.
    if len(original) > 1700:
        original = original[:1700].rsplit("\n", 1)[0] + "\n…"
    return (
        f"🧮 {item.get('title','Формулы').upper()}\n"
        f"🎓 {grade} класс • {SUBJECT_LABELS.get(subject, subject)}\n\n"
        f"🔢 Основные формулы:\n{formula_block}\n\n"
        f"📖 Что это значит\n{explain}\n\n"
        f"💡 Когда использовать\n{usage}\n\n"
        f"📚 Памятка по теме\n{original}"
    )[:3900]


async def _show_topic(q, user, grade: int, subject: str, topic: str):
    item = FORMULA_LIBRARY.get(grade, {}).get(subject, {}).get(topic)
    if not item:
        await q.answer("Материал пока недоступен.", show_alert=True)
        return
    uid = int(user["id"])
    _remember(uid, grade, subject, topic)
    fav = _is_favorite(uid, grade, subject, topic)
    rows = [
        [InlineKeyboardButton("★ Убрать из избранного" if fav else "⭐ В избранное", callback_data=f"fh_fav|{grade}|{subject}|{topic}")],
        [InlineKeyboardButton("🧠 Проверить себя", callback_data=f"fh_quiz_topic|{grade}|{subject}|{topic}")],
        [InlineKeyboardButton("🔎 Найти другую", callback_data="fh_search")],
        [InlineKeyboardButton("⬅️ К темам", callback_data=f"fh_subject|{grade}|{subject}"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ]
    await q.edit_message_text(_topic_text(grade, subject, topic, item), reply_markup=InlineKeyboardMarkup(rows))


async def _show_favorites(q, user):
    c = _connect()
    try:
        rows_db = c.execute("SELECT grade,subject,topic FROM formula_favorites WHERE user_id=? ORDER BY created_at DESC LIMIT 20", (int(user["id"]),)).fetchall()
    finally:
        c.close()
    rows = []
    for grade, subject, topic in rows_db:
        item = FORMULA_LIBRARY.get(int(grade), {}).get(subject, {}).get(topic)
        if item:
            rows.append([InlineKeyboardButton(f"⭐ {grade} • {item['title']}", callback_data=f"fh_topic|{grade}|{subject}|{topic}")])
    rows += [[InlineKeyboardButton("⬅️ Назад", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    text = "⭐ ИЗБРАННЫЕ ФОРМУЛЫ\n\n" + ("Ваши сохранённые темы — всё под рукой." if rows_db else "Здесь пока пусто. Откройте формулу и нажмите «⭐ В избранное».")
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def _show_recent(q, user):
    c = _connect()
    try:
        rows_db = c.execute("SELECT grade,subject,topic,MAX(id) AS mid FROM formula_recent WHERE user_id=? GROUP BY grade,subject,topic ORDER BY mid DESC LIMIT 12", (int(user["id"]),)).fetchall()
    finally:
        c.close()
    rows = []
    for grade, subject, topic, _ in rows_db:
        item = FORMULA_LIBRARY.get(int(grade), {}).get(subject, {}).get(topic)
        if item:
            rows.append([InlineKeyboardButton(f"🕘 {grade} • {item['title']}", callback_data=f"fh_topic|{grade}|{subject}|{topic}")])
    rows += [[InlineKeyboardButton("⬅️ Назад", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    await q.edit_message_text("🕘 НЕДАВНИЕ ФОРМУЛЫ\n\nБыстрый возврат к тому, что вы открывали недавно.", reply_markup=InlineKeyboardMarkup(rows))


async def _search_results(q, user, text: str):
    scored = []
    for grade, subject, topic, item in _topic_rows():
        s = _score(text, grade, subject, topic, item)
        if s:
            scored.append((s, grade, subject, topic, item))
    scored.sort(key=lambda x: (-x[0], x[1], x[4].get("title", "")))
    rows = [[InlineKeyboardButton(f"{grade} • {item['title']}", callback_data=f"fh_topic|{grade}|{subject}|{topic}")] for _, grade, subject, topic, item in scored[:10]]
    rows += [[InlineKeyboardButton("🔎 Новый поиск", callback_data="fh_search")], [InlineKeyboardButton("⬅️ Формулы", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
    if scored:
        msg = f"🔎 НАЙДЕНО: «{text[:80]}»\n\nПоказываю самые подходящие темы. Поиск работает по названию, формуле, величинам и тексту памятки."
    else:
        msg = f"🔎 По запросу «{text[:80]}» ничего не нашла.\n\nПопробуйте название величины, темы или саму формулу — например: «сопротивление», «плотность», «I = U/R»."
    await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(rows))


def _quiz_options(target_grade: int, target_subject: str, target_topic: str):
    target = FORMULA_LIBRARY[target_grade][target_subject][target_topic]
    pool = [(g, s, t, i) for g, s, t, i in _topic_rows() if s == target_subject and (g, t) != (target_grade, target_topic)]
    random.shuffle(pool)
    chosen = [(target_grade, target_subject, target_topic, target)] + pool[:2]
    random.shuffle(chosen)
    return chosen


async def _quiz(q, user, grade=None, subject=None, topic=None):
    if not topic:
        g = _grade(user)
        candidates = [(gg, s, t, i) for gg, s, t, i in _topic_rows() if gg == g] or list(_topic_rows())
        grade, subject, topic, item = random.choice(candidates)
    else:
        item = FORMULA_LIBRARY.get(int(grade), {}).get(subject, {}).get(topic)
        if not item:
            await q.answer("Материал недоступен.", show_alert=True); return
    formulas = _formula_lines(item.get("text", ""))
    clue = random.choice(formulas) if formulas else item.get("title", "")
    opts = _quiz_options(int(grade), subject, topic)
    rows = []
    for gg, ss, tt, ii in opts:
        ok = 1 if (gg == int(grade) and ss == subject and tt == topic) else 0
        rows.append([InlineKeyboardButton(ii["title"], callback_data=f"fh_quiz_answer|{ok}|{grade}|{subject}|{topic}")])
    rows.append([InlineKeyboardButton("⬅️ Формулы", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")])
    await q.edit_message_text(f"🧠 БЫСТРАЯ САМОПРОВЕРКА\n\nК какой теме относится формула или зависимость?\n\n{clue}\n\nВыберите тему:", reply_markup=InlineKeyboardMarkup(rows))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = _user_from_update(update)
    if not user:
        await q.edit_message_text("Сначала нажмите /start, чтобы открыть учебный кабинет 💜")
        return ConversationHandler.END
    d = q.data or ""
    if d in ("fh_home", "fh_study"):
        if d == "fh_study":
            g = _grade(user)
            correct, total = _quiz_stats(int(user["id"]))
            fav_count = 0
            c = _connect()
            try:
                fav_count = c.execute("SELECT COUNT(*) FROM formula_favorites WHERE user_id=?", (int(user["id"]),)).fetchone()[0]
            finally:
                c.close()
            rows = [[InlineKeyboardButton("🧮 Формулы", callback_data="fh_home"), InlineKeyboardButton("🔎 Поиск", callback_data="fh_search")], [InlineKeyboardButton("⭐ Избранные", callback_data="fh_favorites"), InlineKeyboardButton("🧠 Самопроверка", callback_data="fh_quiz")], [InlineKeyboardButton("⬅️ Назад", callback_data="global_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]
            await q.edit_message_text(f"📚 МОЯ УЧЁБА\n\n🎓 Текущий класс: {g or '—'}\n⭐ Избранных тем: {fav_count}\n🧠 Самопроверка: {correct}/{total}\n\nЗдесь собраны формулы и справочник. В следующих этапах сюда добавятся ДЗ, темы и прогресс.", reply_markup=InlineKeyboardMarkup(rows))
        else:
            await show_home(q, user)
        return ConversationHandler.END
    if d == "fh_grades": await _show_grades(q, user); return ConversationHandler.END
    if d.startswith("fh_grade|"):
        await _show_grade(q, user, int(d.split("|",1)[1])); return ConversationHandler.END
    if d.startswith("fh_subject|"):
        _, g, s = d.split("|",2); await _show_subject(q, int(g), s); return ConversationHandler.END
    if d.startswith("fh_topic|"):
        _, g, s, t = d.split("|",3); await _show_topic(q, user, int(g), s, t); return ConversationHandler.END
    if d.startswith("fh_fav|"):
        _, g, s, t = d.split("|",3); _toggle_favorite(int(user["id"]), int(g), s, t); await _show_topic(q, user, int(g), s, t); return ConversationHandler.END
    if d == "fh_favorites": await _show_favorites(q, user); return ConversationHandler.END
    if d == "fh_recent": await _show_recent(q, user); return ConversationHandler.END
    if d == "fh_search":
        context.user_data["formula_search_return"] = "fh_home"
        await q.edit_message_text("🔎 ПОИСК ФОРМУЛ\n\nНапишите название темы, величины или саму формулу.\n\nНапример:\n• закон Ома\n• сопротивление\n• плотность\n• количество вещества\n• I = U/R\n\nПоиск работает без ИИ и не расходует OpenRouter.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="fh_home")]]))
        return SEARCH
    if d == "fh_quiz": await _quiz(q, user); return ConversationHandler.END
    if d.startswith("fh_quiz_topic|"):
        _, g, s, t = d.split("|",3); await _quiz(q, user, int(g), s, t); return ConversationHandler.END
    if d.startswith("fh_quiz_answer|"):
        _, ok, g, s, t = d.split("|",4); good = ok == "1"; _record_quiz(int(user["id"]), good)
        item = FORMULA_LIBRARY.get(int(g), {}).get(s, {}).get(t, {})
        text = "✅ Верно!" if good else f"❌ Не совсем. Правильная тема: {item.get('title','—')}"
        correct,total = _quiz_stats(int(user["id"]))
        await q.edit_message_text(f"{text}\n\n🧠 Результат самопроверки: {correct}/{total}\n\nХотите ещё один вопрос?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Ещё вопрос", callback_data="fh_quiz")],[InlineKeyboardButton("🧮 Открыть тему", callback_data=f"fh_topic|{g}|{s}|{t}")],[InlineKeyboardButton("⬅️ Формулы", callback_data="fh_home"), InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]))
        return ConversationHandler.END
    return ConversationHandler.END


async def search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _user_from_update(update)
    if not user:
        return ConversationHandler.END
    text = (update.message.text or "").strip()
    # A normal message cannot be edited, so send the result as a new compact screen.
    class Dummy:
        async def edit_message_text(self, text, reply_markup=None):
            await update.message.reply_text(text, reply_markup=reply_markup)
    await _search_results(Dummy(), user, text)
    return ConversationHandler.END


def handlers():
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callbacks, pattern=r"^fh_search$")],
        states={SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_text), CallbackQueryHandler(callbacks, pattern=r"^fh_home$")]},
        fallbacks=[],
        allow_reentry=True,
    )
    return [conv, CallbackQueryHandler(callbacks, pattern=r"^fh_")]
