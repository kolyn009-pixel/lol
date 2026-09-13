from __future__ import annotations

# Import the existing, recovered final feature module unchanged.
from . import handlers as _base
from handlers import regular_schedule_change_handlers
from core import schedule_sync
import database


async def _unified_refresh_calendar_and_reminders(context, lesson_ids):
    """Use the same Calendar/Telemost reconciliation as web and desktop flows."""
    return await schedule_sync.sync_lessons(context.application, lesson_ids)


# The legacy module still