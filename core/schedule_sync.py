from __future__ import annotations

"""Shared post-change synchronization for Calendar and lesson reminders.

Business logic changes lesson times first. This helper is then called by Telegram,
web or desktop adapters so there is only one reconciliation path.
"""

import asyncio
import database


async def sync_lessons(application, lesson_ids):
    import bot as tutor_bot
    synced = []
    failed = []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'})
            continue
        user = database.get_user(int(lesson['user_id']))
        if not user:
            failed.append({'lesson_id': raw_id, 'reason': 'student_not_found'})
            continue
        try:
            event_id = lesson['google_event_id']
            if lesson['lesson_status'] == 'CONFIRMED':
                if event_id:
                    await asyncio.to_thread(tutor_bot.update_google_event, event_id, user, lesson)
                else:
                    new_id = await asyncio.to_thread(tutor_bot.create_google_event, user, lesson)
                    tutor_bot.save_google_event_id(raw_id, new_id)
            elif event_id:
                deleted = await asyncio.to_thread(tutor_bot.delete_google_event, event_id)
                if deleted:
                    tutor_bot.save_google_event_id(raw_id, None)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'calendar_error', 'detail': type(exc).__name__})
            continue
        try:
            c = database.connect()
            c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?', (raw_id,))
            c.commit(); c.close()
            if application is not None and lesson['lesson_status'] == 'CONFIRMED':
                tutor_bot.schedule_lesson_reminders(application, raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'reminder_error', 'detail': type(exc).__name__})
            continue
        synced.append(raw_id)
    return {'synced_lesson_ids': synced, 'failed': failed}


def sync_lessons_blocking(lesson_ids):
    """Calendar-only reconciliation for synchronous web/API processes.

    Reminder re-scheduling requires the running Telegram Application and is left
    to the bot reconciliation job; stale reminder rows are removed immediately.
    """
    import bot as tutor_bot
    synced = []
    failed = []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'})
            continue
        user = database.get_user(int(lesson['user_id']))
        try:
            event_id = lesson['google_event_id']
            if lesson['lesson_status'] == 'CONFIRMED':
                if event_id:
                    tutor_bot.update_google_event(event_id, user, lesson)
                else:
                    new_id = tutor_bot.create_google_event(user, lesson)
                    tutor_bot.save_google_event_id(raw_id, new_id)
            elif event_id:
                if tutor_bot.delete_google_event(event_id):
                    tutor_bot.save_google_event_id(raw_id, None)
            c = database.connect()
            c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?', (raw_id,))
            c.commit(); c.close()
            synced.append(raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': type(exc).__name__})
    return {'synced_lesson_ids': synced, 'failed': failed}
