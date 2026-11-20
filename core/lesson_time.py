from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import database


def lesson_timezone() -> ZoneInfo:
    """Return the timezone used by lesson schedule timestamps."""
    try:
        # Scheduled lesson wall-clock values are stored in the canonical
        # schedule timezone. Keep this separate from the bot/runtime timezone:
        # changing where the bot process runs must never shift a lesson.
        name = database.get_setting("schedule_timezone", "Europe/Moscow")
    except Exception:
        name = "Europe/Moscow"
    try:
        return ZoneInfo(str(name or "Europe/Moscow"))
    except Exception:
        return ZoneInfo("Europe/Moscow")


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


def teacher_timezone() -> ZoneInfo:
    """Teacher/TutorBot working timezone (bot_timezone, default Europe/Samara)."""
    try:
        name = database.get_setting("bot_timezone", "Europe/Samara")
    except Exception:
        name = "Europe/Samara"
    try:
        return ZoneInfo(str(name or "Europe/Samara"))
    except Exception:
        return ZoneInfo("Europe/Samara")


def local_date(raw, tz) -> "date | None":
    """Calendar date of a scheduled lesson timestamp in ``tz``."""
    try:
        return schedule_datetime(raw).astimezone(tz).date()
    except Exception:
        return None


def sort_by_start(rows, key: str = "start_time"):
    """Sort rows chronologically by a schedule timestamp (mixed formats)."""
    def k(row):
        try:
            return schedule_datetime(row[key]).timestamp()
        except Exception:
            return float("inf")
    return sorted(rows, key=k)


def lessons_on_local_day(conn, day, tz, base_sql: str, params=(), start_col: str = "l.start_time", key: str = "start_time"):
    """Rows of ``base_sql`` whose start falls on ``day`` in timezone ``tz``.

    SQLite date() converts offset-aware strings (``+04:00``) to UTC, so a
    01:30 Samara lesson would be counted on the previous day. We prefilter a
    +-1 day window in SQL (any UTC shift is < 1 day) and decide exactly in
    Python. ``base_sql`` must already contain a WHERE clause.
    """
    from datetime import timedelta
    lo = (day - timedelta(days=1)).isoformat()
    hi = (day + timedelta(days=1)).isoformat()
    sql = f"{base_sql} AND date({start_col}) BETWEEN ? AND ?"
    rows = conn.execute(sql, (*tuple(params), lo, hi)).fetchall()
    picked = [r for r in rows if local_date(r[key], tz) == day]
    return sort_by_start(picked, key)


def daily_slot_due(now_local: datetime, target_hhmm: str, last_day: str | None, catch_up_minutes: int = 180) -> bool:
    """True when a once-a-day job should fire now.

    Fires on the first tick with ``now >= target`` (so a skipped/late minute
    does not lose the job), at most once per local day (``last_day`` holds the
    ISO date of the last run) and only within ``catch_up_minutes`` after the
    target, so a bot restart in the evening does not send a morning brief.
    """
    from datetime import timedelta
    try:
        hh, mm = str(target_hhmm or "").strip().split(":", 1)
        target = now_local.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return False
    day = now_local.date().isoformat()
    if (last_day or "") == day:
        return False
    return target <= now_local < target + timedelta(minutes=int(catch_up_minutes))


def claim_daily_slot(setting_key: str, now_local: datetime, target_hhmm: str, catch_up_minutes: int = 180) -> bool:
    """Check :func:`daily_slot_due` and persist the run day before sending.

    The flag is written (idempotent upsert into settings) before any await,
    so overlapping dispatcher ticks in the same event loop cannot both fire.
    """
    last = database.get_setting(setting_key, "") or ""
    if not daily_slot_due(now_local, target_hhmm, last, catch_up_minutes):
        return False
    database.set_setting(setting_key, now_local.date().isoformat())
    return True
