from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden
from telegram.ext import CallbackQueryHandler

import database
from automation import schedule_tools
from core import admin_roles


def _tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Samara")


def _now():
    return datetime.now(_tz())


def _done_key():
    return f"review_v2_done_{_now().date().isoformat()}"


def _done_cases():
    raw = database.get_setting(_done_key(), "") or ""
    return {x for x in str(raw).split(",") if x}


def _mark_done(case_key):
    done = _done_cases()
    done.add(str(case_key))
    database.set_setting(_done_key(), ",".join(sorted(done)))


def _defer_key(case_key):
    safe = str(case_key).replace(":", "_").replace("|", "_")
    return f"review_v2_defer_{safe}"


def _deferred_until(case_key):
    value = database.get_setting(_defer_key(case_key), "") or ""
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _defer(case_key, date_text):
    target = datetime.fromisoformat(str(date_text)).date()
    database.set_setting(_defer_key(case_key), target.isoformat())


def _is_deferred(case_key):
    target = _deferred_until(case_key)
    return bool(target and target > _now().date())


def _lesson_price(row):
    """Return the current effective lesson price, not a stale stored snapshot."""
    stored = int(row["price"] or 0)
    try:
        duration = int(row["duration_minutes"] or 60)
        program_id = row["program_id"]
        if program_id:
            hourly = int(database.get_program_rate_info(int(program_id))["effective_rate"])
        else:
            hourly = int(database.get_student_rate_info(
                int(row["user_id"]),
                row["study_goal"],
                row["subject"],
            )["effective_rate"])
        return int(database.calculate_lesson_price(hourly, duration))
    except Exception:
        return stored


def _payment_cases():
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT
                u.id AS user_id,
                u.name,
                u.telegram_id,
                l.id AS lesson_id,
                l.start_time,
                l.price,
                l.duration_minutes,
                l.program_id,
                l.study_goal,
                l.subject,
                l.regular_schedule_id
            FROM users u
            JOIN lessons l
              ON l.id = (
                  SELECT l2.id
                  FROM lessons l2
                  WHERE l2.user_id=u.id
                    AND l2.lesson_status='CONFIRMED'
                    AND l2.cancelled_at IS NULL
                    AND datetime(l2.start_time)>=datetime('now')
                  ORDER BY datetime(l2.start_time)
                  LIMIT 1
              )
            WHERE u.active=1
              AND l.payment_status='AWAITING_PAYMENT'
            ORDER BY datetime(l.start_time)
        """).fetchall()

        result = []
        for r in rows:
            remaining = 0
            if r["regular_schedule_id"]:
                try:
                    start_date = datetime.fromisoformat(str(r["start_time"])).date()
                    schedule_dates = database.get_regular_schedule_dates(int(r["regular_schedule_id"]))
                    remaining = sum(1 for day in schedule_dates if day >= start_date)
                except Exception:
                    remaining = c.execute("""
                        SELECT COUNT(*)
                        FROM lessons
                        WHERE regular_schedule_id=?
                          AND lesson_status='CONFIRMED'
                          AND cancelled_at IS NULL
                          AND datetime(start_time)>=datetime(?)
                    """, (r["regular_schedule_id"], r["start_time"])).fetchone()[0]

            result.append({
                "key": f"pay:{int(r['lesson_id'])}",
                "kind": "PAYMENT_NEXT",
                "user_id": int(r["user_id"]),
                "name": r["name"],
                "telegram_id": int(r["telegram_id"]) if r["telegram_id"] else None,
                "lesson_id": int(r["lesson_id"]),
                "start_time": r["start_time"],
                "price": _lesson_price(r),
                "stored_price": int(r["price"] or 0),
                "remaining": int(remaining or 0),
            })
        return result
    finally:
        c.close()


def _no_next_cases():
    today = _now().date().isoformat()
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT id,name,telegram_id,COALESCE(trial_used,0) trial_used
            FROM users u
            WHERE u.active=1
              AND NOT EXISTS (
                  SELECT 1
                  FROM lessons l
                  WHERE l.user_id=u.id
                    AND l.cancelled_at IS NULL
                    AND l.finished_at IS NULL
                    AND l.lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
                    AND datetime(l.start_time)>=datetime('now')
              )
            ORDER BY name COLLATE NOCASE
        """).fetchall()
    finally:
        c.close()

    result = []
    for r in rows:
        uid = int(r["id"])
        if schedule_tools.is_paused(uid, today):
            continue
        result.append({
            "key": f"next:{uid}",
            "kind": "NO_NEXT_LESSON",
            "user_id": uid,
            "name": r["name"],
            "telegram_id": int(r["telegram_id"]) if r["telegram_id"] else None,
            "trial_available": not bool(int(r["trial_used"] or 0)),
        })
    return result



def _homework_cases():
    c = database.connect()

    try:
        rows = c.execute(
            """
            SELECT
                l.id AS lesson_id,
                l.user_id,
                l.program_id,
                l.start_time,
                l.subject,
                u.name,
                u.telegram_id
            FROM lessons l
            JOIN users u
              ON u.id=l.user_id
            WHERE (
                l.lesson_status IN (
                    'COMPLETED',
                    'FINISHED'
                )
                OR l.finished_at IS NOT NULL
            )
              AND COALESCE(
                    l.homework_required,
                    0
                  )=1
              AND COALESCE(
                    l.homework_assigned,
                    0
                  )=0
              AND COALESCE(
                    l.homework_skipped,
                    0
                  )=0
              AND NOT EXISTS (
                  SELECT 1
                  FROM homework h
                  WHERE h.lesson_id=l.id
              )
            ORDER BY
                datetime(
                    COALESCE(
                        l.finished_at,
                        l.start_time
                    )
                ) DESC
            """
        ).fetchall()

        return [
            {
                "key": (
                    f"homework:"
                    f"{int(r['lesson_id'])}"
                ),
                "kind": "HOMEWORK_MISSING",
                "user_id": int(
                    r["user_id"]
                ),
                "name": r["name"],
                "telegram_id": (
                    int(r["telegram_id"])
                    if r["telegram_id"]
                    else None
                ),
                "lesson_id": int(
                    r["lesson_id"]
                ),
                "program_id": r[
                    "program_id"
                ],
                "start_time": r[
                    "start_time"
                ],
                "subject": r[
                    "subject"
                ],
            }
            for r in rows
        ]

    finally:
        c.close()

def review_cases(include_done=False):
    cases = (
        _payment_cases()
        + _homework_cases()
        + _no_next_cases()
    )
    if include_done:
        return cases
    done = _done_cases()
    return [
        x for x in cases
        if x["key"] not in done and not _is_deferred(x["key"])
    ]


def _fmt_start(value):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz())
        else:
            dt = dt.astimezone(_tz())
        return dt.strftime("%d.%m в %H:%M")
    except Exception:
        return str(value)


def _case_text(case, index, total):
    if case["kind"] == "HOMEWORK_MISSING":
        subject = {
            "PHYSICS": "Физика",
            "CHEMISTRY": "Химия",
        }.get(
            str(
                case.get("subject")
                or ""
            ).upper(),
            str(
                case.get("subject")
                or "Занятие"
            ),
        )

        return (
            "💜 АДЕЛИЯ • РАЗБОР ДНЯ\n\n"
            f"Шаг {index + 1} из {total}\n\n"
            "📝 НЕ ЗАДАНО ДЗ\n"
            f"👤 {case['name']}\n"
            f"📚 {subject}\n"
            f"📅 Урок: "
            f"{_fmt_start(case['start_time'])}\n\n"
            "ДЗ было оставлено как нужное, "
            "но ещё не создано.\n\n"
            "Можно сразу перейти к созданию "
            "или осознанно выбрать «Без ДЗ»."
        )

    if case["kind"] == "PAYMENT_NEXT":
        lines = [
            "💜 АДЕЛИЯ • РАЗБОР ДНЯ",
            "",
            f"Шаг {index + 1} из {total}",
            "",
            "💳 ОПЛАТА",
            f"👤 {case['name']}",
            f"📅 Следующее занятие: {_fmt_start(case['start_time'])}",
            f"💰 Стоимость занятия: {case['price']:,} ₽".replace(",", " "),
        ]
        if case.get("remaining"):
            lines.append(f"🔁 По постоянному расписанию до срока осталось: {case['remaining']} занятий")
        lines += [
            "",
            "Проверяем только ближайшее занятие. Остальная серия не создаёт отдельные ежедневные проблемы.",
        ]
        return "\n".join(lines)

    label = "🎁 ПРОБНОЕ / ЗАПИСЬ" if case.get("trial_available") else "📅 НЕТ СЛЕДУЮЩЕГО ЗАНЯТИЯ"
    action = (
        "У ученика ещё не использовано пробное занятие — можно предложить начать с него."
        if case.get("trial_available")
        else "В расписании нет будущего занятия. Можно отправить предложение записаться."
    )
    return (
        "💜 АДЕЛИЯ • РАЗБОР ДНЯ\n\n"
        f"Шаг {index + 1} из {total}\n\n"
        f"{label}\n👤 {case['name']}\n\n{action}"
    )


def _case_keyboard(case, index):
    rows = []

    if case["kind"] == "HOMEWORK_MISSING":
        lesson_id = int(
            case["lesson_id"]
        )

        rows.append([
            InlineKeyboardButton(
                "📝 Задать ДЗ",
                callback_data=(
                    f"hw_task_start|"
                    f"{lesson_id}"
                ),
            )
        ])

        rows.append([
            InlineKeyboardButton(
                "⏭ Без ДЗ",
                callback_data=(
                    f"admin_homework_skip|"
                    f"{lesson_id}"
                ),
            )
        ])

        rows.append([
            InlineKeyboardButton(
                "👤 Открыть ученика",
                callback_data=(
                    f"student_view|"
                    f"{case['user_id']}"
                ),
            )
        ])

        rows.append([
            InlineKeyboardButton(
                "📅 Отложить до…",
                callback_data=(
                    f"mh_review_defer_menu|"
                    f"{index}"
                ),
            ),
            InlineKeyboardButton(
                "➡️ Следующий",
                callback_data=(
                    f"mh_review_next|"
                    f"{index}"
                ),
            ),
        ])

        rows.append([
            InlineKeyboardButton(
                "✕ Закончить",
                callback_data="mh_review_finish",
            ),
            InlineKeyboardButton(
                "🏠 Главная",
                callback_data="global_home",
            ),
        ])

        return InlineKeyboardMarkup(
            rows
        )

    if case["kind"] == "PAYMENT_NEXT":
        rows.append([
            InlineKeyboardButton("💳 Предложить оплатить следующее", callback_data=f"mh_review_send_next|{index}")
        ])
        if int(case.get("remaining") or 0) > 1:
            rows.append([
                InlineKeyboardButton("🎟 Предложить абонемент на серию", callback_data=f"mh_review_send_pack|{index}")
            ])
    else:
        rows.append([
            InlineKeyboardButton(
                "🎁 Предложить пробное" if case.get("trial_available") else "📅 Предложить записаться",
                callback_data=f"mh_review_send_book|{index}",
            )
        ])

    rows.append([
        InlineKeyboardButton("👤 Открыть ученика", callback_data=f"student_view|{case['user_id']}")
    ])
    rows.append([
        InlineKeyboardButton("✅ Решено", callback_data=f"mh_review_done|{index}"),
        InlineKeyboardButton("📅 Отложить до…", callback_data=f"mh_review_defer_menu|{index}"),
    ])
    rows.append([
        InlineKeyboardButton("➡️ Следующий", callback_data=f"mh_review_next|{index}"),
        InlineKeyboardButton("✕ Закончить", callback_data="mh_review_finish"),
    ])
    rows.append([InlineKeyboardButton("🏠 Главная", callback_data="global_home")])
    return InlineKeyboardMarkup(rows)


def _defer_keyboard(index):
    today = _now().date()
    rows = []
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        label = "Завтра" if offset == 1 else day.strftime("%d.%m")
        rows.append([
            InlineKeyboardButton(
                f"📅 {label}",
                callback_data=f"mh_review_defer|{index}|{day.isoformat()}",
            )
        ])
    rows.append([
        InlineKeyboardButton("⬅️ Назад", callback_data=f"mh_review_back|{index}")
    ])
    return InlineKeyboardMarkup(rows)


async def _show(q, context, index=0):
    cases = review_cases()
    context.user_data["mh_review_cases"] = cases

    if not cases:
        await q.edit_message_text(
            "💜 АДЕЛИЯ • РАЗБОР ДНЯ\n\n🟢 Сейчас нет случаев, которые требуют действия.\n\n"
            "Оплаченные ближайшие занятия не создают шум, отложенные задачи вернутся в выбранный день, а ученики на паузе не попадают в список.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Главная", callback_data="global_home")]]),
        )
        return

    index = max(0, min(int(index), len(cases) - 1))
    context.user_data["mh_review_index"] = index
    case = cases[index]
    await q.edit_message_text(
        _case_text(case, index, len(cases)),
        reply_markup=_case_keyboard(case, index),
    )


def _cached_case(context, index):
    cases = context.user_data.get("mh_review_cases") or review_cases()
    if not cases:
        return None
    index = max(0, min(int(index), len(cases) - 1))
    return cases[index]


async def _send_message(context, case, text, keyboard):
    tid = case.get("telegram_id")
    if not tid:
        return "ERROR", "У ученика нет Telegram ID."
    try:
        await context.bot.send_message(int(tid), text, reply_markup=keyboard)
        return "OK", "Отправлено"
    except Forbidden as exc:
        if "blocked by the user" in str(exc).lower():
            database.set_user_active(case["user_id"], False)
            return "BLOCKED", "Ученик заблокировал бота — убрала его из активных и перехожу дальше."
        return "ERROR", str(exc)
    except Exception as exc:
        return "ERROR", str(exc)


async def _after_send(q, context, case, index, status, detail):
    await q.answer(detail, show_alert=True)
    if status in ("OK", "BLOCKED"):
        _mark_done(case["key"])
        await _show(q, context, index)



async def _close_day(q, context):
    from handlers import briefs_v2

    data = briefs_v2.evening_brief_data()

    text = briefs_v2.evening_brief_text(
        data
    )

    review_count = len(
        review_cases()
    )

    rows = []

    for gap in data.get(
        "hw_gaps",
        [],
    )[:5]:
        rows.append([
            InlineKeyboardButton(
                (
                    "📝 Задать ДЗ — "
                    f"{gap['name']}"
                )[:60],
                callback_data=(
                    f"hw_task_start|"
                    f"{gap['lesson_id']}"
                ),
            )
        ])

    if data["attention"]:
        rows.append([
            InlineKeyboardButton(
                (
                    "🧹 Разобрать хвосты"
                    f" • {data['attention']}"
                ),
                callback_data="mh_review_start",
            )
        ])

    if review_count:
        rows.append([
            InlineKeyboardButton(
                (
                    "💳 Оплаты и записи"
                    f" • {review_count}"
                ),
                callback_data="mh_review_start",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            "🔄 Обновить",
            callback_data="mh_day_close",
        ),
        InlineKeyboardButton(
            "🏠 Главная",
            callback_data="global_home",
        ),
    ])

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            rows
        ),
    )

async def callbacks(update, context):
    q = update.callback_query
    if not q or not q.data.startswith("mh_review"):
        return
    if not admin_roles.is_admin_id(q.from_user.id):
        await q.answer("Нет доступа", show_alert=True)
        return

    data = q.data

    if data == "mh_day_close":
        await q.answer()

        await _close_day(
            q,
            context,
        )

        return

    if data == "mh_review_start":
        await q.answer()
        context.user_data["mh_review_started_at"] = _now().isoformat(timespec="seconds")
        await _show(q, context, 0)
        return

    if data == "mh_review_finish":
        await q.answer()
        await q.edit_message_text(
            "💜 Разбор завершён.\n\nНерешённые случаи останутся в очереди, а отложенные вернутся в выбранную дату.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ Продолжить разбор", callback_data="mh_review_start")],
                [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
            ]),
        )
        return

    if data.startswith("mh_review_defer|"):
        parts = data.split("|", 2)
        if len(parts) == 3:
            index = int(parts[1])
            case = _cached_case(context, index)
            if case:
                _defer(case["key"], parts[2])
                target = datetime.fromisoformat(parts[2]).strftime("%d.%m")
                await q.answer(f"Отложено до {target}")
                await _show(q, context, index)
                return

    try:
        index = int(data.split("|")[1]) if "|" in data else int(context.user_data.get("mh_review_index", 0) or 0)
    except Exception:
        index = int(context.user_data.get("mh_review_index", 0) or 0)

    case = _cached_case(context, index)
    if not case:
        await q.answer()
        await _show(q, context, 0)
        return

    if data.startswith("mh_review_defer_menu|"):
        await q.answer()
        await q.edit_message_text(
            f"📅 ОТЛОЖИТЬ ЗАДАЧУ\n\n👤 {case['name']}\n\nВ какой день вернуть этот пункт в разбор?",
            reply_markup=_defer_keyboard(index),
        )
        return

    if data.startswith("mh_review_back|"):
        await q.answer()
        await q.edit_message_text(
            _case_text(case, index, len(context.user_data.get("mh_review_cases") or [case])),
            reply_markup=_case_keyboard(case, index),
        )
        return

    if data.startswith("mh_review_done|"):
        await q.answer("Отметила решённым на сегодня")
        _mark_done(case["key"])
        await _show(q, context, index)
        return

    if data.startswith("mh_review_next|"):
        await q.answer()
        await _show(q, context, index + 1)
        return

    if data.startswith("mh_review_send_next|"):
        lesson_id = int(case["lesson_id"])
        text = (
            f"💜 {case['name']}, привет!\n\n"
            f"Следующее занятие — {_fmt_start(case['start_time'])}.\n"
            + f"Стоимость: {case['price']:,} ₽.\n\n".replace(",", " ")
            + "Если удобно, оплатить можно прямо здесь 👇"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Оплатить следующее занятие", callback_data=f"payment_lesson|{lesson_id}")],
            [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
        ])
        status, detail = await _send_message(context, case, text, keyboard)
        await _after_send(q, context, case, index, status, detail)
        return

    if data.startswith("mh_review_send_pack|"):
        text = (
            f"💜 {case['name']}, привет!\n\n"
            "У тебя впереди серия занятий. Если удобнее закрыть оплату заранее, можно выбрать абонемент — бот покажет доступные варианты и скидку 👇"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎟 Выбрать абонемент", callback_data="payment_subscription")],
            [InlineKeyboardButton("💳 Оплатить только следующее", callback_data=f"payment_lesson|{case['lesson_id']}")],
            [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
        ])
        status, detail = await _send_message(context, case, text, keyboard)
        await _after_send(q, context, case, index, status, detail)
        return

    if data.startswith("mh_review_send_book|"):
        if case.get("trial_available"):
            text = (
                f"💜 {case['name']}, привет!\n\n"
                "У тебя ещё доступно пробное занятие. Если хочешь, выбери удобную дату и время — я помогу оформить запись 👇"
            )
            label = "🎁 Записаться на пробное"
        else:
            text = (
                f"💜 {case['name']}, привет!\n\n"
                "Я пока не вижу следующего занятия в расписании. Можешь заранее выбрать удобную дату и время 👇"
            )
            label = "📅 Записаться"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data="booking")],
            [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
        ])
        status, detail = await _send_message(context, case, text, keyboard)
        await _after_send(q, context, case, index, status, detail)
        return

    await q.answer()


def install(application):
    application.add_handler(
        CallbackQueryHandler(callbacks, pattern=r"^mh_review"),
        group=-10,
    )

    try:
        import admin
        original_menu = admin.admin_menu

        def menu_v2():
            markup = original_menu()
            rows = [list(row) for row in markup.inline_keyboard]
            count = len(review_cases())
            hour = _now().hour
            if hour < 12:
                label = "🌅 Подготовить день"
                callback = "mh_review_start"

            elif hour >= 18:
                label = "🌙 Закрыть день"
                callback = "mh_day_close"

            else:
                label = "▶️ Разобрать всё"
                callback = "mh_review_start"

            if (
                count
                and callback == "mh_review_start"
            ):
                label += f" • {count}"

            if rows:
                rows[0] = [
                    InlineKeyboardButton(
                        label,
                        callback_data=callback,
                    )
                ]
            return InlineKeyboardMarkup(rows)

        admin.admin_menu = menu_v2
    except Exception as exc:
        print("REVIEW V2 MENU INSTALL ERROR:", repr(exc))
