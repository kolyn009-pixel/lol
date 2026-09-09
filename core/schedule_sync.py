from __future__ import annotations

"""Shared post-change reconciliation for Calendar and lesson reminders.

Business transactions change lesson times first. Adapters call this helper only
after commit, so an external Calendar failure can never roll back the schedule.
"""

import asyncio
import database


def _calendar_should_exist(lesson):
    return (
        lesson['lesson_status'] == 'CONFIRMED'
        and lesson['payment_status'] != 'AWAITING_PAYMENT'
    )


def _clear_reminders(lesson_id):
    c = database.connect()
    try:
        # Existing reminder bookkeeping is time-dependent; after a move old
        # timestamps must not survive. The running bot can schedule fresh jobs.
        if database.table_exists(c, 'lesson_reminders'):
            c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?', (int(lesson_id),))
        c.commit()
    finally:
        c.close()


async def sync_lessons(application, lesson_ids):
    import bot as tutor_bot
    synced, failed = [], []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'}); continue
        user = database.get_user(int(lesson['user_id']))
        if not user:
            failed.append({'lesson_id': raw_id, 'reason': 'student_not_found'}); continue
        try:
            event_id = lesson['google_event_id']
            if _calendar_should_exist(lesson):
                if event_id:
                    await asyncio.to_thread(tutor_bot.update_google_event, event_id, user, lesson)
                else:
                    new_id = await asyncio.to_thread(tutor_bot.create_google_event, user, lesson)
                    tutor_bot.save_google_event_id(raw_id, new_id)
            elif event_id:
                if await asyncio.to_thread(tutor_bot.delete_google_event, event_id):
                    tutor_bot.save_google_event_id(raw_id, None)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'calendar_error', 'detail': type(exc).__name__})
        try:
            _clear_reminders(raw_id)
            if application is not None and _calendar_should_exist(lesson):
                tutor_bot.schedule_lesson_reminders(application, raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'reminder_error', 'detail': type(exc).__name__})
        if not any(x['lesson_id'] == raw_id for x in failed):
            synced.append(raw_id)
    return {'synced_lesson_ids': synced, 'failed': failed}


def sync_lessons_blocking(lesson_ids):
    """Reconcile Calendar from synchronous web/API code after DB commit.

    Old reminder bookkeeping is cleared immediately. Fresh in-process Telegram
    jobs are intentionally created only by ``sync_lessons`` where an Application
    instance exists; the bot's normal reconciliation remains the fallback.
    """
    import bot as tutor_bot
    synced, failed = [], []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'}); continue
        user = database.get_user(int(lesson['user_id']))
        if not user:
            failed.append({'lesson_id': raw_id, 'reason': 'student_not_found'}); continue
        try:
            event_id = lesson['google_event_id']
            if _calendar_should_exist(lesson):
                if event_id:
                    tutor_bot.update_google_event(event_id, user, lesson)
                else:
                    new_id = tutor_bot.create_google_event(user, lesson)
                    tutor_bot.save_google_event_id(raw_id, new_id)
            elif event_id and tutor_bot.delete_google_event(event_id):
                tutor_bot.save_google_event_id(raw_id, None)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'calendar_error', 'detail': type(exc).__name__})
        try:
            _clear_reminders(raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'reminder_error', 'detail': type(exc).__name__})
        if not any(x['lesson_id'] == raw_id for x in failed):
            synced.append(raw_id)
    return {'synced_lesson_ids': synced, 'failed': failed}
