"""External-service orchestration for TutorBot lessons.

Calendar/video failures are deliberately isolated from lesson creation. A
lesson remains valid in TutorBot even when an external provider is temporarily
unavailable; failed integrations can be retried safely.
"""
from __future__ import annotations

import os


def sync_lesson(lesson_id, *, google=True, telemost=True):
    result = {"lesson_id": int(lesson_id), "google": None, "telemost": None}

    if telemost and os.getenv("YANDEX_TELEMOST_ENABLED", "0") == "1":
        try:
            from integrations.yandex_telemost import ensure_lesson_conference
            result["telemost"] = ensure_lesson_conference(lesson_id)
        except Exception as exc:
            result["telemost"] = {"status": "error", "error": str(exc)}

    if google and os.getenv("GOOGLE_CALENDAR_ENABLED", "1") == "1":
        try:
            from integrations.google_calendar import sync_lesson as sync_google
            result["google"] = sync_google(lesson_id)
        except Exception as exc:
            result["google"] = {"status": "error", "error": str(exc)}

    return result


def cancel_lesson(lesson_id):
    result = {"lesson_id": int(lesson_id), "google": None, "telemost": None}
    if os.getenv("GOOGLE_CALENDAR_ENABLED", "1") == "1":
        try:
            from integrations.google_calendar import cancel_lesson as cancel_google
            result["google"] = cancel_google(lesson_id)
        except Exception as exc:
            result["google"] = {"status": "error", "error": str(exc)}
    # Telemost conferences are intentionally not destroyed on local
    # cancellation yet. This avoids deleting a reusable/active conference
    # until the Business API credentials and lifecycle policy are confirmed.
    return result


def status():
    data = {"google": {}, "telemost": {}}
    try:
        from integrations.google_calendar import connection_status
        data["google"] = connection_status()
    except Exception as exc:
        data["google"] = {"connected": False, "error": str(exc)}
    data["telemost"] = {
        "enabled": os.getenv("YANDEX_TELEMOST_ENABLED", "0") == "1",
        "configured": bool(os.getenv("YANDEX_TELEMOST_OAUTH_TOKEN")),
    }
    return data
