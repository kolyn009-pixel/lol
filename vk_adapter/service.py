from __future__ import annotations

from datetime import datetime

import database
from . import schema


def linked_user(vk_user_id):
    uid = schema.get_user_id("VK", str(vk_user_id))
    return database.get_user(uid) if uid else None


def upcoming_text(user_id, limit=5):
    rows = list(database.get_upcoming_lessons(int(user_id)))[: int(limit)]
    if not rows:
        return "📅 Ближайших занятий пока нет."
    lines = ["📅 БЛИЖАЙШИЕ ЗАНЯТИЯ", ""]
    for row in rows:
        raw = str(row["start_time"])
        try:
            dt = datetime.fromisoformat(raw)
            when = dt.strftime("%d.%m в %H:%M")
        except Exception:
            when = raw
        subject = str(row["subject"] or "").upper()
        subject_name = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}.get(subject, subject or "Занятие")
        lines.append(f"• {when} — {subject_name}")
    return "\n".join(lines)


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
