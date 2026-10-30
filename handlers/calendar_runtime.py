from __future__ import annotations

"""Compatibility layer for legacy Telegram Calendar call sites.

The canonical Google Calendar owner is ``integrations.google_calendar``.  Older
Telegram handlers still call ``bot.create_google_event`` / ``update_google_event`` /
``delete_google_event`` / ``ensure_google_event``; this module patches those entry
points so they cannot create a second event through the legacy implementation.

A lightweight state table is retained only as a reconciliation fingerprint.  It
never stores provider ownership; the provider event id lives in
``lesson_external_integrations``.
"""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import database


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
                synced_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(calendar_lesson_state)").fetchall()
        }
        if "synced_at" not in columns:
            c.execute("ALTER TABLE calendar_lesson_state ADD COLUMN synced_at TEXT")
        if "updated_at" not in columns:
            c.execute("ALTER TABLE calendar_lesson_state ADD COLUMN updated_at TEXT")
        c.commit()
    finally:
        c.close()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _state_key(lesson):
    values = []
    for key in (
        "start_time", "end_time", "lesson_status", "payment_status",
        "price", "subject", "duration_minutes", "is_trial", "meeting_url",
        "rescheduled_from_lesson_id",
    ):
        try:
            values.append(lesson[key])
        except Exception:
            values.append(None)
    values.insert(0, "reschedule-details-v1")
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
        columns = {
            row["name"]
            for row in c.execute("PRAGMA table_info(calendar_lesson_state)").fetchall()
        }
        now = _now_iso()
        if "updated_at" in columns:
            c.execute("""
                INSERT INTO calendar_lesson_state(
                    lesson_id, state_key, synced_at, updated_at
                )
                VALUES(?,?,?,?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    state_key=excluded.state_key,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at
            """, (int(lesson_id), key, now, now))
        else:
            c.execute("""
                INSERT INTO calendar_lesson_state(lesson_id,state_key,synced_at)
                VALUES(?,?,?)
                ON CONFLICT(lesson_id) DO UPDATE SET
                    state_key=excluded.state_key,
                    synced_at=excluded.synced_at
            """, (int(lesson_id), key, now))
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


def _should_exist(lesson):
    from core.calendar_policy import should_keep_lesson_event
    return bool(should_keep_lesson_event(lesson))


def _canonical_event_id(lesson_id):
    c = _connect()
    try:
        if not database.table_exists(c, "lesson_external_integrations"):
            return None
        row = c.execute(
            "SELECT google_event_id "
            "FROM lesson_external_integrations "
            "WHERE lesson_id=? LIMIT 1",
            (int(lesson_id),),
        ).fetchone()
        if not row:
            return None
        return str(row["google_event_id"] or "").strip() or None
    finally:
        c.close()


def _mirror_legacy_event_id(lesson_id, event_id):
    """Keep the old lessons.google_event_id field readable during migration."""
    c = _connect()
    try:
        c.execute(
            "UPDATE lessons SET google_event_id=?, updated_at=COALESCE(updated_at, ?) WHERE id=?",
            (event_id, database.now_iso(), int(lesson_id)),
        )
        c.commit()
    finally:
        c.close()


def _canonical_sync(lesson_id):
    from integrations.google_calendar import sync_lesson

    result = sync_lesson(int(lesson_id))
    event_id = result.get("event_id") if isinstance(result, dict) else None
    if event_id:
        _mirror_legacy_event_id(lesson_id, event_id)
    lesson = database.get_lesson(int(lesson_id))
    if lesson:
        _save_state(int(lesson_id), _state_key(lesson))
    return event_id


def _canonical_cancel(lesson_id):
    from integrations.google_calendar import cancel_lesson

    result = cancel_lesson(int(lesson_id))
    _mirror_legacy_event_id(lesson_id, None)
    _drop_state(lesson_id)
    return result


def _lesson_id_for_event(event_id):
    if not event_id:
        return None
    c = _connect()
    try:
        row = None
        if database.table_exists(c, "lesson_external_integrations"):
            row = c.execute(
                "SELECT lesson_id FROM lesson_external_integrations WHERE google_event_id=? LIMIT 1",
                (str(event_id),),
            ).fetchone()
        if row:
            return int(row["lesson_id"])
        row = c.execute(
            "SELECT id FROM lessons WHERE google_event_id=? LIMIT 1",
            (str(event_id),),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        c.close()


async def _sync(application=None):
    """Periodic safety-net reconciliation using the canonical provider adapter."""
    now = datetime.now(timezone.utc)
    lower = (now - timedelta(days=14)).isoformat()
    upper = (now + timedelta(days=120)).isoformat()

    c = _connect()
    try:
        canonical_ids = []
        if database.table_exists(c, 'lesson_external_integrations'):
            canonical_ids = [int(r[0]) for r in c.execute("SELECT lesson_id FROM lesson_external_integrations WHERE google_event_id IS NOT NULL AND google_event_id != ''")]
        lessons = c.execute("""
            SELECT * FROM lessons
            WHERE start_time BETWEEN ? AND ?
               OR (google_event_id IS NOT NULL AND google_event_id != '')
               OR rescheduled_to_lesson_id IS NOT NULL
            ORDER BY start_time
        """, (lower, upper)).fetchall()
    finally:
        c.close()

    by_id = {int(row['id']): row for row in lessons}
    for lid in canonical_ids:
        if lid not in by_id:
            row = database.get_lesson(lid)
            if row:
                by_id[lid] = row
    lessons = list(by_id.values())
    created_or_updated = deleted = skipped = 0
    for lesson in lessons:
        lesson_id = int(lesson["id"])
        key = _state_key(lesson)
        try:
            if not _should_exist(lesson):
                if _stored_state(lesson_id) != key:
                    await asyncio.to_thread(_canonical_cancel, lesson_id)
                    _save_state(lesson_id, key)
                    deleted += 1
                else:
                    skipped += 1
                continue

            if (
                _stored_state(lesson_id) == key
                and _canonical_event_id(lesson_id)
            ):
                skipped += 1
                continue

            await asyncio.to_thread(_canonical_sync, lesson_id)
            created_or_updated += 1
        except Exception as exc:
            print("GOOGLE CALENDAR CANONICAL SYNC:", lesson_id, repr(exc), flush=True)

    if created_or_updated or deleted:
        print(
            "GOOGLE CALENDAR CANONICAL:",
            f"synced={created_or_updated}",
            f"deleted={deleted}",
            f"skipped={skipped}",
            flush=True,
        )
    return {"synced": created_or_updated, "deleted": deleted, "skipped": skipped}


async def _live_calendar_sync_job(context):
    try:
        await _sync(getattr(context, "application", None))
    except Exception as exc:
        print("GOOGLE CALENDAR LIVE SYNC ERROR:", repr(exc), flush=True)


def install(application=None):
    """Patch legacy bot Calendar functions to the single canonical owner."""
    import sys

    bot_module = sys.modules.get("__main__")
    if bot_module is None or not hasattr(bot_module, "save_google_event_id"):
        import bot as bot_module

    if getattr(bot_module, "_calendar_policy_v3_installed", False):
        return

    def create_google_event(user, lesson):
        lesson_id = int(lesson["id"])
        return _canonical_sync(lesson_id)

    def update_google_event(event_id, user, lesson):
        lesson_id = int(lesson["id"])
        return _canonical_sync(lesson_id)

    def delete_google_event(event_id):
        lesson_id = _lesson_id_for_event(event_id)
        if lesson_id is None:
            # Unknown legacy event: do not invoke the old provider writer.  It
            # can be cleaned by a one-time migration if encountered in prod.
            return False
        _canonical_cancel(lesson_id)
        return True

    async def ensure_google_event(lesson_id):
        lesson = database.get_lesson(int(lesson_id))
        if not lesson:
            return None
        try:
            if not _should_exist(lesson):
                await asyncio.to_thread(_canonical_cancel, int(lesson_id))
                return None
            return await asyncio.to_thread(_canonical_sync, int(lesson_id))
        except Exception as exc:
            print("GOOGLE CALENDAR ENSURE CANONICAL:", lesson_id, repr(exc), flush=True)
            return None

    async def sync_google_calendar(application=None):
        return await _sync(application)

    bot_module.create_google_event = create_google_event
    bot_module.update_google_event = update_google_event
    bot_module.delete_google_event = delete_google_event
    bot_module.ensure_google_event = ensure_google_event
    bot_module.sync_google_calendar = sync_google_calendar
    bot_module._calendar_policy_v2_installed = True
    bot_module._calendar_policy_v3_installed = True
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
