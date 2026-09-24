from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import database


def lesson_timezone() -> ZoneInfo:
    """Return the timezone used by lesson schedule timestamps."""
    try:
        name = database.get_setting("bot_timezone", "Europe/Samara")
    except Exception:
        name = "Europe/Samara"
    try:
        return ZoneInfo(str(name or "Europe/Samara"))
    except Exception:
        return ZoneInfo("Europe/Samara")


def schedule_datetime(raw) -> datetime:
    """Parse a scheduled lesson timestamp and return it in lesson timezone.

    Legacy schedule values without an offset are local wall-clock values.
    """
    value = datetime.fromisoformat(str(raw))
    tz = lesson_timezone()
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def actual_datetime(raw) -> datetime:
    """Parse started_at/finished_at and return it in lesson timezone.

    Legacy actual timestamps were produced by database.now_iso() on the
    production UTC host and therefore are UTC-naive. Offset-aware values are
    supported as well.
    """
    value = datetime.fromisoformat(str(raw))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(lesson_timezone())


def actual_storage_iso(value: datetime) -> str:
    """Serialize an instant in the legacy actual-time storage convention.

    database.finish_lesson currently subtracts naive datetimes. Until that
    storage format is migrated, write UTC-naive values so they remain
    compatible with existing started_at rows.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=lesson_timezone())
    return (
        value.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def actual_now_iso() -> str:
    """Current instant in legacy UTC-naive actual-time storage format."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
