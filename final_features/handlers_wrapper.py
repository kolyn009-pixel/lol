from __future__ import annotations

# Import the existing, recovered final feature module unchanged.
from . import handlers as _base
from handlers import regular_schedule_change_handlers


def handlers():
    """Return legacy handlers plus the permanent-schedule conversation first.

    The specific ConversationHandler must be registered before broad ff_* callbacks.
    Keeping this wrapper separate avoids rewriting the large legacy handlers module.
    """
    return [regular_schedule_change_handlers.handler(), *_base.handlers()]


def __getattr__(name):
    return getattr(_base, name)
