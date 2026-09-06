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
    post_lesson.initialize()
    c = database.connect()
    try:
        rows = list(c.execute(
            """
            SELECT l.id,l.user_id,l.finished_at,u.name,s.homework_status,s.selected_json
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            LEFT JOIN post_lesson_review_sync s ON s.lesson_id=l.id
            WHERE l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
            ORDER BY datetime(l.finished_at) DESC
            LIMIT 80
            """
        ).fetchall())
        out = []
        for row in rows:
            lid = int(row["id"])
            has_hw = c.execute(
                "SELECT 1 FROM homeworks WHERE lesson_id=? LIMIT 1",
                (lid,),
            ).fetchone()
            if has_hw:
                continue
            status = str(row["homework_status"] or "PENDING").upper()
            if status in {"SKIPPED", "SENT"}:
                continue
            marks = post_lesson.draft_marks(lid)
            summary = post_lesson.review_summary(lid)
            topics = summary.get("topics") or [post_lesson.topic_row(m[0])["topic"] for m in marks if post_lesson.topic_row(m[0])]
            out.append({
                "lesson_id": lid,
                "user_id": int(row["user_id"]),
                "name": row["name"],
                "status": status,
                "topics": topics[:3],
            })
            if len(out) >= limit:
                break
        return out
    except Exception:
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


def _queue_markup(morning=False):
    first = "🌅 Разобрать утро" if morning else "🌙 Закрыть хвосты дня"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(first, callback_data="ux_review_start")],
        [InlineKeyboardButton("🧾 Чеки", callback_data="receipt_center"), InlineKeyboardButton("💳 Оплаты", callback_data="mh_debts")],
        [InlineKeyboardButton("📅 Сегодня", callback_data="crm_today"), InlineKeyboardButton("⚠️ Внимание", callback_data="mh_attention")],
        [InlineKeyboardButton("🏠 Главная", callback_data="global_home")],
    ])


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
            await context.bot.send_message(aid, "\n".join(lines)[:3900], reply_markup=_queue_markup(True))
            database.set_setting("morning_brief_last_ok", now.isoformat(timespec="minutes"))
            database.log_automation_delivery("morning_brief_v2", "OK", "ADMIN", aid)
        except Exception as exc:
            database.log_automation_delivery("morning_brief_v2", "ERROR", "ADMIN", aid, repr(exc))


async def evening_brief_job(context):
    now = datetime.now(_tz())
    day = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    lessons = _today_lessons(day)
    tomorrow_lessons = _today_lessons(tomorrow)
    receipts = _waiting_receipts()
    messages = _open_messages()
    reviews = _unfinished_reviews()
    hw_gaps = _homework_gaps()

    done = [x for x in lessons if str(x["lesson_status"] or "").upper() == "COMPLETED" or x["finished_at"]]
    cancelled = [x for x in lessons if str(x["lesson_status"] or "").upper() in {"CANCELLED", "REJECTED"}]
    unpaid_tomorrow = _today_payment_attention(tomorrow_lessons)

    lines = [
        "💜 АДЕЛИЯ • ИТОГ ДНЯ",
        "",
        "Закрываю день по фактическим данным занятия, опросам, ДЗ и оплатам.",
        "",
        f"✅ Проведено занятий: {len(done)}",
    ]
    for lesson in done[:8]:
        start = _fmt_actual(lesson["started_at"]) if lesson["started_at"] else _fmt_time(lesson["start_time"])
        finish = _fmt_actual(lesson["finished_at"]) if lesson["finished_at"] else "—"
        lines.append(f"• {lesson['name']} · факт {start}–{finish}")

    lines += [
        f"❌ Отменено: {len(cancelled)}",
        f"🧠 Незавершённых опросов: {len(reviews)}",
        f"📝 Темы выбраны / ДЗ не отправлено: {len(hw_gaps)}",
        f"🧾 Чеков ждут проверки: {receipts}",
        f"💬 Сообщений ждут ответа: {messages}",
        f"📅 Занятий завтра: {len(tomorrow_lessons)}",
        f"🔴 Завтра без оплаты: {len(unpaid_tomorrow)}",
    ]

    if hw_gaps:
        lines += ["", "📝 Не закрыты ДЗ:"]
        for item in hw_gaps[:6]:
            topic_text = ", ".join(item["topics"]) if item["topics"] else "без сохранённой темы"
            lines.append(f"• {item['name']} — {topic_text}")

    if reviews:
        lines += ["", "🧠 Не закрыты итоги занятий:"]
        for item in reviews[:5]:
            lines.append(f"• {item['name']} · занятие #{item['id']}")

    for aid in _admins():
        try:
            await context.bot.send_message(aid, "\n".join(lines)[:3900], reply_markup=_queue_markup(False))
            database.set_setting("evening_brief_last_ok", now.isoformat(timespec="minutes"))
            database.log_automation_delivery("evening_brief_v2", "OK", "ADMIN", aid)
        except Exception as exc:
            database.log_automation_delivery("evening_brief_v2", "ERROR", "ADMIN", aid, repr(exc))


def install(application=None):
    """Make existing dispatcher and test buttons call the unified V2 briefs."""
    from crm_plus import jobs as crm_jobs
    crm_jobs.morning_brief_job = morning_brief_job
    crm_jobs.evening_brief_job = evening_brief_job
