from __future__ import annotations

from datetime import datetime

import database
from automation import messaging
from core import event_center
from crm_plus import service as crm_service
from formula_library import FORMULA_LIBRARY

from . import schema

SUBJECT_NAMES = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}
GOAL_NAMES = {
    "SCHOOL": "Повышение успеваемости",
    "OGE": "Подготовка к ОГЭ",
    "EGE": "Подготовка к ЕГЭ",
    "OLYMPIAD": "Олимпиадная подготовка",
}


def linked_user(vk_user_id):
    uid = schema.get_user_id("VK", str(vk_user_id))
    return database.get_user(uid) if uid else None


def _row_value(row, *names, default=None):
    if row is None:
        return default
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    for name in names:
        if name in keys:
            value = row[name]
            if value not in (None, ""):
                return value
    return default


def _fmt_dt(raw):
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(str(raw))
        return dt.strftime("%d.%m в %H:%M")
    except Exception:
        return str(raw)


def upcoming_text(user_id, limit=5):
    rows = list(database.get_upcoming_lessons(int(user_id)))[: int(limit)]
    if not rows:
        return "📅 Ближайших занятий пока нет."
    lines = ["📅 МОИ ЗАНЯТИЯ", ""]
    for row in rows:
        subject = str(_row_value(row, "subject", default="") or "").upper()
        subject_name = SUBJECT_NAMES.get(subject, subject or "Занятие")
        payment = str(_row_value(row, "payment_status", default="") or "")
        payment_label = {
            "PAID": "✅ оплачено",
            "FREE": "🎁 бесплатно",
            "AWAITING_PAYMENT": "💳 ожидает оплаты",
            "RESERVED_BALANCE": "🎟 абонемент",
        }.get(payment, "")
        suffix = f" · {payment_label}" if payment_label else ""
        lines.append(f"• {_fmt_dt(_row_value(row, 'start_time'))} — {subject_name}{suffix}")
    return "\n".join(lines)


def homework_text(user_id, limit=8):
    try:
        rows = list(database.get_student_homework(int(user_id), active_only=True))[: int(limit)]
    except Exception:
        rows = []
    if not rows:
        return "📝 Активных домашних заданий сейчас нет."

    lines = ["📝 ДОМАШНЕЕ ЗАДАНИЕ", ""]
    for index, row in enumerate(rows, 1):
        title = _row_value(row, "title", "topic", "name", default=f"Задание {index}")
        text = _row_value(row, "task_text", "description", "text", "content", default="")
        due = _row_value(row, "due_at", "deadline", "due_date")
        status = str(_row_value(row, "status", default="") or "")
        lines.append(f"{index}. {title}")
        if text:
            clean = str(text).strip().replace("\n", " ")
            lines.append(clean[:500])
        if due:
            lines.append(f"⏰ До: {_fmt_dt(due)}")
        if status:
            lines.append(f"Статус: {status}")
        lines.append("")
    return "\n".join(lines).strip()


def study_text(user_id):
    user = database.get_user(int(user_id))
    if not user:
        return "📚 Профиль ученика не найден."

    c = database.connect()
    try:
        programs = c.execute(
            """
            SELECT study_goal,subject,custom_hourly_rate,is_primary
            FROM student_programs
            WHERE user_id=? AND active=1
            ORDER BY is_primary DESC,id
            """,
            (int(user_id),),
        ).fetchall()
    finally:
        c.close()

    lines = ["📚 МОЯ УЧЁБА", "", f"👤 {user['name']} · {user['grade']} класс"]
    if programs:
        lines += ["", "Направления:"]
        for row in programs:
            goal = GOAL_NAMES.get(str(row["study_goal"] or ""), str(row["study_goal"] or ""))
            subject = SUBJECT_NAMES.get(str(row["subject"] or ""), str(row["subject"] or ""))
            primary = " ⭐" if row["is_primary"] else ""
            lines.append(f"• {subject} · {goal}{primary}")
    else:
        goal = GOAL_NAMES.get(str(user["study_goal"] or ""), str(user["study_goal"] or ""))
        subject = SUBJECT_NAMES.get(str(user["main_subject"] or ""), str(user["main_subject"] or ""))
        lines += ["", f"• {subject} · {goal}"]

    try:
        active_hw = len(database.get_student_homework(int(user_id), active_only=True))
        lines += ["", f"📝 Активных ДЗ: {active_hw}"]
    except Exception:
        pass

    upcoming = list(database.get_upcoming_lessons(int(user_id)))
    lines.append(f"📅 Ближайших занятий: {len(upcoming)}")
    return "\n".join(lines)


def formulas_text(user_id):
    user = database.get_user(int(user_id))
    try:
        grade = int(str(user["grade"]).split()[0]) if user else None
    except Exception:
        grade = None

    lines = ["🧮 ФОРМУЛЫ И СПРАВОЧНИК", ""]
    if grade in FORMULA_LIBRARY:
        lines.append(f"🎓 {grade} класс")
        for subject, topics in FORMULA_LIBRARY[grade].items():
            lines.append(f"\n{SUBJECT_NAMES.get(subject, subject)}:")
            for item in list(topics.values())[:8]:
                lines.append(f"• {item.get('title', 'Тема')}")
        lines += ["", "Напиши название темы сообщением — я постараюсь найти её в справочнике."]
    else:
        grades = ", ".join(str(x) for x in sorted(FORMULA_LIBRARY))
        lines.append(f"Доступные классы: {grades}")
    return "\n".join(lines)


def formula_topic_text(user_id, query):
    q = str(query or "").strip().lower()
    if not q:
        return None
    user = database.get_user(int(user_id))
    try:
        grade = int(str(user["grade"]).split()[0]) if user else None
    except Exception:
        grade = None
    libraries = []
    if grade in FORMULA_LIBRARY:
        libraries.append(FORMULA_LIBRARY[grade])
    for g, lib in FORMULA_LIBRARY.items():
        if g != grade:
            libraries.append(lib)
    for lib in libraries:
        for _subject, topics in lib.items():
            for item in topics.values():
                title = str(item.get("title") or "")
                if q in title.lower() or title.lower() in q:
                    return str(item.get("text") or title)
    return None


def board_text(user_id):
    user = database.get_user(int(user_id))
    url = _row_value(user, "board_url")
    if not url:
        return "🖥 Ссылка на доску пока не добавлена. Когда преподаватель сохранит её, она появится здесь."
    return f"🖥 ДОСКА\n\nОткрывай рабочую доску:\n{url}"


def more_text(user_id):
    user = database.get_user(int(user_id))
    if not user:
        return "⚙️ Профиль не найден."
    c = database.connect()
    try:
        unpaid = c.execute(
            """
            SELECT COUNT(*) AS n
            FROM lessons
            WHERE user_id=? AND lesson_status='CONFIRMED'
              AND payment_status='AWAITING_PAYMENT'
              AND cancelled_at IS NULL
            """,
            (int(user_id),),
        ).fetchone()["n"]
    finally:
        c.close()
    return (
        "⚙️ ЕЩЁ\n\n"
        f"👤 {user['name']} · {user['grade']} класс\n"
        f"💳 Занятий ожидают оплаты: {int(unpaid or 0)}\n"
        f"🔗 VK подключён к общей карточке TutorBot."
    )


def message_history_text(user_id, limit=12):
    rows = crm_service.message_history(int(user_id), int(limit))
    if not rows:
        return "💬 Переписки с преподавателем пока нет."
    lines = ["💬 ПРЕПОДАВАТЕЛЬ", ""]
    for row in reversed(rows):
        who = "👨‍🏫" if row["direction"] == "OUT" else "👤"
        when = _fmt_dt(row["created_at"])
        lines.append(f"{who} {when}\n{row['body']}")
    return "\n\n".join(lines)[-3500:]


def submit_teacher_message(user_id, text, source_vk_id=None):
    user = database.get_user(int(user_id))
    body = str(text or "").strip()
    if not user or not body:
        return False, "Пустое сообщение не отправлено."

    accepting, deliver_at = crm_service.inbound_delivery_state()
    status = "OPEN" if accepting else "QUEUED"
    sender_id = int(user["telegram_id"] or 0)
    subject = "Сообщение от ученика из VK"
    iid = messaging.create_inbox(
        body,
        sender_id,
        student_id=int(user_id),
        subject=subject,
        status=status,
    )
    crm_service.log_message(
        int(user_id),
        "IN",
        body,
        None,
        "TEACHER",
        "DELIVERED" if accepting else "QUEUED",
        None if accepting else deliver_at.isoformat(timespec="seconds"),
        inbox_id=iid,
    )
    event_center.push(
        "TEACHER_INBOX",
        f"Сообщение из VK от {user['name']}",
        body[:500],
        priority="ACTION",
        entity_type="teacher_inbox",
        entity_id=iid,
        dedupe_key=f"inbox:{iid}",
    )
    if accepting:
        return True, "✅ Сообщение сохранено в диалоге с преподавателем."
    return True, f"🌙 Сообщение сохранено и будет доставлено в часы приёма. Плановая доставка: {_fmt_dt(deliver_at.isoformat())}"


def submit_booking_request(user_id, text):
    user = database.get_user(int(user_id))
    body = str(text or "").strip()
    if not user or not body:
        return False, "Напиши желаемые день и время одним сообщением."
    iid = messaging.create_inbox(
        body,
        int(user["telegram_id"] or 0),
        student_id=int(user_id),
        subject="Запрос на запись из VK",
        status="OPEN",
    )
    event_center.push(
        "VK_BOOKING_REQUEST",
        f"Запрос на запись из VK · {user['name']}",
        body[:500],
        priority="ACTION",
        entity_type="teacher_inbox",
        entity_id=iid,
        dedupe_key=f"vk_booking:{iid}",
    )
    return True, "✅ Запрос на запись отправлен преподавателю. Я сохраню ответ в общей карточке ученика."


def identity_status(vk_user_id):
    user = linked_user(vk_user_id)
    if not user:
        return None
    return {
        "user_id": int(user["id"]),
        "name": user["name"],
        "grade": user["grade"],
        "active": bool(user["active"]),
    }
