from __future__ import annotations

"""Compatibility wrapper around the recovered final-feature handlers.

Keep the large legacy module unchanged while routing schedule mutations through
Adelia's canonical integration path and registering the permanent-schedule flow
before broad final-feature callbacks.
"""

from . import handlers as _base
from handlers import regular_schedule_change_handlers
from core import schedule_sync


async def _unified_refresh_calendar_and_reminders(context, lesson_ids):
    return await schedule_sync.sync_lessons(context.application, lesson_ids)


# Legacy callbacks call this helper by module global lookup, so replacing it on
# the imported module redirects those calls without copying the large handler.
_base._refresh_calendar_and_reminders = _unified_refresh_calendar_and_reminders


def handlers():
    return [regular_schedule_change_handlers.handler(), *_base.handlers()]


def __getattr__(name):
    return getattr(_base, name)
