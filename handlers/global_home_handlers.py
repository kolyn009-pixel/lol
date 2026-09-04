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

    # Не очищаем parent_acting_student_id до того,
    # как проверили режим родителя.
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

    # ========================================================
    # TEST MODE
    # ========================================================

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

    # ========================================================
    # ADMIN
    # ========================================================

    elif admin_roles.is_admin_id(
        tid
    ):

        text = (
            admin.admin_home_text()
        )

        markup = (
            admin.admin_menu()
        )

    # ========================================================
    # NORMAL USER
    # ========================================================

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

        # ----------------------------------------------------
        # Parent acting as student
        # ----------------------------------------------------

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

                    # Главное:
                    # никто после нас уже не
                    # перерисовывает это сообщение.
                    raise ApplicationHandlerStop

        # ----------------------------------------------------
        # Parent home
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Student home
        # ----------------------------------------------------

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

    # После выбора роли уже можно
    # очистить временные состояния.
    #
    # Для обычного возвращения ученика
    # на главную нам больше ничего
    # от старого flow не требуется.

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

    # КРИТИЧЕСКАЯ ЧАСТЬ:
    # запрещаем bot.py / payments.py /
    # другим поздним handler-группам
    # повторно обработать main/global_home.
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
    ]
