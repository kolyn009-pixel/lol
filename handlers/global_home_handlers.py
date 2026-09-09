from telegram import Update

from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    ApplicationHandlerStop,
)

import database
import admin

from core import (
    admin_roles,
    test_lab,
)
from handlers import homework_channel_handlers


async def home(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    q = update.callback_query

    if q:
        await q.answer()

    tid = int(
        update.effective_user.id
    )

    data = (
        str(q.data or "")
        if q
        else ""
    )

    acting_student_id = (
        context.user_data.get(
            "parent_acting_student_id"
        )
    )

    test_active = bool(
        test_lab.active(tid)
        and (
            test_lab._is_tester_prod(tid)
            or admin_roles.is_owner(tid)
        )
    )

    if test_active:

        database.set_test_mode(True)

        test_lab.ensure_test_db()

        role = (
            test_lab.get_test_role(tid)
        )

        import bot as b

        if role == "TEACHER":

            text = (
                admin.admin_home_text()
            )

            markup = (
                admin.admin_menu()
            )

        elif role == "PARENT":

            parent = (
                database
                .get_parent_by_telegram_id(
                    tid
                )
            )

            if (
                parent
                and parent["active"]
            ):

                text = (
                    b.parent_home_text(
                        parent
                    )
                )

                markup = (
                    b.parent_menu()
                )

            else:

                text = (
                    "🧪 Режим родителя\n\n"
                    "В тестовой базе пока "
                    "нет профиля родителя."
                )

                markup = None

        else:

            user = (
                database
                .get_user_by_telegram_id(
                    tid
                )
            )

            if (
                user
                and user["active"]
            ):

                text = (
                    b.student_home_text(
                        user
                    )
                )

                markup = (
                    b.student_menu(
                        user["id"]
                    )
                )

            else:

                text = (
                    "🧪 Режим ученика\n\n"
                    "В тестовой базе пока "
                    "нет профиля ученика."
                )

                markup = None

    elif admin_roles.is_admin_id(
        tid
    ):

        text = (
            admin.admin_home_text()
        )

        markup = (
            admin.admin_menu()
        )

    else:

        parent = (
            database
            .get_parent_by_telegram_id(
                tid
            )
        )

        user = (
            database
            .get_user_by_telegram_id(
                tid
            )
        )

        import bot as b

        if (
            parent
            and parent["active"]
            and acting_student_id
            and data == "main"
        ):

            allowed = {
                int(row["id"])
                for row in (
                    database
                    .get_parent_students(
                        parent["id"]
                    )
                )
            }

            if (
                int(
                    acting_student_id
                )
                in allowed
            ):

                student = (
                    database.get_user(
                        int(
                            acting_student_id
                        )
                    )
                )

                if (
                    student
                    and student["active"]
                ):

                    await (
                        b.show_parent_child_card(
                            q,
                            parent,
                            student,
                        )
                    )

                    raise ApplicationHandlerStop

        if (
            parent
            and parent["active"]
        ):

            text = (
                b.parent_home_text(
                    parent
                )
            )

            markup = (
                b.parent_menu()
            )

        elif (
            user
            and user["active"]
        ):

            text = (
                b.student_home_text(
                    user
                )
            )

            markup = (
                b.student_menu(
                    user["id"]
                )
            )

        else:

            text = (
                "🏠 Я не нашла профиль.\n\n"
                "Нажмите /start — "
                "помогу зарегистрироваться 💜"
            )

            markup = None

    if not (
        parent
        if "parent" in locals()
        else False
    ):
        context.user_data.clear()

    if q:

        await q.edit_message_text(
            text,
            reply_markup=markup,
        )

    else:

        await (
            update.message
            .reply_text(
                text,
                reply_markup=markup,
            )
        )

    raise ApplicationHandlerStop


def handlers():

    return [
        CommandHandler(
            "home",
            home,
        ),

        CallbackQueryHandler(
            home,
            pattern=(
                r"^(?:main|global_home)$"
            ),
        ),
        *homework_channel_handlers.handlers(),
    ]
