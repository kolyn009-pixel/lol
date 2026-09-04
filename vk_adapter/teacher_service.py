from __future__ import annotations

from datetime import datetime, timedelta

import database
from crm_plus import service as crm_service

from . import channel_delivery, schema

SUBJECT_NAMES = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}


def is_teacher(vk_id: int):
    return schema.get_admin_telegram_id("VK", str(vk_id))


def home_text():
    try:
        d = crm_service.today_dashboard()
        lessons = len(d.get("lessons") or [])
        unpaid = int(d.get("unpaid") or 0)
        attention = len(d.get("attention") or [])
    except Exception:
        lessons = unpaid = attention = 0
    try:
        unread = int(crm_service.message_counts().get("unread") or 0)
    except Exception:
        unread = 0
    return (
        "💜 АДЕЛИЯ • ПРЕПОДАВАТЕЛЬ\n\n"
        f"📅 Сегодня занятий: {lessons}\n"
        f"💬 Ждут ответа: {unread}\n"
        f"💳 Ожидают оплаты: {unpaid}\n"
        f"⚠️ Требуют внимания: {attention}\n\n"
        "Выберите действие 👇"
    )


def today_lessons(limit=12):
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT l.id,l.user_id,l.start_time,l.duration,l.subject,l.lesson_status,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.start_time>=? AND l.start_time<?
              AND l.cancelled_at IS NULL
              AND l.lesson_status NOT IN ('CANCELLED','REJECTED')
            ORDER BY l.start_time
            LIMIT ?
            """,
            (start, end, int(limit)),
        ).fetchall()
        return list(rows)
    finally:
        c.close()


def lesson_text(row):
    dt = datetime.fromisoformat(str(row["start_time"]))
    subject = SUBJECT_NAMES.get(str(row["subject"] or "").upper(), str(row["subject"] or "Занятие"))
    return f"{dt:%H:%M} · {row['name']} · {subject}"


def active_students(limit=40):
    c = database.connect()
    try:
        return list(c.execute(
            "SELECT id,name,grade,main_subject,study_goal,telegram_id FROM users WHERE active=1 ORDER BY name LIMIT ?",
            (int(limit),),
        ).fetchall())
    finally:
        c.close()


def student_programs(user_id: int):
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT id,user_id,study_goal,subject,is_primary
            FROM student_programs
            WHERE user_id=? AND active=1
            ORDER BY is_primary DESC,id
            """,
            (int(user_id),),
        ).fetchall()
        return list(rows)
    finally:
        c.close()


def create_homework(user_id: int, description: str, deadline=None, program_id=None):
    user = database.get_user(int(user_id))
    if not user:
        return None, "Ученик не найден."
    programs = student_programs(int(user_id))
    program = None
    if program_id is not None:
        program = next((r for r in programs if int(r["id"]) == int(program_id)), None)
    if program is None and programs:
        program = programs[0]
    study_goal = str(program["study_goal"] if program else user["study_goal"] or "SCHOOL")
    subject = str(program["subject"] if program else user["main_subject"] or "PHYSICS")
    homework_id = database.create_homework(
        user_id=int(user_id),
        study_goal=study_goal,
        subject=subject,
        description=str(description).strip(),
        title="Дополнительное домашнее задание",
        deadline=deadline,
        program_id=int(program["id"]) if program else None,
        homework_type="EXTRA",
    )
    subject_name = SUBJECT_NAMES.get(subject.upper(), subject)
    deadline_line = f"\n⏰ Срок: {deadline}" if deadline else ""
    text = (
        "📝 НОВОЕ ДОМАШНЕЕ ЗАДАНИЕ\n\n"
        f"📖 {subject_name}\n"
        f"{str(description).strip()}"
        f"{deadline_line}\n\n"
        "Задание уже появилось в разделе «Домашнее задание» 💜"
    )
    delivered = channel_delivery.send_student(int(user_id), text)
    return homework_id, delivered


def send_lesson_link(lesson_id: int, url: str):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        return None, "Занятие не найдено."
    user = database.get_user(int(lesson["user_id"]))
    if not user:
        return None, "Ученик не найден."
    value = str(url or "").strip()
    if not (value.startswith("https://") or value.startswith("http://")):
        return None, "Пришлите полную ссылку, начинающуюся с https://"
    try:
        if str(lesson["lesson_status"] or "").upper() != "IN_PROGRESS":
            database.start_lesson(int(lesson_id), force=True)
    except Exception as exc:
        return None, f"Не удалось начать занятие: {exc}"
    subject = SUBJECT_NAMES.get(str(lesson["subject"] or "").upper(), str(lesson["subject"] or "Занятие"))
    parts = [
        "▶️ ЗАНЯТИЕ НАЧАЛОСЬ",
        "",
        f"📖 {subject}",
        "",
        "🎥 Подключиться к занятию:",
        value,
    ]
    board_url = str(user["board_url"] or "").strip()
    if board_url:
        parts += ["", "📝 Доска занятия:", board_url]
    parts += ["", "Можно подключаться 💜"]
    delivered = channel_delivery.send_student(int(user["id"]), "\n".join(parts))
    return delivered, None


def teacher_alert_peers():
    return schema.get_admin_external_ids("VK")
