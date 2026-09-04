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

    # Карточка ученика — только для преподавателя / админа.
    if not admin_roles.is_admin_id(
        q.from_user.id
    ):
        return

    await q.answer()

    try:

        user_id = int(
            q.data.split(
                "|",
                1
            )[1]
        )

    except Exception:

        raise ApplicationHandlerStop


    print(
        "ADMIN STUDENT ROUTER:",
        user_id,
        "-> students_admin.show_student"
    )


    # Единственный канонический экран карточки.
    await students_admin.show_student(
        q,
        user_id,
    )


    # КРИТИЧЕСКИ:
    # никакой handler из group 0 / 999 после этого
    # не имеет права снова перерисовать student_view.
    raise ApplicationHandlerStop


def install(application):

    application.add_handler(
        CallbackQueryHandler(
            student_view,
            pattern=r"^student_view\|",
        ),
        group=-168,
    )
