"""Teacher settings for Yandex Telemost lesson links.

The global switch controls whether Adelia creates a Yandex Telemost conference
when the teacher presses "Start lesson". Conferences are never created while a
lesson/group/event is merely being scheduled.
"""
from __future__ import annotations

import database
from integrations import telemost_lifecycle, yandex_telemost

SETTING_KEY = "telemost_auto_on_start"


def auto_on_start() -> bool:
    value = str(database.get_setting(SETTING_KEY, "1") or "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def snapshot():
    status = yandex_telemost.connection_status()
    return {
        "status": "ok",
        "provider": "YANDEX_TELEMOST",
        "provider_name": "Яндекс Телемост",
        "auto_on_start": auto_on_start(),
        "enabled": bool(status.get("enabled")),
        "configured": bool(status.get("configured")),
        "ready": bool(telemost_lifecycle.enabled()),
        "waiting_room_level": status.get("waiting_room_level"),
        "config_error": status.get("config_error"),
        "create_moment": "TEACHER_START",
    }


def update(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("auto_on_start"), bool):
        raise ValueError("invalid_auto_on_start")
    database.set_setting(SETTING_KEY, "1" if payload["auto_on_start"] else "0")
    result = snapshot()
    result["saved"] = True
    return result
