from __future__ import annotations

import asyncio

import database
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationHandlerStop,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from core import admin_roles
from handlers import review_v2, runtime_patch_v2


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
                    "✅ Отметить оплату",
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
    q = update.callback_query
    if not q:
        return
    await q.answer()
    context.user_data["mh_review_started_at"] = review_v2._now().isoformat(timespec="seconds")
    context.user_data["mh_review_entry"] = str(q.data or "ux_review_start")
    await review_v2._show(q, context, 0)


def _install_primary_review_route(application):
    if application is None or getattr(application, "_adelia_primary_review_route", False):
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


def _next_unpaid_lessons(user_id, limit):
    c = database.connect()
    try:
        return c.execute(
            """
            SELECT *
            FROM lessons
            WHERE user_id=?
              AND lesson_status='CONFIRMED'
              AND payment_status='AWAITING_PAYMENT'
              AND cancelled_at IS NULL
              AND finished_at IS NULL
              AND datetime(start_time)>=datetime('now')
            ORDER BY datetime(start_time)
            LIMIT ?
            """,
            (int(user_id), int(limit)),
        ).fetchall()
    finally:
        c.close()


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


def _subject_name(code):
    return {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}.get(str(code or "").upper(), str(code or "Занятие"))


def _fmt_lesson_line(lesson, amount):
    raw = str(lesson["start_time"] or "")
    try:
        dt = review_v2.datetime.fromisoformat(raw)
        when = dt.strftime("%d.%m в %H:%M")
    except Exception:
        when = raw.replace("T", " ")[:16]
    return f"• {when} — {_subject_name(lesson['subject'])} — {int(amount):,} ₽".replace(",", " ")


def _vk_external_id(user_id):
    try:
        from vk_adapter import schema
        schema.initialize()
        c = database.connect()
        try:
            row = c.execute(
                """
                SELECT external_id
                FROM channel_identities
                WHERE user_id=? AND channel='VK' AND enabled=1
                LIMIT 1
                """,
                (int(user_id),),
            ).fetchone()
            return int(row["external_id"]) if row else None
        finally:
            c.close()
    except Exception:
        return None


async def _notify_payment_received(context, user_id, paid_rows):
    if not paid_rows:
        return
    user = database.get_user(int(user_id))
    if user is None:
        return

    total = sum(int(amount) for _, amount in paid_rows)
    lines = ["✅ ОПЛАТА ПОЛУЧЕНА", "", "Оплачены занятия:"]
    for lesson, amount in paid_rows:
        lines.append(_fmt_lesson_line(lesson, amount))
    lines += ["", f"Итого: {total:,} ₽".replace(",", " "), "", "💜 Всё готово, занятия подтверждены."]
    text = "\n".join(lines)

    tg_id = user["telegram_id"] if "telegram_id" in user.keys() else None
    if tg_id:
        try:
            await context.bot.send_message(chat_id=int(tg_id), text=text)
        except Exception as exc:
            print("MANUAL PAYMENT TELEGRAM NOTIFY ERROR:", user_id, repr(exc))

    vk_id = _vk_external_id(user_id)
    if vk_id:
        try:
            from vk_adapter import app as vk_app
            await asyncio.to_thread(vk_app.send, int(vk_id), text, True)
        except Exception as exc:
            print("MANUAL PAYMENT VK NOTIFY ERROR:", user_id, repr(exc))


async def _recolor_paid_calendar_events(paid_rows):
    if database.in_test_mode():
        return
    try:
        import __main__ as runtime
        service = await asyncio.to_thread(runtime.get_calendar_service)
        calendar_id = getattr(runtime, "CALENDAR_ID", "primary")
    except Exception as exc:
        print("MANUAL PAYMENT CALENDAR SERVICE ERROR:", repr(exc))
        return

    for lesson, _ in paid_rows:
        event_id = lesson["google_event_id"] if "google_event_id" in lesson.keys() else None
        if not event_id:
            continue
        try:
            await asyncio.to_thread(
                lambda eid=str(event_id): service.events().patch(
                    calendarId=calendar_id,
                    eventId=eid,
                    body={"colorId": "10"},
                ).execute()
            )
        except Exception as exc:
            print("MANUAL PAYMENT CALENDAR COLOR ERROR:", lesson["id"], repr(exc))


def _payment_count_keyboard(index, lesson_id, available):
    rows = []
    quick = [n for n in (1, 2, 3) if n <= available]
    if quick:
        rows.append([
            InlineKeyboardButton(
                f"✅ {n} занятие" if n == 1 else f"✅ {n} занятия",
                callback_data=f"mh_review_manual_paid_pick|{index}|{lesson_id}|{n}",
            )
            for n in quick
        ])
    rows.append([
        InlineKeyboardButton(
            "✏️ Указать количество",
            callback_data=f"mh_review_manual_paid_custom|{index}|{lesson_id}",
        )
    ])
    rows.append([
        InlineKeyboardButton(
            "⬅️ Назад к проблеме",
            callback_data=f"mh_review_manual_paid_cancel|{index}|{lesson_id}",
        )
    ])
    return InlineKeyboardMarkup(rows)


async def _show_payment_preview(q, context, index, lesson_id, count):
    case = _manual_paid_case(context, index, lesson_id)
    if not case:
        await q.answer("Этот кейс уже исчез из разбора", show_alert=True)
        await review_v2._show(q, context, index)
        return
    rows = list(_next_unpaid_lessons(case["user_id"], count))
    if not rows:
        await q.answer("Неоплаченных занятий уже нет", show_alert=True)
        await review_v2._show(q, context, index)
        return
    if len(rows) < count:
        count = len(rows)

    priced = [(row, _effective_price_for_lesson_row(row)) for row in rows]
    total = sum(amount for _, amount in priced)
    text = [
        "✅ ПОДТВЕРЖДЕНИЕ ОПЛАТЫ",
        "",
        f"👤 {case['name']}" + (f" • {case.get('grade')} класс" if case.get("grade") is not None else ""),
        "",
        "Будут отмечены оплачены:",
    ]
    text.extend(_fmt_lesson_line(row, amount) for row, amount in priced)
    text += ["", f"Итого получено: {total:,} ₽".replace(",", " ")]

    await q.edit_message_text(
        "\n".join(text),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ Подтвердить",
                callback_data=f"mh_review_manual_paid_confirm|{index}|{lesson_id}|{count}",
            )],
            [InlineKeyboardButton(
                "⬅️ Изменить количество",
                callback_data=f"mh_review_manual_paid|{index}|{lesson_id}",
            )],
        ]),
    )


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
        available = len(_next_unpaid_lessons(case["user_id"], 50))
        await q.answer()
        await q.edit_message_text(
            "✅ ОТМЕТИТЬ ОПЛАТУ ВРУЧНУЮ\n\n"
            f"👤 {case['name']}"
            + (f" • {case.get('grade')} класс" if case.get("grade") is not None else "")
            + f"\n\nНеоплаченных будущих занятий: {available}.\n"
            + "Сколько ближайших занятий оплачено?",
            reply_markup=_payment_count_keyboard(index, lesson_id, available),
        )
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_cancel":
        context.user_data.pop("manual_paid_wait_count", None)
        await q.answer()
        await review_v2._show(q, context, index)
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_custom":
        context.user_data["manual_paid_wait_count"] = {
            "index": index,
            "lesson_id": lesson_id,
            "user_id": int(case["user_id"]),
        }
        await q.answer()
        await q.edit_message_text(
            "✏️ УКАЖИТЕ КОЛИЧЕСТВО\n\n"
            "Отправьте одним сообщением число, например: 2\n\n"
            "Я отмечу оплаченными именно столько ближайших неоплаченных занятий.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "⬅️ Отмена",
                    callback_data=f"mh_review_manual_paid|{index}|{lesson_id}",
                )
            ]]),
        )
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_pick":
        try:
            count = int(parts[3])
        except Exception:
            count = 1
        context.user_data.pop("manual_paid_wait_count", None)
        await q.answer()
        await _show_payment_preview(q, context, index, lesson_id, count)
        raise ApplicationHandlerStop

    if action == "mh_review_manual_paid_confirm":
        try:
            count = max(1, int(parts[3]))
            rows = list(_next_unpaid_lessons(case["user_id"], count))
            if not rows:
                raise ValueError("Неоплаченных занятий уже нет")
            paid_rows = []
            for row in rows:
                _, amount = _record_manual_lesson_payment(int(row["id"]))
                refreshed = database.get_lesson(int(row["id"])) or row
                paid_rows.append((refreshed, int(amount)))
            review_v2._mark_done(case["key"])
            await _notify_payment_received(context, case["user_id"], paid_rows)
            await _recolor_paid_calendar_events(paid_rows)
            total = sum(amount for _, amount in paid_rows)
            await q.answer(
                f"✅ Оплачено занятий: {len(paid_rows)} • {total:,} ₽".replace(",", " "),
                show_alert=True,
            )
            await review_v2._show(q, context, index)
        except Exception as exc:
            await q.answer(f"Не удалось отметить оплату: {exc}", show_alert=True)
        raise ApplicationHandlerStop


async def _manual_paid_count_text(update, context):
    state = context.user_data.get("manual_paid_wait_count")
    if not state:
        return
    if not admin_roles.is_admin_id(update.effective_user.id):
        return
    raw = str(update.message.text or "").strip()
    try:
        count = int(raw)
    except Exception:
        await update.message.reply_text("Напишите только количество занятий числом, например 2.")
        raise ApplicationHandlerStop
    if count < 1 or count > 50:
        await update.message.reply_text("Количество должно быть от 1 до 50.")
        raise ApplicationHandlerStop

    available = len(_next_unpaid_lessons(state["user_id"], 50))
    if count > available:
        await update.message.reply_text(f"Сейчас неоплаченных будущих занятий только {available}.")
        raise ApplicationHandlerStop

    context.user_data.pop("manual_paid_wait_count", None)
    case = _manual_paid_case(context, state["index"], state["lesson_id"])
    if not case:
        await update.message.reply_text("Этот кейс уже исчез из разбора.")
        raise ApplicationHandlerStop

    rows = list(_next_unpaid_lessons(case["user_id"], count))
    priced = [(row, _effective_price_for_lesson_row(row)) for row in rows]
    total = sum(amount for _, amount in priced)
    text = [
        "✅ ПОДТВЕРЖДЕНИЕ ОПЛАТЫ",
        "",
        f"👤 {case['name']}",
        "",
        "Будут отмечены оплачены:",
    ]
    text.extend(_fmt_lesson_line(row, amount) for row, amount in priced)
    text += ["", f"Итого получено: {total:,} ₽".replace(",", " ")]
    await update.message.reply_text(
        "\n".join(text),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "✅ Подтвердить",
                callback_data=f"mh_review_manual_paid_confirm|{state['index']}|{state['lesson_id']}|{count}",
            )
        ]]),
    )
    raise ApplicationHandlerStop


def _install_manual_paid_handler(application):
    if application is None or getattr(application, "_adelia_manual_paid_handler", False):
        return
    application.add_handler(
        CallbackQueryHandler(_manual_paid_callbacks, pattern=r"^mh_review_manual_paid"),
        group=-90,
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, _manual_paid_count_text),
        group=-90,
    )
    application._adelia_manual_paid_handler = True


def debts(limit=40):
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
