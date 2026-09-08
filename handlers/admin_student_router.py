from __future__ import annotations

from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
)

import students_admin
from core import admin_roles


async def student_view(update, context):

    q = update.callback_query

    if not q:
        return

    if not admin_roles.is_admin_id(
        q.from_user.id
    ):
        return

    await q.answer()

    try:
        user_id = int(
            q.data.split("|", 1)[1]
        )
    except Exception:
        raise ApplicationHandlerStop

    print(
        "ADMIN_STUDENT_V4:",
        q.from_user.id,
        "user_id=",
        user_id,
        flush=True,
    )

    await students_admin.show_student(
        q,
        user_id,
    )

    raise ApplicationHandlerStop


def handler():

    return CallbackQueryHandler(
        student_view,
        pattern=r"^student_view\|",
    )
