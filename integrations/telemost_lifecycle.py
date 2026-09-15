"""Verified Telemost lifecycle shared by individual, group and open events.

The create payload matches the production API probe that returned HTTP 201.
Provider secrets stay in environment variables and are never persisted/logged.
"""
from __future__ import annotations

import os

from integrations import yandex_telemost


def enabled():
    return os.getenv("YANDEX_TELEMOST_ENABLED", "0") == "1" and bool(
        os.getenv("YANDEX_TELEMOST_OAUTH_TOKEN", "").strip()
    )


def create_conference():
    if not enabled():
        return {"status": "disabled", "conference_id": None, "join_url": None}
    # This is the payload verified against the live Yandex 360 Telemost API.
    status, data = yandex_telemost._request(
        "POST",
        "/conferences",
        {"access_level": "PUBLIC"},
    )
    if status != 201:
        raise RuntimeError(f"telemost_unexpected_status_{status}")
    conference_id = str(data.get("id") or "").strip()
    join_url = yandex_telemost._join_url(data.get("join_url"))
    if not conference_id:
        raise RuntimeError("telemost_missing_conference_id")
    return {
        "status": "ok",
        "conference_id": conference_id,
        "join_url": join_url,
    }


def ensure_individual_conference(lesson_id):
    """Create/reuse one conference for an individual lesson."""
    lesson_id = int(lesson_id)
    existing = yandex_telemost._integration(lesson_id) or {}
    if existing.get("telemost_conference_id") and existing.get("telemost_join_url"):
        return {
            "status": "ok",
            "conference_id": existing["telemost_conference_id"],
            "join_url": existing["telemost_join_url"],
            "reused": True,
        }
    result = create_conference()
    if result["status"] != "ok":
        return {**result, "reused": False}
    saved = yandex_telemost._save(
        lesson_id,
        result["conference_id"],
        result["join_url"],
    )
    return {"status": "ok", **saved}


def finish_individual_conference(lesson_id):
    """Best-effort provider cleanup that must never block lesson completion."""
    if not enabled():
        return {"status": "disabled", "conference_id": None}
    try:
        return yandex_telemost.close_lesson_conference(int(lesson_id))
    except Exception as exc:
        return {"status": "close_failed", "error": str(exc)[:120]}


def safe_read(conference_id):
    if not conference_id or not enabled():
        return None
    try:
        return yandex_telemost.read_conference(conference_id)
    except Exception:
        return None
