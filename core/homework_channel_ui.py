"""Channel-safe homework presentation shared by Telegram and VK.

This module is intentionally UI-only: canonical homework data remains in the
existing database/web homework services. It never exposes task-bank answers.
"""
from datetime import datetime

import database
from web_backend.homework_status import label as status_label, is_active

APP_BASE_URL = "https://adeliatutor.ru/app/"


def _value(row, *names, default=None):
    if row is None:
        return default
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    for name in names:
        if name in keys and row[name] not in (None, ""):
            return row[name]
    return default


def _fmt_deadline(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)


def app_url(homework_id=None):
    return APP_BASE_URL + (f"?homework={int(homework_id)}" if homework_id else "?view=homework")


def list_items(user_id, limit=20, include_finished=False):
    try:
        rows = list(database.get_student_homework(int(user_id), active_only=not include_finished))
    except Exception:
        rows = []
    if not include_finished:
        rows = [r for r in rows if is_active(_value(r, "status", default="ASSIGNED"))]
    return rows[:int(limit)]


def item_title(row, fallback_index=None):
    title = _value(row, "title", "topic", "name")
    if title:
        return str(title)
    hid = _value(row, "id")
    return f"ДЗ #{hid}" if hid else f"Задание {fallback_index or ''}".strip()


def list_text(user_id, limit=20):
    rows = list_items(user_id, limit)
    if not rows:
        return "📝 Активных домашних заданий сейчас нет."
    lines = ["📝 ДОМАШНИЕ ЗАДАНИЯ", ""]
    for i, row in enumerate(rows, 1):
        title = item_title(row, i)
        status = status_label(_value(row, "status"), "student")
        deadline = _fmt_deadline(_value(row, "deadline", "due_at", "due_date"))
        lines.append(f"{i}. {title}")
        lines.append(f"   {status}" + (f" · до {deadline}" if deadline else ""))
    lines += ["", "Открыть, решить интерактивное ДЗ и посмотреть комментарии преподавателя можно в Аделии 💜"]
    return "\n".join(lines)


def detail(user_id, homework_id):
    row = database.get_homework(int(homework_id))
    if not row or int(_value(row, "user_id", default=-1)) != int(user_id):
        return None
    title = item_title(row)
    status = status_label(_value(row, "status"), "student")
    description = str(_value(row, "description", "task_text", "text", "content", default="") or "").strip()
    deadline = _fmt_deadline(_value(row, "deadline", "due_at", "due_date"))
    lines = [f"📝 {title}", "", f"Статус: {status}"]
    if deadline:
        lines.append(f"⏰ Срок: {deadline}")
    if description:
        lines += ["", description]
    lines += ["", "В личном кабинете доступны задания, материалы, результаты и комментарии преподавателя."]
    return {"row": row, "text": "\n".join(lines), "url": app_url(homework_id), "status": status}
