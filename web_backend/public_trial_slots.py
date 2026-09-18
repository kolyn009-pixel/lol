"""Timezone-aware free slots for public trial booking."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import database
from web_backend import availability_guard

STEP_MINUTES = 30
DEFAULT_DURATION = 60
MAX_DAYS = 21


def _read_connection():
    """Open the public-slot database connection without mutating journal mode."""
    conn = sqlite3.connect(database.current_db_name(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _teacher_tz(conn=None):
    name = database.get_setting("bot_timezone", "Europe/Samara", conn=conn) or "Europe/Samara"
    try:
        return str(name), ZoneInfo(str(name))
    except ZoneInfoNotFoundError:
        return "Europe/Samara", ZoneInfo("Europe/Samara")


def _client_tz(name):
    value = str(name or "Europe/Moscow").strip()[:80]
    try:
        return value, ZoneInfo(value)
    except ZoneInfoNotFoundError:
        raise ValueError("invalid_timezone")


def _working_dt(day, value, tz):
    raw = str(value or '').strip()
    try:
        parts = raw.split(':')
        if len(parts) not in {2, 3}:
            raise ValueError
        hh = int(parts[0])
        mm = int(parts[1])
        ss = int(parts[2]) if len(parts) == 3 else 0
        return datetime.combine(day, time(hh, mm, ss), tzinfo=tz)
    except Exception:
        raise ValueError("invalid_working_hours")


def _working_spans(day, rows, tz):
    """Return the real independent working intervals for one date.

    Do not collapse a split schedule such as 10:00-13:00 and 16:00-20:00
    into one 10:00-20:00 envelope: that would expose bookable trial slots
    inside the teacher's break.
    """
    spans = []
    for row in rows:
        start = _working_dt(day, row['start_time'], tz)
        end = _working_dt(day, row['end_time'], tz)
        if end <= start:
            continue
        spans.append((start, end))
    spans.sort(key=lambda item: item[0])
    return spans


def feed(timezone_name, days=14, duration_minutes=DEFAULT_DURATION):
    if str(database.get_setting('teacher_schedule_booking_paused','0') or '0').lower() in {'1','true','on','yes'}:
        return {'timezone': str(timezone_name or 'Europe/Moscow'), 'teacher_timezone': str(database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'), 'duration_minutes': int(duration_minutes or DEFAULT_DURATION), 'items': [], 'booking_paused': True}
    client_name, client_tz = _client_tz(timezone_name)
    duration = int(duration_minutes or DEFAULT_DURATION)
    if duration != DEFAULT_DURATION:
        raise ValueError("invalid_duration")
    days = max(1, min(int(days or 14), MAX_DAYS))
    out = []
    conn = _read_connection()
    try:
        teacher_name, teacher_tz = _teacher_tz(conn=conn)
        now_teacher = datetime.now(teacher_tz)
        range_start = now_teacher.replace(tzinfo=None)
        range_end = (now_teacher + timedelta(days=days + 1)).replace(tzinfo=None)
        snapshot = availability_guard.availability_snapshot(range_start, range_end, conn=conn)
        for offset in range(days):
            day = now_teacher.date() + timedelta(days=offset)
            values = []
            rows = database.get_effective_working_hours(day, conn=conn)
            for start, end in _working_spans(day, rows, teacher_tz):
                cur = start
                while cur + timedelta(minutes=duration) <= end:
                    finish = cur + timedelta(minutes=duration)
                    teacher_start = cur.replace(tzinfo=None)
                    teacher_end = finish.replace(tzinfo=None)
                    if cur > now_teacher + timedelta(minutes=30) and availability_guard.is_available_from_snapshot(
                        teacher_start, teacher_end, snapshot
                    ):
                        local_start = cur.astimezone(client_tz)
                        local_end = finish.astimezone(client_tz)
                        values.append({
                            "start_time": teacher_start.isoformat(timespec="seconds"),
                            "end_time": teacher_end.isoformat(timespec="seconds"),
                            "local_start": local_start.isoformat(timespec="seconds"),
                            "local_end": local_end.isoformat(timespec="seconds"),
                            "label": local_start.strftime("%H:%M"),
                        })
                    cur += timedelta(minutes=STEP_MINUTES)
            if values:
                by_local_day = {}
                for slot in values:
                    local_day = datetime.fromisoformat(slot["local_start"]).date().isoformat()
                    by_local_day.setdefault(local_day, []).append(slot)
                for local_day in sorted(by_local_day):
                    out.append({"date": local_day, "slots": by_local_day[local_day]})
    finally:
        conn.close()
    return {
        "timezone": client_name,
        "teacher_timezone": teacher_name,
        "duration_minutes": duration,
        "items": out,
    }
