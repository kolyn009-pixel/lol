"""Teacher working-hours editor shared by web and desktop clients.

Changing working hours only changes future availability. Existing lessons and
regular schedules are never moved or deleted by this module.
"""
from __future__ import annotations

from datetime import datetime
import re

import database

WEEK_TYPES = {"ALL", "ODD", "EVEN"}
MODES = {"SAME", "ALTERNATING"}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _time(value):
    value = str(value or "").strip()[:5]
    if not _TIME_RE.fullmatch(value):
        raise ValueError("invalid_time")
    return value


def _minutes(value):
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def _normalize_rows(rows, mode):
    if not isinstance(rows, list):
        raise ValueError("invalid_schedule")
    normalized = []
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("invalid_schedule_row")
        weekday = int(raw.get("weekday"))
        if weekday < 0 or weekday > 6:
            raise ValueError("invalid_weekday")
        week_type = str(raw.get("week_type") or "ALL").upper()
        if week_type not in WEEK_TYPES:
            raise ValueError("invalid_week_type")
        if mode == "SAME" and week_type != "ALL":
            raise ValueError("alternating_row_in_same_mode")
        start = _time(raw.get("start_time"))
        end = _time(raw.get("end_time"))
        if _minutes(end) <= _minutes(start):
            raise ValueError("invalid_working_interval")
        normalized.append({
            "weekday": weekday,
            "week_type": week_type,
            "start_time": start,
            "end_time": end,
        })

    # A schedule editor must never allow overlapping windows in the same bucket.
    buckets = {}
    for row in normalized:
        key = (row["weekday"], row["week_type"])
        buckets.setdefault(key, []).append(row)
    for bucket in buckets.values():
        ordered = sorted(bucket, key=lambda r: _minutes(r["start_time"]))
        for left, right in zip(ordered, ordered[1:]):
            if _minutes(right["start_time"]) < _minutes(left["end_time"]):
                raise ValueError("working_hours_overlap")
    normalized.sort(key=lambda r: (r["week_type"], r["weekday"], r["start_time"]))
    return normalized


def _rows():
    rows = database.get_working_hours()
    result = []
    for row in rows:
        d = dict(row)
        result.append({
            "id": int(d["id"]),
            "weekday": int(d["weekday"]),
            "week_type": str(d.get("week_type") or "ALL").upper(),
            "start_time": str(d["start_time"])[:5],
            "end_time": str(d["end_time"])[:5],
            "active": bool(d.get("active", 1)),
        })
    return result


def _warnings(rows, mode):
    """Report regular schedules outside the new envelope without mutating them."""
    conn = database.connect()
    try:
        regular = conn.execute(
            """SELECT rs.id,rs.user_id,rs.weekday,rs.start_time,rs.duration_minutes,
                      u.name AS student_name
               FROM regular_schedules rs
               JOIN users u ON u.id=rs.user_id
               WHERE rs.active=1
                 AND COALESCE(rs.status,'APPROVED') NOT IN ('CANCELLED','REJECTED')
               ORDER BY rs.weekday,rs.start_time,rs.id"""
        ).fetchall()
    finally:
        conn.close()
    by_day = {}
    for row in rows:
        by_day.setdefault((row["weekday"], row["week_type"]), []).append(row)
    warnings = []
    for item in regular:
        start = str(item["start_time"] or "")[:5]
        if not _TIME_RE.fullmatch(start):
            continue
        duration = int(item["duration_minutes"] or 60)
        s = _minutes(start)
        e = s + duration
        week_types = ["ALL"] if mode == "SAME" else ["ODD", "EVEN"]
        missing = []
        for wt in week_types:
            candidates = by_day.get((int(item["weekday"]), wt), [])
            covered = any(_minutes(x["start_time"]) <= s and _minutes(x["end_time"]) >= e for x in candidates)
            if not covered:
                missing.append(wt)
        if missing:
            warnings.append({
                "type": "regular_schedule_outside_working_hours",
                "regular_schedule_id": int(item["id"]),
                "student_id": int(item["user_id"]),
                "student_name": item["student_name"],
                "weekday": int(item["weekday"]),
                "start_time": start,
                "duration_minutes": duration,
                "week_types": missing,
            })
    return warnings


def snapshot():
    mode = str(database.get_setting("teacher_week_mode", "SAME") or "SAME").upper()
    if mode not in MODES:
        mode = "SAME"
    rows = _rows()
    return {
        "timezone": str(database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"),
        "mode": mode,
        "items": rows,
        "warnings": _warnings(rows, mode),
    }


def replace(payload):
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    mode = str(payload.get("mode") or "SAME").upper()
    if mode not in MODES:
        raise ValueError("invalid_week_mode")
    rows = _normalize_rows(payload.get("items") or [], mode)
    # Empty schedule is allowed intentionally: it means no self-bookable hours.
    now = database.now_iso()
    conn = database.connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("UPDATE working_hours SET active=0,updated_at=? WHERE active=1", (now,))
        for row in rows:
            conn.execute(
                """INSERT INTO working_hours(
                       weekday,start_time,end_time,active,created_at,updated_at,week_type
                   ) VALUES(?,?,?,?,?,?,?)""",
                (
                    row["weekday"], row["start_time"], row["end_time"],
                    1, now, now, row["week_type"],
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    database.set_setting("teacher_week_mode", mode)
    result = snapshot()
    result["status"] = "ok"
    result["saved_at"] = datetime.now().isoformat(timespec="seconds")
    result["existing_lessons_changed"] = False
    return result
