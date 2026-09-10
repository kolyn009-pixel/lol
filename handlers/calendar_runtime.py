from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import database
from core import calendar_policy
from core.lesson_time import schedule_datetime, actual_datetime


SUBJECT_NAMES = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}


def _init_state_tables():
    c = database.connect()
    try:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS calendar_lesson_state (
                lesson_id INTEGER PRIMARY KEY,
                state_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS calendar_special_events (
                event_key TEXT PRIMARY KEY,
                google_event_id TEXT NOT NULL,
                state_key TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        c.commit()
    finally:
        c.close()


def _subject(lesson):
    raw = str(lesson["subject"] or "").upper()
    return SUBJECT_NAMES.get(raw, raw or "Занятие")


def _state_key(lesson):
    return "|".join(
        str(x or "") for x in (
            lesson["start_time"],
            lesson["end_time"],
            lesson["lesson_status"],
            lesson["payment_status"],
            lesson["started_at"],
            lesson["finished_at"],
            int(bool(lesson["is_trial"])),
            calendar_policy.lesson_state(lesson),
            calendar_policy.lesson_color_id(lesson),
            calendar_policy.lesson_summary_prefix(lesson),
        )
    )


def _stored_state(lesson_id):
    c = database.connect()
    try:
        row = c.execute(
            "SELECT state_key FROM calendar_lesson_state WHERE lesson_id=?",
            (int(lesson_id),),
        ).fetchone()
        return row["state_key"] if row else None
    finally:
        c.close()


def _save_state(lesson_id, key):
    c = database.connect()
    try:
        c.execute(
            """
            INSERT INTO calendar_lesson_state(lesson_id,state_key,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                state_key=excluded.state_key,
                updated_at=excluded.updated_at
            """,
            (int(lesson_id), str(key), database.now_iso()),
        )
        c.commit()
    finally:
        c.close()


def _delete_state(lesson_id):
    c = database.connect()
    try:
        c.execute("DELETE FROM calendar_lesson_state WHERE lesson_id=?", (int(lesson_id),))
        c.commit()
    finally:
        c.close()


def _fmt_actual(raw):
    if not raw:
        return "—"
    try:
        return actual_datetime(raw).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(raw)


def _lesson_body(bot_module, user, lesson):
    start_dt = schedule_datetime(lesson["start_time"])
    end_dt = schedule_datetime(lesson["end_time"])
    prefix = calendar_policy.lesson_summary_prefix(lesson)
    subject = _subject(lesson)
    title = f"{prefix}{user['name']} • {subject}"

    description = [
        calendar_policy.lesson_status_note(lesson),
        "",
        f"👤 Ученик: {user['name']}",
        f"🎓 Класс: {user['grade']}",
        f"📖 Предмет: {subject}",
        f"📅 План: {start_dt:%d.%m.%Y %H:%M}–{end_dt:%H:%M}",
    ]
    if lesson["started_at"]:
        description.append(f"▶️ Фактическое начало: {_fmt_actual(lesson['started_at'])}")
    if lesson["finished_at"]:
        description.append(f"⏹ Фактическое завершение: {_fmt_actual(lesson['finished_at'])}")
    description.extend([
        "",
        calendar_policy.lesson_payment_note(lesson),
        "",
        f"TutorBot lesson #{lesson['id']}",
    ])

    body = {
        "summary": title,
        "description": "\n".join(description),
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": bot_module.TIMEZONE_NAME,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": bot_module.TIMEZONE_NAME,
        },
        "extendedProperties": {
            "private": {
                "tutorbot_type": "LESSON",
                "tutorbot_lesson_id": str(lesson["id"]),
            }
        },
    }
    color = calendar_policy.lesson_color_id(lesson)
    if color:
        body["colorId"] = color
    return body


def _create_event(bot_module, user, lesson):
    if database.in_test_mode():
        return f"TEST_EVENT_{lesson['id']}"
    result = (
        bot_module.get_calendar_service()
        .events()
        .insert(calendarId=bot_module.CALENDAR_ID, body=_lesson_body(bot_module, user, lesson))
        .execute()
    )
    return result["id"]


def _update_event(bot_module, event_id, user, lesson):
    if database.in_test_mode():
        return event_id or f"TEST_EVENT_{lesson['id']}"
    if not event_id:
        return None
    result = (
        bot_module.get_calendar_service()
        .events()
        .update(
            calendarId=bot_module.CALENDAR_ID,
            eventId=event_id,
            body=_lesson_body(bot_module, user, lesson),
        )
        .execute()
    )
    return result["id"]


def _special_row(key):
    c = database.connect()
    try:
        return c.execute(
            "SELECT event_key,google_event_id,state_key FROM calendar_special_events WHERE event_key=?",
            (str(key),),
        ).fetchone()
    finally:
        c.close()


def _save_special(key, event_id, state_key):
    c = database.connect()
    try:
        c.execute(
            """
            INSERT INTO calendar_special_events(event_key,google_event_id,state_key,updated_at)
            VALUES(?,?,?,?)
            ON CONFLICT(event_key) DO UPDATE SET
                google_event_id=excluded.google_event_id,
                state_key=excluded.state_key,
                updated_at=excluded.updated_at
            """,
            (str(key), str(event_id), str(state_key), database.now_iso()),
        )
        c.commit()
    finally:
        c.close()


def _delete_special_row(key):
    c = database.connect()
    try:
        c.execute("DELETE FROM calendar_special_events WHERE event_key=?", (str(key),))
        c.commit()
    finally:
        c.close()


async def _sync_days_off(bot_module):
    current = {}
    for row in calendar_policy.closed_dates():
        key = calendar_policy.day_off_event_key(row["id"])
        state_key = f"{row['date']}|{row['comment'] or ''}"
        current[key] = True
        stored = _special_row(key)
        body = calendar_policy.day_off_event_body(row)
        try:
            if stored:
                if str(stored["state_key"]) != state_key:
                    await asyncio.to_thread(
                        bot_module.get_calendar_service().events().update(
                            calendarId=bot_module.CALENDAR_ID,
                            eventId=stored["google_event_id"],
                            body=body,
                        ).execute
                    )
                    _save_special(key, stored["google_event_id"], state_key)
            else:
                result = await asyncio.to_thread(
                    bot_module.get_calendar_service().events().insert(
                        calendarId=bot_module.CALENDAR_ID,
                        body=body,
                    ).execute
                )
                _save_special(key, result["id"], state_key)
        except Exception as exc:
            print("CALENDAR DAY OFF SYNC:", key, repr(exc))

    c = database.connect()
    try:
        stale = list(c.execute(
            "SELECT event_key,google_event_id FROM calendar_special_events WHERE event_key LIKE 'tutorbot-day-off-%'"
        ).fetchall())
    finally:
        c.close()
    for row in stale:
        if row["event_key"] in current:
            continue
        try:
            await asyncio.to_thread(bot_module.delete_google_event, row["google_event_id"])
            _delete_special_row(row["event_key"])
        except Exception as exc:
            print("CALENDAR DAY OFF DELETE:", row["event_key"], repr(exc))


async def _sync(bot_module, application=None):
    _init_state_tables()
    c = database.connect()
    try:
        lessons = list(c.execute(
            """
            SELECT * FROM lessons
            WHERE start_time >= datetime('now','-90 day')
            ORDER BY datetime(start_time),id
            """
        ).fetchall())
    finally:
        c.close()

    created = updated = deleted = 0
    for lesson in lessons:
        event_id = str(lesson["google_event_id"] or "").strip()
        if calendar_policy.should_delete_lesson_event(lesson):
            if event_id:
                ok = await asyncio.to_thread(bot_module.delete_google_event, event_id)
                if ok:
                    bot_module.save_google_event_id(lesson["id"], None)
                    _delete_state(lesson["id"])
                    deleted += 1
            continue

        user = database.get_user(int(lesson["user_id"]))
        if not user:
            continue

        key = _state_key(lesson)
        try:
            if not event_id:
                # Future lessons of every payment state belong in Calendar.
                # Recent completed history is recreated after the old sync deleted it.
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
    """
    tutor.db is the source of truth.
    TG, VK and background jobs all become visible
    in Google Calendar through this one sync owner.
    """
    try:
        import sys

        runtime = sys.modules.get(
            "__main__"
        )

        if runtime is None:
            import bot as runtime

        await _sync(
            runtime,
            getattr(
                context,
                "application",
                None,
            ),
        )

    except Exception as exc:
        print(
            "GOOGLE CALENDAR LIVE SYNC ERROR:",
            repr(exc),
            flush=True,
        )

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

    if (
        application is not None
        and getattr(
            application,
            "job_queue",
            None,
        )
    ):
        names = {
            job.name
            for job
            in application.job_queue.jobs()
        }

        if (
            "calendar_policy_live_sync"
            not in names
        ):
            application.job_queue.run_repeating(
                _live_calendar_sync_job,
                interval=20,
                first=5,
                name="calendar_policy_live_sync",
            )
