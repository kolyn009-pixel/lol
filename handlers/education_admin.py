from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles
import education_profile

GOALS = {
    "SCHOOL": "Повышение успеваемости",
    "OGE": "Подготовка к ОГЭ",
    "EGE": "Подготовка к ЕГЭ",
    "OLYMPIAD": "Олимпиадная подготовка",
}
SUBJECTS = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}


def initialize():
    education_profile.initialize()


def _admin(update):
    return bool(update.effective_user and admin_roles.is_admin_id(update.effective_user.id))


def _programs(uid, active_only=True):
    conn = database.connect()
    try:
        sql = "SELECT * FROM student_programs WHERE user_id=?"
        if active_only:
            sql += " AND active=1"
        sql += " ORDER BY is_primary DESC,id"
        return list(conn.execute(sql, (int(uid),)).fetchall())
    finally:
        conn.close()


def _sync_primary(uid):
    rows = _programs(uid)
    if not rows:
        return
    primary = next((r for r in rows if int(r["is_primary"] or 0)), rows[0])
    conn = database.connect()
    try:
        conn.execute(
            "UPDATE users SET study_goal=?, main_subject=?, updated_at=? WHERE id=?",
            (primary["study_goal"], primary["subject"], database.now_iso(), int(uid)),
        )
        conn.commit()
    finally:
        conn.close()


def _education_markup(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏫 Школа", callback_data=f"edu_type|{uid}|SCHOOL"), InlineKeyboardButton("🎓 Колледж", callback_data=f"edu_type|{uid}|COLLEGE")],
        [InlineKeyboardButton("⬅️ К ученику", callback_data=f"student_view|{uid}")],
    ])


def _level_markup(uid, etype):
    levels = range(5, 12) if etype == "SCHOOL" else range(1, 5)
    buttons = [InlineKeyboardButton((f"{x} класс" if etype == "SCHOOL" else f"{x} курс"), callback_data=f"edu_level|{uid}|{etype}|{x}") for x in levels]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edu_profile|{uid}")])
    return InlineKeyboardMarkup(rows)


def _program_markup(uid):
    rows = []
    for p in _programs(uid):
        star = "⭐ " if int(p["is_primary"] or 0) else "📚 "
        rows.append([InlineKeyboardButton(f"{star}{SUBJECTS.get(p['subject'],p['subject'])} · {GOALS.get(p['study_goal'],p['study_goal'])}", callback_data=f"edu_program|{p['id']}")])
    rows += [
        [InlineKeyboardButton("➕ Добавить направление", callback_data=f"edu_add|{uid}")],
        [InlineKeyboardButton("⬅️ К ученику", callback_data=f"student_view|{uid}")],
    ]
    return InlineKeyboardMarkup(rows)


def _program_actions(p):
    uid = int(p["user_id"])
    rows = [
        [InlineKeyboardButton("🎯 Сменить цель", callback_data=f"edu_goal_menu|{p['id']}"), InlineKeyboardButton("📖 Сменить предмет", callback_data=f"edu_subject_menu|{p['id']}")],
    ]
    if not int(p["is_primary"] or 0):
        rows.append([InlineKeyboardButton("⭐ Сделать основным", callback_data=f"edu_primary|{p['id']}")])
    rows.append([InlineKeyboardButton("🚫 Отключить", callback_data=f"edu_disable|{p['id']}")])
    rows.append([InlineKeyboardButton("⬅️ К направлениям", callback_data=f"edu_programs|{uid}")])
    return InlineKeyboardMarkup(rows)


def _get_program(pid):
    conn = database.connect()
    try:
        return conn.execute("SELECT * FROM student_programs WHERE id=?", (int(pid),)).fetchone()
    finally:
        conn.close()


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not str(q.data or "").startswith("edu_"):
        return
    if not _admin(update):
        await q.answer("Нет доступа", show_alert=True)
        return
    await q.answer()
    d = q.data

    if d.startswith("edu_profile|"):
        uid = int(d.split("|")[1]); user = database.get_user(uid); profile = education_profile.get(user)
        await q.edit_message_text(f"🎓 ОБУЧЕНИЕ\n\n👤 {user['name']}\nСейчас: {profile['label']}\n\nВыберите тип обучения. История занятий и оплат при переводе не меняется.", reply_markup=_education_markup(uid)); return

    if d.startswith("edu_type|"):
        _, uid, etype = d.split("|")
        await q.edit_message_text("Выберите класс:" if etype == "SCHOOL" else "Выберите курс колледжа:", reply_markup=_level_markup(int(uid), etype)); return

    if d.startswith("edu_level|"):
        _, uid, etype, level = d.split("|"); user = database.get_user(int(uid))
        profile = education_profile.set_profile(int(uid), etype, int(level))
        await q.edit_message_text(f"✅ {user['name']} переведён: {profile['label']}.\n\nПрошлые занятия, оплаты, ДЗ и статистика сохранены. Новая учебная ступень применяется дальше.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📚 Направления", callback_data=f"edu_programs|{uid}")],[InlineKeyboardButton("⬅️ К ученику", callback_data=f"student_view|{uid}")]])); return

    if d.startswith("edu_programs|"):
        uid = int(d.split("|")[1]); user = database.get_user(uid)
        await q.edit_message_text(f"📚 НАПРАВЛЕНИЯ\n\n👤 {user['name']}\n🎓 {education_profile.label(user)}\n\nЗдесь можно изменить цель/предмет, выбрать основное или добавить новое направление.", reply_markup=_program_markup(uid)); return

    if d.startswith("edu_program|"):
        p = _get_program(int(d.split("|")[1]))
        if not p: return
        await q.edit_message_text(f"📚 НАПРАВЛЕНИЕ\n\n{SUBJECTS.get(p['subject'],p['subject'])}\n{GOALS.get(p['study_goal'],p['study_goal'])}\n{'⭐ Основное' if p['is_primary'] else 'Дополнительное'}", reply_markup=_program_actions(p)); return

    if d.startswith("edu_goal_menu|"):
        pid = int(d.split("|")[1]); p = _get_program(pid)
        rows = [[InlineKeyboardButton(label, callback_data=f"edu_goal|{pid}|{key}")] for key,label in GOALS.items()]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edu_program|{pid}")])
        await q.edit_message_text("🎯 Выберите новую цель направления:", reply_markup=InlineKeyboardMarkup(rows)); return

    if d.startswith("edu_subject_menu|"):
        pid = int(d.split("|")[1])
        rows = [[InlineKeyboardButton(label, callback_data=f"edu_subject|{pid}|{key}")] for key,label in SUBJECTS.items()]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edu_program|{pid}")])
        await q.edit_message_text("📖 Выберите предмет:", reply_markup=InlineKeyboardMarkup(rows)); return

    if d.startswith("edu_goal|") or d.startswith("edu_subject|"):
        kind, pid, value = d.split("|"); p = _get_program(int(pid))
        if not p: return
        field = "study_goal" if kind == "edu_goal" else "subject"
        conn = database.connect()
        try:
            duplicate = conn.execute(f"SELECT id FROM student_programs WHERE user_id=? AND {field}=? AND id<>? AND study_goal=? AND subject=?", (int(p['user_id']), value, int(pid), value if field=='study_goal' else p['study_goal'], value if field=='subject' else p['subject'])).fetchone()
            if duplicate:
                await q.answer("Такое направление уже существует", show_alert=True); return
            conn.execute(f"UPDATE student_programs SET {field}=?, updated_at=? WHERE id=?", (value, database.now_iso(), int(pid))); conn.commit()
        finally: conn.close()
        _sync_primary(int(p['user_id']))
        await q.edit_message_text("✅ Направление обновлено. История прошлых занятий не изменена.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К направлениям", callback_data=f"edu_programs|{p['user_id']}")]])); return

    if d.startswith("edu_primary|"):
        pid = int(d.split("|")[1]); p = _get_program(pid)
        if not p: return
        conn = database.connect()
        try:
            conn.execute("UPDATE student_programs SET is_primary=0,updated_at=? WHERE user_id=?", (database.now_iso(), int(p['user_id'])))
            conn.execute("UPDATE student_programs SET is_primary=1,active=1,updated_at=? WHERE id=?", (database.now_iso(), pid)); conn.commit()
        finally: conn.close()
        _sync_primary(int(p['user_id']))
        await q.edit_message_text("⭐ Основное направление изменено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К направлениям", callback_data=f"edu_programs|{p['user_id']}")]])); return

    if d.startswith("edu_disable|"):
        pid = int(d.split("|")[1]); p = _get_program(pid)
        if not p: return
        active = _programs(int(p['user_id']))
        if len(active) <= 1:
            await q.answer("Нельзя отключить единственное активное направление", show_alert=True); return
        conn = database.connect()
        try:
            conn.execute("UPDATE student_programs SET active=0,is_primary=0,updated_at=? WHERE id=?", (database.now_iso(), pid)); conn.commit()
        finally: conn.close()
        _sync_primary(int(p['user_id']))
        await q.edit_message_text("🚫 Направление отключено. История сохранена.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К направлениям", callback_data=f"edu_programs|{p['user_id']}")]])); return

    if d.startswith("edu_add|"):
        uid = int(d.split("|")[1])
        rows = [[InlineKeyboardButton(label, callback_data=f"edu_add_subject|{uid}|{key}")] for key,label in SUBJECTS.items()]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edu_programs|{uid}")])
        await q.edit_message_text("➕ НОВОЕ НАПРАВЛЕНИЕ\n\nСначала выберите предмет:", reply_markup=InlineKeyboardMarkup(rows)); return

    if d.startswith("edu_add_subject|"):
        _, uid, subject = d.split("|")
        rows = [[InlineKeyboardButton(label, callback_data=f"edu_add_finish|{uid}|{subject}|{key}")] for key,label in GOALS.items()]
        rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"edu_add|{uid}")])
        await q.edit_message_text(f"📖 {SUBJECTS.get(subject,subject)}\n\nТеперь выберите цель:", reply_markup=InlineKeyboardMarkup(rows)); return

    if d.startswith("edu_add_finish|"):
        _, uid, subject, goal = d.split("|"); uid = int(uid)
        existing = _programs(uid)
        if any(p['subject']==subject and p['study_goal']==goal for p in existing):
            await q.answer("Такое направление уже есть", show_alert=True); return
        database.ensure_student_programs_for_user(uid, [{"study_goal":goal,"subject":subject,"is_primary":not bool(existing),"approval_status":"APPROVED","created_by":"ADMIN"}])
        _sync_primary(uid)
        await q.edit_message_text("✅ Новое направление добавлено.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К направлениям", callback_data=f"edu_programs|{uid}")]])); return


def handlers():
    initialize()
    return [CallbackQueryHandler(callback, pattern=r"^edu_")]
