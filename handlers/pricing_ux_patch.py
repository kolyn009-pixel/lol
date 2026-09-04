from __future__ import annotations

import database
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ApplicationHandlerStop
from handlers import review_v2, runtime_patch_v2
from core import admin_roles


def _grade_for_user(user_id):
    c = database.connect()
    try:
        row = c.execute("SELECT grade FROM users WHERE id=?", (int(user_id),)).fetchone()
        return int(row["grade"]) if row and row["grade"] is not None else None
    finally:
        c.close()


def _effective_price_for_lesson_row(row):
    try:
        return int(review_v2._lesson_price(row))
    except Exception:
        return int(row["price"] or 0)


def _patch_review_grade():
    if getattr(review_v2, "_adelia_grade_patch", False):
        return

    original_payment_cases = review_v2._payment_cases
    original_no_next_cases = review_v2._no_next_cases
    original_case_text = review_v2._case_text
    original_case_keyboard = review_v2._case_keyboard

    def payment_cases():
        cases = original_payment_cases()
        for case in cases:
            case["grade"] = _grade_for_user(case["user_id"])
        return cases

    def no_next_cases():
        cases = original_no_next_cases()
        for case in cases:
            case["grade"] = _grade_for_user(case["user_id"])
        return cases

    def case_text(case, index, total):
        text = original_case_text(case, index, total)
        grade = case.get("grade")
        if grade is not None:
            text = text.replace(
                f"👤 {case['name']}",
                f"👤 {case['name']} • {grade} класс",
                1,
            )
        return text

    def case_keyboard(case, index):
        kb = original_case_keyboard(case, index)
        rows = [list(row) for row in kb.inline_keyboard]
        if case.get("kind") == "PAYMENT_NEXT":
            rows.insert(0, [
                InlineKeyboardButton(
                    "✅ Отметить оплачено",
                    callback_data=f"mh_review_manual_paid|{index}|{int(case['lesson_id'])}",
                )
            ])
        return InlineKeyboardMarkup(rows)

    review_v2._payment_cases = payment_cases
    review_v2._no_next_cases = no_next_cases
    review_v2._case_text = case_text
    review_v2._case_keyboard = case_keyboard
    review_v2._adelia_grade_patch = True


async def _primary_review_entry(update, context):
    """Route every daily-review entry to the sequential review_v2 flow."""
    q = update.callback_query
    if not q:
        return

    await q.answer()
    context.user_data["mh_review_started_at"] = review_v2._now().isoformat(timespec="seconds")
    context.user_data["mh_review_entry"] = str(q.data or "ux_review_start")
    await review_v2._show(q, context, 0)


def _install_primary_review_route(application):
    if application is None:
        return
    if getattr(application, "_adelia_primary_review_route", False):
        return

    application.add_handler(
        CallbackQueryHandler(
            _primary_review_entry,
            pattern=r"^ux_review_start(?:\|.*)?$",
        ),
        group=-100,
    )
    application._adelia_primary_review_route = True


def _manual_paid_case(context, index, lesson_id):
    cases = context.user_data.get("mh_review_cases") or review_v2.review_cases(include_done=True)
    for case in cases:
        if case.get("kind") == "PAYMENT_NEXT" and int(case.get("lesson_id") or 0) == int(lesson_id):
            return case
    try:
        return cases[max(0, min(int(index), len(cases) - 1))] if cases else None
    except Exception:
        return None


def _record_manual_lesson_payment(lesson_id):
    lesson = database.get_lesson(int(lesson_id))
    if lesson is None:
        raise ValueError("Занятие не найдено")
    if str(lesson["payment_status"] or "") == "PAID":
        return None, int(lesson["price"] or 0)
    if str(lesson["payment_status"] or "") != "AWAITING_PAYMENT":
        raise ValueError("У этого занятия сейчас нет ожидаемой оплаты")

    amount = _effective_price_for_lesson_row(lesson)

    c = database.connect()
    try:
        c.execute(
            "UPDATE lessons SET price=?, updated_at=? WHERE id=?",
            (int(amount), database.now_iso(), int(lesson_id)),
        )
        c.commit()
    finally:
        c.close()

    payment_id = database.create_lesson_payment(int(lesson_id))
    database.approve_payment(int(payment_id))

    try:
        database.log_automation_delivery(
            "manual_lesson_payment", "OK", "LESSON", int(lesson_id), f"amount={int(amount)}"
        )
    except Exception:
        pass

    return int(payment_id), int(amount)


async def _manual_paid_callbacks(update, context):
    q = update.callback_query
    if not q or not str(q.data or "").startswith("mh_review_manual_paid"):
        return
    if not admin_roles.is_admin_id(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        raise ApplicationHandlerStop

    parts = str(q.data).split("|")
    action = parts[0]
    try:
        index = int(parts[1])
        lesson_id = int(parts[2])
    except Exception:
        await q.answer("Не удалось определить занятие", show_alert=True)
        raise ApplicationHandlerStop

    case = _manual_paid_case(context, index, lesson_id)
    if not case:
        await q.answer("Этот кейс уже исчез из разбора", show_alert=True)
        await review_v2._show(q, context, index)
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid":
        amount = int(case.get("price") or 0)
        await q.answer()
        await q.edit_message_text(
            "✅ ОТМЕТИТЬ ОПЛАТУ ВРУЧНУЮ\n\n"
            f"👤 {case['name']}"
            + (f" • {case.get('grade')} класс" if case.get("grade") is not None else "")
            + "\n"
            + f"💰 {amount:,} ₽\n".replace(",", " ")
            + f"📅 {review_v2._fmt_start(case.get('start_time'))}\n\n"
            + "Используйте это, если ученик оплатил переводом, наличными или другим способом и чек в бота не отправлял.\n\n"
            + "После подтверждения занятие станет оплаченным, напоминания об оплате прекратятся, а сумма попадёт в финансовую статистику.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "✅ Да, оплата получена",
                    callback_data=f"mh_review_manual_paid_confirm|{index}|{lesson_id}",
                )],
                [InlineKeyboardButton(
                    "⬅️ Назад к проблеме",
                    callback_data=f"mh_review_manual_paid_cancel|{index}|{lesson_id}",
                )],
            ]),
        )
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_cancel":
        await q.answer()
        await review_v2._show(q, context, index)
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_confirm":
        try:
            _, amount = _record_manual_lesson_payment(lesson_id)
            review_v2._mark_done(case["key"])
            await q.answer(f"✅ Оплата {amount:,} ₽ отмечена".replace(",", " "), show_alert=True)
            await review_v2._show(q, context, index)
        except Exception as exc:
            await q.answer(f"Не удалось отметить оплату: {exc}", show_alert=True)
        raise ApplicationHandlerStop


def _install_manual_paid_handler(application):
    if application is None:
        return
    if getattr(application, "_adelia_manual_paid_handler", False):
        return
    application.add_handler(
        CallbackQueryHandler(_manual_paid_callbacks, pattern=r"^mh_review_manual_paid"),
        group=-90,
    )
    application._adelia_manual_paid_handler = True


def debts(limit=40):
    """One debt card per student, only for the nearest unpaid confirmed lesson."""
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT
                u.id,
                u.name,
                u.grade,
                l.id AS lesson_id,
                l.user_id,
                l.program_id,
                l.study_goal,
                l.subject,
                l.duration_minutes,
                l.price,
                l.start_time AS since
            FROM users u
            JOIN lessons l
              ON l.id = (
                  SELECT l2.id
                  FROM lessons l2
                  WHERE l2.user_id=u.id
                    AND l2.lesson_status='CONFIRMED'
                    AND l2.cancelled_at IS NULL
                    AND l2.finished_at IS NULL
                    AND datetime(l2.start_time)>=datetime('now')
                  ORDER BY datetime(l2.start_time)
                  LIMIT 1
              )
            WHERE u.active=1
              AND l.payment_status='AWAITING_PAYMENT'
            ORDER BY datetime(l.start_time)
            LIMIT ?
        """, (int(limit),)).fetchall()

        result = []
        for row in rows:
            result.append({
                "id": int(row["id"]),
                "name": row["name"],
                "grade": int(row["grade"]) if row["grade"] is not None else None,
                "cnt": 1,
                "amount": _effective_price_for_lesson_row(row),
                "since": row["since"],
            })
        return result
    finally:
        c.close()


def weekly_payment_snapshot():
    """Current actionable payment cases using effective individual rates."""
    cases = [c for c in review_v2.review_cases(include_done=True) if c["kind"] == "PAYMENT_NEXT"]
    return {
        "count": len(cases),
        "amount": sum(int(c.get("price") or 0) for c in cases),
    }


def install(application=None):
    _patch_review_grade()
    _install_primary_review_route(application)
    _install_manual_paid_handler(application)

    try:
        from handlers import musthave_admin
        musthave_admin._debts = debts
    except Exception as exc:
        print("ADELIA PRICING UX DEBTS PATCH ERROR:", repr(exc))

    runtime_patch_v2.debts = debts
