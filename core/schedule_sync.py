from __future__ import annotations

"""Shared post-change reconciliation for external lesson services and reminders.

Business transactions change lesson times first. External integrations run only
after commit, so provider failures can never roll back the TutorBot schedule.
All Calendar/Telemost work is routed through ``integrations.lesson_sync`` to
avoid the legacy duplicate Google implementation in ``bot.py``.
"""

import database


def _external_should_exist(lesson):
    return (
        str(lesson['lesson_status'] or '').upper() == 'CONFIRMED'
        and str(lesson['payment_status'] or '').upper() != 'AWAITING_PAYMENT'
    )


def _clear_reminders(lesson_id):
    c = database.connect()
    try:
        if database.table_exists(c, 'lesson_reminders'):
            c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?', (int(lesson_id),))
        c.commit()
    finally:
        c.close()


def _sync_external(lesson_id, lesson):
    from integrations import lesson_sync
    if _external_should_exist(lesson):
        result = lesson_sync.sync_lesson(int(lesson_id), google=True, telemost=True)
    else:
        result = lesson_sync.cancel_lesson(int(lesson_id))
    failures = []
    for provider in ('google', 'telemost'):
        item = result.get(provider)
        if isinstance(item, dict) and item.get('status') == 'error':
            failures.append({'lesson_id': int(lesson_id), 'reason': f'{provider}_error', 'detail': item.get('error')})
    return result, failures


async def sync_lessons(application, lesson_ids):
    """Reconcile external services and rebuild in-process reminder jobs."""
    import asyncio
    import bot as tutor_bot
    synced, failed = [], []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'}); continue
        try:
            _, integration_failures = await asyncio.to_thread(_sync_external, raw_id, lesson)
            failed.extend(integration_failures)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'integration_error', 'detail': type(exc).__name__})
        try:
            _clear_reminders(raw_id)
            if application is not None and _external_should_exist(lesson):
                tutor_bot.schedule_lesson_reminders(application, raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'reminder_error', 'detail': type(exc).__name__})
        if not any(x['lesson_id'] == raw_id for x in failed):
            synced.append(raw_id)
    return {'synced_lesson_ids': synced, 'failed': failed}


def sync_lessons_blocking(lesson_ids):
    """Reconcile integrations from synchronous web/API code after DB commit."""
    synced, failed = [], []
    for raw_id in dict.fromkeys(int(x) for x in (lesson_ids or []) if x is not None):
        lesson = database.get_lesson(raw_id)
        if not lesson:
            failed.append({'lesson_id': raw_id, 'reason': 'lesson_not_found'}); continue
        try:
            _, integration_failures = _sync_external(raw_id, lesson)
            failed.extend(integration_failures)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'integration_error', 'detail': type(exc).__name__})
        try:
            _clear_reminders(raw_id)
        except Exception as exc:
            failed.append({'lesson_id': raw_id, 'reason': 'reminder_error', 'detail': type(exc).__name__})
        if not any(x['lesson_id'] == raw_id for x in failed):
            synced.append(raw_id)
    return {'synced_lesson_ids': synced, 'failed': failed}
