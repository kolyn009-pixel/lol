from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

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
from handlers import homework_channel_handlers, web_portal_login, payment_hub_handlers, payment_menu_patch


def _with_web_button(markup, role):
    """Add a prominent full-width web-cabinet entry at the bottom of home menus."""
    if not markup or role not in {"student", "teacher", "parent"}:
        return markup
    rows = [list(row) for row in markup.inline_keyboard]
    if role == "teacher":
        callback, label = "web_teacher_code", "🌐 ОТКРЫТЬ АДЕЛИЯ • КАБИНЕТ"
    elif role == "parent":
        callback, label = "web_parent_code", "🌐 ОТКРЫТЬ АДЕЛИЯ • КАБИНЕТ"
    else:
        callback, label = "web_student_code", "🌐 ОТКРЫТЬ АДЕЛИЯ • ЛИЧНЫЙ КАБИНЕТ"
    if not any(getattr(button, "callback_data", None) == callback for row in rows for button in row):
        rows.append([InlineKeyboardButton(label, callback_data=callback)])
    return InlineKeyboardMarkup(rows)


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

    web_role = None

    if test_active:

        database.set_test_mode(True)

        test_lab.ensure_test_db()

        role = (
            test_lab.get_test_role(tid)
        )

        import bot as b
        payment_menu_patch.install()

        if role == "TEACHER":

            text = (
                admin.admin_home_text()
            )

            markup = (
                admin.admin_menu()
            )
            web_role = "teacher"

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
                web_role = "parent"

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
                web_role = "student"

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
        web_role = "teacher"

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
        payment_menu_patch.install()

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
            web_role = "parent"

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
            web_role = "student"

        else:

            text = (
                "🏠 Я не нашла профиль.\n\n"
                "Нажмите /start — "
                "помогу зарегистрироваться 💜"
            )

            markup = None

    markup = _with_web_button(markup, web_role)

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
        *payment_hub_handlers.handlers(),
        *web_portal_login.handlers(),
        *homework_channel_handlers.handlers(),
    ]