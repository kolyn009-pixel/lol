from __future__ import annotations

import education_profile
from handlers import education_admin


def install(application):
    """Activate college-aware registration after Application handlers exist.

    bot.main() builds the registration ConversationHandler before post_init.
    education_profile installs the replacement callbacks on __main__; this
    function then swaps only matching registration callbacks inside the
    already-built ConversationHandler. No production history/data is touched.
    """
    education_profile.install_runtime()
    education_admin.initialize()

    import __main__ as bot
    replacements = {
        "registration_name": getattr(bot, "registration_name", None),
        "registration_grade": getattr(bot, "registration_grade", None),
        "registration_phone": getattr(bot, "registration_phone", None),
    }

    def patch_handler(handler):
        callback = getattr(handler, "callback", None)
        name = getattr(callback, "__name__", "")
        replacement = replacements.get(name)
        if replacement is not None and callback is not replacement:
            handler.callback = replacement
        states = getattr(handler, "states", None)
        if isinstance(states, dict):
            for items in states.values():
                for child in items:
                    patch_handler(child)
        entries = getattr(handler, "entry_points", None)
        if entries:
            for child in entries:
                patch_handler(child)
        fallbacks = getattr(handler, "fallbacks", None)
        if fallbacks:
            for child in fallbacks:
                patch_handler(child)

    for group_handlers in application.handlers.values():
        for handler in group_handlers:
            patch_handler(handler)

    # Admin education/program actions run before legacy generic callbacks.
    for handler in education_admin.handlers():
        application.add_handler(handler, group=-169)
