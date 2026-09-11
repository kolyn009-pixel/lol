"""Timezone-aware free slots for public trial booking."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import database
from web_backend import public_trial

STEP_MINUTES = 30
DEFAULT_DURATION = 60
MAX_DAYS = 21


def _teacher_tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
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


def _pending_public_slots():
    public_trial.ensure_schema()
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT selected_slot_start, selected_slot_end
            FROM public_trial_requests
            WHERE selected_slot_start IS NOT NULL
              AND status IN ('NEW','CONTACTED','ACCEPTED')
              AND (expires_at IS NULL OR expires_at > ?)
            """,
            (datetime.now().isoformat(timespec="seconds"),),
        ).fetchall()
        return {(str(r["selected_slot_start"]), str(r["selected_slot_end"] or "")) for r in rows}
    finally:
        c.close()


def feed(timezone_name, days=14, duration_minutes=DEFAULT_DURATION):
    teacher_name, teacher_tz = _teacher_tz()
    client_name, client_tz = _client_tz(timezone_name)
    duration = int(duration_minutes or DEFAULT_DURATION)
    if duration != DEFAULT_DURATION:
        raise ValueError("invalid_duration")
    days = max(1, min(int(days or 14), MAX_DAYS))

    now_teacher = datetime.now(teacher_tz)
    pending = _pending_public_slots()
    out = []
    for offset in range(days):
        day = now_teacher.date() + timedelta(days=offset)
        values = []
        for row in database.get_effective_working_hours(day):
            start = datetime.fromisoformat(f"{day.isoformat()}T{row['start_time']}:00").replace(tzinfo=teacher_tz)
            end = datetime.fromisoformat(f"{day.isoformat()}T{row['end_time']}:00").replace(tzinfo=teacher_tz)
            cur = start
            while cur + timedelta(minutes=duration) <= end:
                finish = cur + timedelta(minutes=duration)
                teacher_start = cur.replace(tzinfo=None).isoformat(timespec="seconds")
                teacher_end = finish.replace(tzinfo=None).isoformat(timespec="seconds")
                if cur > now_teacher + timedelta(minutes=30):
                    occupied = database.is_slot_reserved(teacher_start, teacher_end)
                    public_occupied = (teacher_start, teacher_end) in pending
                    if not occupied and not public_occupied:
                        local_start = cur.astimezone(client_tz)
                        local_end = finish.astimezone(client_tz)
                        values.append({
                            "start_time": teacher_start,
                            "end_time": teacher_end,
                            "local_start": local_start.isoformat(timespec="seconds"),
                            "local_end": local_end.isoformat(timespec="seconds"),
                            "label": local_start.strftime("%H:%M"),
                        })
                cur += timedelta(minutes=STEP_MINUTES)
        if values:
            local_day = datetime.fromisoformat(values[0]["local_start"]).date().isoformat()
            out.append({"date": local_day, "slots": values})
    return {
        "timezone": client_name,
        "teacher_timezone": teacher_name,
        "duration_minutes": duration,
        "items": out,
    }
