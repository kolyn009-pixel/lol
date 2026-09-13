from __future__ import annotations

# Import the existing, recovered final feature module unchanged.
from . import handlers as _base
from handlers import regular_schedule_change_handlers
from core import schedule_sync


async def _unified_refresh_calendar_and_reminders(context, lesson_ids):
    """Use the same Calendar/Telemost reconciliation as web and desktop flows."""
    return await schedule_sync.sync_lessons(context.application, lesson_ids)


# The legacy module still contains direct calls into bot.py's old Google Calendar
# implementation. Override only that helper here so existing Telegram callbacks keep
# their behavior while all external lesson integrations go through one code path.
_base._refresh_calendar_and_reminders = _unified_refresh_calendar_and_reminders


def handlers():
    """Return legacy handlers plus the permanent-schedule conversation first.

    The specific ConversationHandler must be registered before broad ff_* callbacks.
    Keeping this wrapper separate avoids rewriting the large legacy handlers module.
    """
    return [regular_schedule_change_handlers.handler(), *_base.handlers()]


def __getattr__(name):
    return getattr(_base, name)
