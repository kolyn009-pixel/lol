from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from core import admin_roles, post_lesson
from core.lesson_time import schedule_datetime, actual_datetime


def _tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Samara")


def _admins():
    try:
        return [int(a["telegram_id"]) for a in admin_roles.list_admins() if a["active"]]
    except Exception:
        return []


def _fmt_time(raw):
    try:
        return schedule_datetime(raw).strftime("%H:%M")
    except Exception:
        return "—"


def _fmt_actual(raw):
    try:
        return actual_datetime(raw).strftime("%H:%M") if raw else "—"
    except Exception:
        return "—"


def _today_lessons(day):
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT l.*,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE date(l.start_time)=?
              AND l.lesson_status NOT IN ('CANCELLED','REJECTED')
            ORDER BY datetime(l.start_time),l.id
            """,
            (day,),
        ).fetchall())
    finally:
        c.close()


def _waiting_receipts():
    c = database.connect()
    try:
        row = c.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM receipts r JOIN payments p ON p.id=r.payment_id
            WHERE r.status='WAITING' AND p.status='RECEIPT_SENT'
            """
        ).fetchone()
        return int(row["cnt"] or 0) if row else 0
    except Exception:
        return 0
    finally:
        c.close()


def _open_messages():
    try:
        from crm_plus import service
        return int(service.today_dashboard()["open_messages"] or 0)
    except Exception:
        return 0


def _unfinished_reviews(limit=20):
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT l.id,l.user_id,l.finished_at,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
              AND COALESCE(l.post_lesson_reviewed,0)=0
            ORDER BY datetime(l.finished_at) DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall())
    except Exception:
        return []
    finally:
        c.close()


def _homework_gaps(limit=20):
    """
    Canonical homework gaps.

    lessons flags are the source of truth.
    No separate interpretation of
    post_lesson_review_sync is required here.
    """

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
                u.name
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
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()

        out = []

        for row in rows:
            lid = int(
                row["lesson_id"]
            )

            try:
                summary = (
                    post_lesson
                    .review_summary(lid)
                )

                topics = (
                    summary.get(
                        "topics"
                    )
                    or []
                )

            except Exception:
                topics = []

            out.append({
                "lesson_id": lid,
                "user_id": int(
                    row["user_id"]
                ),
                "program_id": row[
                    "program_id"
                ],
                "name": row["name"],
                "subject": row[
                    "subject"
                ],
                "status": "MISSING",
                "topics": topics[:3],
            })

        return out

    except Exception as exc:
        print(
            "BRIEF HOMEWORK GAPS:",
            repr(exc),
        )

        return []

    finally:
        c.close()


def _today_payment_attention(lessons):
    result = []
    for lesson in lessons:
        if bool(lesson["is_trial"]):
            continue
        p = str(lesson["payment_status"] or "").upper()
        if p in {"AWAITING_PAYMENT", "UNPAID"}:
            result.append(lesson)
    return result


def _queue_markup(
    morning=False,
    hw_gaps=None,
):
    first = (
        "🌅 Разобрать утро"
        if morning
        else "🌙 Закрыть хвосты дня"
    )

    rows = []

    for gap in (
        hw_gaps or []
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

    rows.extend([
        [
            InlineKeyboardButton(
                first,
                callback_data="ux_review_start",
            )
        ],
        [
            InlineKeyboardButton(
                "🧾 Чеки",
                callback_data="receipt_center",
            ),
            InlineKeyboardButton(
                "💳 Оплаты",
                callback_data="mh_debts",
            ),
        ],
        [
            InlineKeyboardButton(
                "📅 Сегодня",
                callback_data="crm_today",
            ),
            InlineKeyboardButton(
                "⚠️ Внимание",
                callback_data="mh_attention",
            ),
        ],
        [
            InlineKeyboardButton(
                "🏠 Главная",
                callback_data="global_home",
            )
        ],
    ])

    return InlineKeyboardMarkup(
        rows
    )


async def morning_brief_job(context):
    now = datetime.now(_tz())
    day = now.date().isoformat()
    lessons = _today_lessons(day)
    receipts = _waiting_receipts()
    messages = _open_messages()
    reviews = _unfinished_reviews()
    hw_gaps = _homework_gaps()
    unpaid = _today_payment_attention(lessons)

    lines = [
        "💜 АДЕЛИЯ • ДОБРОЕ УТРО",
        "",
        "Я собрала день по новой системе — только то, что реально требует внимания.",
        "",
        f"📅 Занятий сегодня: {len(lessons)}",
    ]
    for lesson in lessons[:8]:
        trial = "🧪 " if lesson["is_trial"] else ""
        pay = str(lesson["payment_status"] or "").upper()
        pay_icon = "💳" if pay in {"PAID", "RESERVED_BALANCE", "FREE"} else ("🔴" if pay in {"AWAITING_PAYMENT", "UNPAID"} and not lesson["is_trial"] else "")
        lines.append(f"• {_fmt_time(lesson['start_time'])} · {trial}{lesson['name']} {pay_icon}".rstrip())

    lines += [
        "",
        f"🧾 Чеков ждут проверки: {receipts}",
        f"🔴 Сегодня без оплаты: {len(unpaid)}",
        f"💬 Сообщений ждут ответа: {messages}",
        f"🧠 Незавершённых опросов: {len(reviews)}",
        f"📝 После уроков нет ДЗ: {len(hw_gaps)}",
    ]

    if hw_gaps:
        lines += ["", "📝 ДЗ, которые надо довести:"]
        for item in hw_gaps[:5]:
            topic_text = ", ".join(item["topics"]) if item["topics"] else "темы ещё не сохранены"
            lines.append(f"• {item['name']} — {topic_text}")

    if not any((lessons, receipts, unpaid, messages, reviews, hw_gaps)):
        lines += ["", "🟢 Всё спокойно. Хвостов нет."]

    for aid in _admins():
        try:
            await context.bot.send_message(aid, "\n".join(lines)[:3900], reply_markup=_queue_markup(True, hw_gaps))
            database.set_setting("morning_brief_last_ok", now.isoformat(timespec="minutes"))
            database.log_automation_delivery("morning_brief_v2", "OK", "ADMIN", aid)
        except Exception as exc:
            database.log_automation_delivery("morning_brief_v2", "ERROR", "ADMIN", aid, repr(exc))



def evening_brief_data():
    now = datetime.now(
        _tz()
    )

    day = now.date().isoformat()

    tomorrow = (
        now.date()
        + timedelta(days=1)
    ).isoformat()

    lessons = _today_lessons(
        day
    )

    tomorrow_lessons = _today_lessons(
        tomorrow
    )

    receipts = _waiting_receipts()
    messages = _open_messages()
    reviews = _unfinished_reviews()
    hw_gaps = _homework_gaps()

    done = [
        x for x in lessons
        if (
            str(
                x["lesson_status"]
                or ""
            ).upper()
            in {
                "COMPLETED",
                "FINISHED",
            }
            or x["finished_at"]
        )
    ]

    running = [
        x for x in lessons
        if (
            str(
                x["lesson_status"]
                or ""
            ).upper()
            == "IN_PROGRESS"
            and not x["finished_at"]
        )
    ]

    cancelled = [
        x for x in lessons
        if str(
            x["lesson_status"]
            or ""
        ).upper()
        in {
            "CANCELLED",
            "REJECTED",
        }
    ]

    unfinished = [
        x for x in lessons
        if (
            x not in done
            and x not in running
            and x not in cancelled
        )
    ]

    unpaid_tomorrow = (
        _today_payment_attention(
            tomorrow_lessons
        )
    )

    attention = (
        len(running)
        + len(unfinished)
        + len(reviews)
        + len(hw_gaps)
        + int(receipts or 0)
        + int(messages or 0)
        + len(unpaid_tomorrow)
    )

    return {
        "now": now,
        "lessons": lessons,
        "tomorrow_lessons": tomorrow_lessons,
        "done": done,
        "running": running,
        "unfinished": unfinished,
        "cancelled": cancelled,
        "reviews": reviews,
        "hw_gaps": hw_gaps,
        "receipts": receipts,
        "messages": messages,
        "unpaid_tomorrow": unpaid_tomorrow,
        "attention": attention,
    }


def evening_brief_text(data=None):
    data = (
        data
        or evening_brief_data()
    )

    lines = [
        "💜 АДЕЛИЯ • ИТОГ ДНЯ",
        "",
        "Закрываю день по фактическим данным.",
        "",
        "━━━━━━━━━━━━━━",
        "📚 СЕГОДНЯ",
        "",
        f"✅ Проведено: {len(data['done'])}",
    ]

    for lesson in data["done"][:8]:
        start = (
            _fmt_actual(
                lesson["started_at"]
            )
            if lesson["started_at"]
            else _fmt_time(
                lesson["start_time"]
            )
        )

        finish = (
            _fmt_actual(
                lesson["finished_at"]
            )
            if lesson["finished_at"]
            else "—"
        )

        lines.append(
            f"• {lesson['name']} · "
            f"{start}–{finish}"
        )

    lines += [
        f"🩷 Сейчас идут: {len(data['running'])}",
        f"⚠️ Не закрыты: {len(data['unfinished'])}",
        f"❌ Отменено: {len(data['cancelled'])}",
        "",
        "━━━━━━━━━━━━━━",
        "🧹 ХВОСТЫ",
        "",
        f"🧠 Опросы: {len(data['reviews'])}",
        f"📝 ДЗ: {len(data['hw_gaps'])}",
        f"🧾 Чеки: {data['receipts']}",
        f"💬 Сообщения: {data['messages']}",
        "",
        "━━━━━━━━━━━━━━",
        "🌅 ЗАВТРА",
        "",
        f"📅 Занятий: {len(data['tomorrow_lessons'])}",
        (
            "🟡 Без подтверждённой оплаты: "
            f"{len(data['unpaid_tomorrow'])}"
        ),
    ]

    for lesson in data[
        "tomorrow_lessons"
    ][:8]:
        pay = str(
            lesson["payment_status"]
            or ""
        ).upper()

        if lesson["is_trial"]:
            icon = "🧪"
        elif pay in {
            "PAID",
            "RESERVED_BALANCE",
            "FREE",
        }:
            icon = "🟣"
        else:
            icon = "🟡"

        lines.append(
            f"• {_fmt_time(lesson['start_time'])}"
            f" · {icon} {lesson['name']}"
        )

    if data["attention"]:
        lines += [
            "",
            (
                "⚠️ Осталось действий: "
                f"{data['attention']}"
            ),
        ]
    else:
        lines += [
            "",
            "🟢 День полностью закрыт.",
        ]

    return "\n".join(lines)[:3900]

async def evening_brief_job(context):
    data = evening_brief_data()

    text = evening_brief_text(
        data
    )

    for aid in _admins():
        try:
            await context.bot.send_message(
                aid,
                text,
                reply_markup=_queue_markup(
                    False,
                    data.get("hw_gaps", []),
                ),
            )

            database.set_setting(
                "evening_brief_last_ok",
                data["now"].isoformat(
                    timespec="minutes"
                ),
            )

            database.log_automation_delivery(
                "evening_brief_v2",
                "OK",
                "ADMIN",
                aid,
            )

        except Exception as exc:
            database.log_automation_delivery(
                "evening_brief_v2",
                "ERROR",
                "ADMIN",
                aid,
                repr(exc),
            )


def install(application=None):
    """Make existing dispatcher and test buttons call the unified V2 briefs."""
    from crm_plus import jobs as crm_jobs
    crm_jobs.morning_brief_job = morning_brief_job
    crm_jobs.evening_brief_job = evening_brief_job
