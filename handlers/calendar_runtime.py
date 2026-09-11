from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import database
from core import calendar_policy


def _connect():
    c = database.connect()
    c.row_factory = sqlite3.Row
    return c


def _init_state_tables():
    c = _connect()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS calendar_lesson_state (
                lesson_id INTEGER PRIMARY KEY,
                state_key TEXT NOT NULL,
                synced_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS calendar_special_events (
                event_key TEXT PRIMARY KEY,
                google_event_id TEXT,
                state_key TEXT NOT NULL,
                synced_at TEXT NOT NULL
            )
        """)
        c.commit()
    finally:
        c.close()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _state_key(lesson):
    values = []
    for key in (
        "start_time", "end_time", "lesson_status", "payment_status",
        "price", "subject", "duration_minutes", "is_trial",
    ):
        try:
            values.append(lesson[key])
        except Exception:
            values.append(None)
    return json.dumps(values, ensure_ascii=False, default=str)


def _stored_state(lesson_id):
    c = _connect()
    try:
        row = c.execute(
            "SELECT state_key FROM calendar_lesson_state WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
        return row["state_key"] if row else None
    finally:
        c.close()


def _save_state(lesson_id, key):
    c = _connect()
    try:
        c.execute("""
            INSERT INTO calendar_lesson_state(lesson_id,state_key,synced_at)
            VALUES(?,?,?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                state_key=excluded.state_key,
                synced_at=excluded.synced_at
        """, (int(lesson_id), key, _now_iso()))
        c.commit()
    finally:
        c.close()


def _drop_state(lesson_id):
    c = _connect()
    try:
        c.execute("DELETE FROM calendar_lesson_state WHERE lesson_id=?", (int(lesson_id),))
        c.commit()
    finally:
        c.close()


def _create_event(bot_module, user, lesson):
    return calendar_policy.create_google_event(bot_module, user, lesson)


def _update_event(bot_module, event_id, user, lesson):
    return calendar_policy.update_google_event(bot_module, event_id, user, lesson)


def _delete_event(bot_module, event_id):
    return calendar_policy.delete_google_event(bot_module, event_id)


async def _sync_days_off(bot_module):
    # Existing day-off integration is deliberately best-effort. Lesson sync is
    # the latency-sensitive path; day-off materialization can be added here
    # without changing ownership of Calendar writes.
    return None


async def _sync(bot_module, application=None):
    """Synchronize the relevant lesson window with Google Calendar.

    The previous 20-second cadence repeatedly walked the same SQLite rows and
    could invoke Google Calendar from the Telegram application's event loop.
    State keys keep writes incremental; the wider scan now runs at a sane
    cadence while direct lesson mutations still call ensure_google_event().
    """
    now = datetime.now(timezone.utc)
    lower = (now - timedelta(days=14)).isoformat()
    upper = (now + timedelta(days=120)).isoformat()

    c = _connect()
    try:
        lessons = c.execute("""
            SELECT * FROM lessons
            WHERE start_time BETWEEN ? AND ?
               OR (google_event_id IS NOT NULL AND google_event_id != '')
            ORDER BY start_time
        """, (lower, upper)).fetchall()
    finally:
        c.close()

    created = updated = deleted = 0
    for lesson in lessons:
        event_id = str(lesson["google_event_id"] or "").strip()
        should_delete = calendar_policy.should_delete_lesson_event(lesson)
        if should_delete:
            if event_id:
                try:
                    await asyncio.to_thread(_delete_event, bot_module, event_id)
                    try:
                        bot_module.save_google_event_id(lesson["id"], None)
                    except Exception:
                        pass
                    _drop_state(lesson["id"])
                    deleted += 1
                except Exception as exc:
                    print("GOOGLE CALENDAR POLICY DELETE:", lesson["id"], repr(exc))
            continue

        user = database.get_user(int(lesson["user_id"]))
        if not user:
            continue

        key = _state_key(lesson)
        try:
            if not event_id:
                new_id = await asyncio.to_thread(_create_event, bot_module, user, lesson)
                bot_module.save_google_event_id(lesson["id"], new_id)
                _save_state(lesson["id"], key)
                created += 1
            elif _stored_state(lesson["id"]) != key:
                await asyncio.to_thread(_update_event, bot_module, event_id, user, lesson)
                _save_state(lesson["id"], key)
                updated += 1
        except Exception as exc:
            print("GOOGLE CALENDAR POLICY SYNC:", lesson["id"], repr(exc))

    await _sync_days_off(bot_module)
    if created or updated or deleted:
        print(
            "GOOGLE CALENDAR POLICY:",
            f"created={created}",
            f"updated={updated}",
            f"deleted={deleted}",
        )
    return {"created": created, "updated": updated, "deleted": deleted}


async def _live_calendar_sync_job(context):
    """Periodic safety-net sync; direct mutations remain the fast path."""
    try:
        import sys
        runtime = sys.modules.get("__main__")
        if runtime is None:
            import bot as runtime
        await _sync(runtime, getattr(context, "application", None))
    except Exception as exc:
        print("GOOGLE CALENDAR LIVE SYNC ERROR:", repr(exc), flush=True)


def install(application=None):
    """Patch the live Calendar runtime without duplicating job scheduling."""
    import sys

    bot_module = sys.modules.get("__main__")
    if (
        bot_module is None
        or not hasattr(bot_module, "get_calendar_service")
        or not hasattr(bot_module, "save_google_event_id")
    ):
        import bot as bot_module

    if getattr(bot_module, "_calendar_policy_v2_installed", False):
        return

    def create_google_event(user, lesson):
        event_id = _create_event(bot_module, user, lesson)
        _save_state(lesson["id"], _state_key(lesson))
        return event_id

    def update_google_event(event_id, user, lesson):
        result = _update_event(bot_module, event_id, user, lesson)
        _save_state(lesson["id"], _state_key(lesson))
        return result

    async def ensure_google_event(lesson_id):
        lesson = database.get_lesson(int(lesson_id))
        if not lesson or calendar_policy.should_delete_lesson_event(lesson):
            return None
        user = database.get_user(int(lesson["user_id"]))
        if not user:
            return None
        event_id = str(lesson["google_event_id"] or "").strip()
        try:
            if event_id:
                await asyncio.to_thread(_update_event, bot_module, event_id, user, lesson)
                _save_state(lesson["id"], _state_key(lesson))
                return event_id
            event_id = await asyncio.to_thread(_create_event, bot_module, user, lesson)
            bot_module.save_google_event_id(lesson["id"], event_id)
            _save_state(lesson["id"], _state_key(lesson))
            return event_id
        except Exception as exc:
            print("GOOGLE CALENDAR ENSURE POLICY:", lesson_id, repr(exc))
            return None

    async def sync_google_calendar(application=None):
        return await _sync(bot_module, application)

    bot_module.create_google_event = create_google_event
    bot_module.update_google_event = update_google_event
    bot_module.ensure_google_event = ensure_google_event
    bot_module.sync_google_calendar = sync_google_calendar
    bot_module._calendar_policy_v2_installed = True
    _init_state_tables()

    if application is not None and getattr(application, "job_queue", None):
        names = {job.name for job in application.job_queue.jobs()}
        if "calendar_policy_live_sync" not in names:
            application.job_queue.run_repeating(
                _live_calendar_sync_job,
                interval=300,
                first=30,
                name="calendar_policy_live_sync",
            )
