"""Canonical homework status vocabulary shared by web, Telegram and VK."""

STATUSES = {
    "ASSIGNED": {"student": "Назначено", "teacher": "Назначено", "active": True, "tone": "primary"},
    "SUBMITTED": {"student": "Сдано · ждёт проверки", "teacher": "Нужно проверить", "active": True, "tone": "warning"},
    "UNDER_REVIEW": {"student": "На проверке", "teacher": "На проверке", "active": True, "tone": "warning"},
    "REVISION": {"student": "На доработке", "teacher": "Доработка", "active": True, "tone": "danger"},
    "REVIEWED": {"student": "Проверено", "teacher": "Проверено", "active": False, "tone": "success"},
    "COMPLETED": {"student": "Выполнено", "teacher": "Завершено", "active": False, "tone": "success"},
    "CANCELLED": {"student": "Отменено", "teacher": "Отменено", "active": False, "tone": "muted"},
}

ALIASES = {
    "CHECKED": "COMPLETED",
    "DONE": "COMPLETED",
    "ACCEPTED": "COMPLETED",
    "PENDING": "ASSIGNED",
}


def canonical(value):
    status = str(value or "ASSIGNED").strip().upper()
    return ALIASES.get(status, status if status in STATUSES else "ASSIGNED")


def payload(value):
    status = canonical(value)
    return {"code": status, **STATUSES[status]}


def label(value, audience="student"):
    item = payload(value)
    return item["teacher" if str(audience).lower() == "teacher" else "student"]


def is_active(value):
    return bool(payload(value)["active"])
