"""Precreate Yandex Telemost conferences shortly before scheduled lessons.

The worker prepares conferences up to PRECREATE_MINUTES before start, but does
not publish links to students and does not mark lessons as started. Teacher
"Start lesson" remains the action that opens access. If precreation missed or
failed, the normal start flow may still create the conference as a fallback.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta

import database
from integrations.telemost_lifecycle import ensure_individual_conference, create_conference
from web_backend import telemost_settings

PRECREATE_MINUTES = max(5, min(int(os.getenv("ADELIA_TELEMOST_PRECREATE_MINUTES", "60")), 360))
LOOKBACK_MINUTES = max(1, min(int(os.getenv("ADELIA_TELEMOST_PRECREATE_LOOKBACK_MINUTES", "10")), 60))
POLL_SECONDS = max(20, min(int(os.getenv("ADELIA_TELEMOST_PRECREATE_POLL_SECONDS", "60")), 600))
FINAL_INDIVIDUAL = {"CANCELLED", "REJECTED", "NO_SHOW", "LATE_CANCELLED", "SICKNESS", "COMPLETED"}
FINAL_GROUP = {"COMPLETED", "CANCELLED", "QUORUM_FAILED"}
FINAL_EVENT = {"COMPLETED", "CANCELLED", "CLOSED"}


def _now():
    return datetime.now()


def _window():
    now = _now()
    return now - timedelta(minutes=LOOKBACK_MINUTES), now + timedelta(minutes=PRECREATE_MINUTES)


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _in_window(value, lo, hi):
    dt = _parse(value)
    return bool(dt and lo <= dt <= hi)


def _prepare_individual(lo, hi):
    conn = database.connect()
    rows = conn.execute(
        """SELECT id,start_time,lesson_status,payment_status,is_trial,finished_at
             FROM lessons
            WHERE start_time IS NOT NULL
              AND finished_at IS NULL
            ORDER BY start_time"""
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        if str(row["lesson_status"] or "").upper() in FINAL_INDIVIDUAL:
            continue
        payment = str(row["payment_status"] or "").upper()
        admitted = bool(row["is_trial"]) or payment in {"PAID", "FREE", "RESERVED_BALANCE", "WAIVED", "COVERED"}
        if not admitted:
            continue
        if not _in_window(row["start_time"], lo, hi):
            continue
        try:
            result = ensure_individual_conference(int(row["id"]))
            out.append(("individual", int(row["id"]), result.get("status"), bool(result.get("reused"))))
        except Exception as exc:
            out.append(("individual", int(row["id"]), "error", str(exc)[:120]))
    return out


def _prepare_group(lo, hi):
    conn = database.connect()
    rows = conn.execute(
        """SELECT id,start_time,status,telemost_conference_id,telemost_join_url
             FROM group_lessons
            WHERE start_time IS NOT NULL
            ORDER BY start_time"""
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        if str(row["status"] or "").upper() in FINAL_GROUP:
            continue
        if not _in_window(row["start_time"], lo, hi):
            continue
        if row["telemost_conference_id"] and row["telemost_join_url"]:
            out.append(("group", int(row["id"]), "ok", True))
            continue
        try:
            result = create_conference()
            if result.get("status") == "ok":
                conn = database.connect()
                conn.execute(
                    """UPDATE group_lessons
                          SET telemost_conference_id=?,telemost_join_url=?,updated_at=?
                        WHERE id=? AND (telemost_conference_id IS NULL OR telemost_join_url IS NULL)""",
                    (result["conference_id"], result["join_url"], database.now_iso(), int(row["id"])),
                )
                conn.commit(); conn.close()
            out.append(("group", int(row["id"]), result.get("status"), False))
        except Exception as exc:
            out.append(("group", int(row["id"]), "error", str(exc)[:120]))
    return out


def _prepare_events(lo, hi):
    conn = database.connect()
    table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='open_learning_events'").fetchone()
    if not table:
        conn.close(); return []
    rows = conn.execute(
        """SELECT id,starts_at,status,telemost_conference_id,telemost_join_url
             FROM open_learning_events
            WHERE starts_at IS NOT NULL
            ORDER BY starts_at"""
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        if str(row["status"] or "").upper() in FINAL_EVENT:
            continue
        if not _in_window(row["starts_at"], lo, hi):
            continue
        if row["telemost_conference_id"] and row["telemost_join_url"]:
            out.append(("event", int(row["id"]), "ok", True))
            continue
        try:
            result = create_conference()
            if result.get("status") == "ok":
                conn = database.connect()
                conn.execute(
                    """UPDATE open_learning_events
                          SET telemost_conference_id=?,telemost_join_url=?,updated_at=?
                        WHERE id=? AND (telemost_conference_id IS NULL OR telemost_join_url IS NULL)""",
                    (result["conference_id"], result["join_url"], database.now_iso(), int(row["id"])),
                )
                conn.commit(); conn.close()
            out.append(("event", int(row["id"]), result.get("status"), False))
        except Exception as exc:
            out.append(("event", int(row["id"]), "error", str(exc)[:120]))
    return out


def run_once():
    if not telemost_settings.auto_on_start():
        return {"status": "disabled_by_teacher", "items": []}
    lo, hi = _window()
    items = _prepare_individual(lo, hi) + _prepare_group(lo, hi) + _prepare_events(lo, hi)
    return {"status": "ok", "window_from": lo.isoformat(timespec="seconds"), "window_to": hi.isoformat(timespec="seconds"), "items": items}


def main():
    print(f"[telemost-precreate] started: {PRECREATE_MINUTES}m window, poll={POLL_SECONDS}s", flush=True)
    while True:
        try:
            result = run_once()
            errors = [x for x in result.get("items", []) if len(x) > 2 and x[2] == "error"]
            print(f"[telemost-precreate] status={result.get('status')} items={len(result.get('items', []))} errors={len(errors)}", flush=True)
            for item in errors:
                print("[telemost-precreate] error", item, flush=True)
        except Exception as exc:
            print("[telemost-precreate] loop error", type(exc).__name__, str(exc)[:200], flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
