from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import database
from core import effective_pricing, payment_reminder_routing
from core.lesson_time import schedule_datetime

SUBJECT_NAMES = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}

LESSON_OFFSETS = {
    "LESSON_24H": timedelta(hours=24),
    "LESSON_2H": timedelta(hours=2),
    "LESSON_30M": timedelta(minutes=30),
    "LESSON_LINK_10M": timedelta(minutes=10),
}

PAYMENT_OFFSETS = {
    "PAYMENT_24H": timedelta(hours=24),
    "PAYMENT_8H": timedelta(hours=8),
}


def _tz():
    name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Samara")


def _student_tz(lesson):
    """Timezone of the student: personal region if configured (by telegram_id),
    otherwise the teacher/TutorBot timezone (same fallback as Telegram)."""
    fallback = _tz()
    try:
        tid = lesson["student_telegram_id"]
    except (KeyError, IndexError):
        tid = None
    if not tid:
        return fallback, None
    try:
        from core import user_timezone
        zone = str(getattr(fallback, "key", "Europe/Samara"))
        return user_timezone.user_tz(int(tid), zone), user_timezone.user_label(int(tid), zone)
    except Exception:
        return fallback, None


def _student_start(lesson):
    tz, label = _student_tz(lesson)
    return schedule_datetime(lesson["start_time"]).astimezone(tz), label


def initialize():
    c = database.connect()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS channel_delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                event_key TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                UNIQUE(channel, user_id, event_key),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_channel_delivery_event ON channel_delivery_log(channel,event_key)")
        c.commit()
    finally:
        c.close()


def _was_sent(user_id, event_key):
    initialize()
    c = database.connect()
    try:
        row = c.execute(
            "SELECT 1 FROM channel_delivery_log WHERE channel='VK' AND user_id=? AND event_key=?",
            (int(user_id), str(event_key)),
        ).fetchone()
        return bool(row)
    finally:
        c.close()


def _mark_sent(user_id, event_key):
    c = database.connect()
    try:
        c.execute(
            "INSERT OR IGNORE INTO channel_delivery_log(channel,user_id,event_key,delivered_at) VALUES('VK',?,?,?)",
            (int(user_id), str(event_key), database.now_iso()),
        )
        c.commit()
    finally:
        c.close()


def _vk_peer(user_id):
    c = database.connect()
    try:
        row = c.execute("""
            SELECT external_id
            FROM channel_identities
            WHERE user_id=? AND channel='VK' AND enabled=1
            LIMIT 1
        """, (int(user_id),)).fetchone()
        return int(row["external_id"]) if row else None
    finally:
        c.close()


def _due(start_dt, offset, now, grace_minutes=15):
    due_at = start_dt - offset
    return due_at <= now <= due_at + timedelta(minutes=int(grace_minutes))


def _lesson_text(user, lesson, reminder_type):
    subject = SUBJECT_NAMES.get(str(lesson["subject"] or "").upper(), str(lesson["subject"] or "Занятие"))
    start, label = _student_start(lesson)
    intros = {
        "LESSON_24H": "💜 Небольшое напоминание\n\nЗавтра у тебя занятие.",
        "LESSON_2H": "⏰ До занятия осталось 2 часа.",
        "LESSON_30M": "👀 Через 30 минут начинается занятие.",
        "LESSON_LINK_10M": "🔗 Через 10 минут начинаем занятие.",
    }
    text = (
        f"{intros.get(reminder_type, '⏰ Напоминание о занятии')}\n\n"
        f"📖 {subject}\n"
        f"📅 {start.strftime('%d.%m.%Y')}\n"
        f"🕐 {start.strftime('%H:%M')}" + (f" · {label}" if label else "") + "\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} минут"
    )
    if reminder_type == "LESSON_LINK_10M":
        text += (
            "\n\nПреподаватель сейчас подготовит актуальную ссылку на Телемост. "
            "Как только он отправит её, здесь придут и ссылка для подключения, и ссылка на доску."
        )
    return text


def _payment_text(lesson, reminder_type):
    # Naive values are schedule-timezone wall clock (schedule_datetime), not
    # bot_timezone; display in the student's own timezone.
    start, label = _student_start(lesson)
    try:
        amount = int(effective_pricing.effective_lesson_price(lesson))
    except Exception:
        amount = int(lesson["price"] or 0)
    amount_text = f"{amount:,}".replace(",", " ")
    tail = "До занятия осталось меньше суток." if reminder_type == "PAYMENT_24H" else "До занятия осталось около 8 часов."
    return (
        "💳 Небольшое напоминание об оплате 💜\n\n"
        f"📅 {start.strftime('%d.%m.%Y в %H:%M')}" + (f" · {label}" if label else "") + "\n"
        f"💰 {amount_text} ₽\n\n"
        f"{tail}\n\n"
        "Пожалуйста, подтверди оплату не позднее чем за 2 часа до занятия."
    )


def tick(send_func):
    """Duplicate reminders to student VK, except parent-owned payment reminders."""
    initialize()
    now = datetime.now(_tz())
    c = database.connect()
    try:
        # datetime() prefilter is only a coarse window (it normalises offset
        # values to UTC but treats naive ones as UTC too); exact due checks
        # happen on aware datetimes below.
        lessons = c.execute("""
            SELECT l.*, u.name, u.board_url, u.active AS user_active,
                   u.telegram_id AS student_telegram_id
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE u.active=1
              AND l.lesson_status='CONFIRMED'
              AND l.cancelled_at IS NULL
              AND datetime(l.start_time)>=datetime('now','-1 day')
              AND datetime(l.start_time)<=datetime('now','+2 days')
        """).fetchall()
    finally:
        c.close()

    from core.lesson_time import sort_by_start
    lessons = sort_by_start(lessons)
    sent = 0
    for lesson in lessons:
        user_id = int(lesson["user_id"])
        peer = _vk_peer(user_id)
        if not peer:
            continue
        try:
            start = schedule_datetime(lesson["start_time"])
        except Exception:
            continue

        if str(lesson["payment_status"] or "") != "AWAITING_PAYMENT":
            for rtype, offset in LESSON_OFFSETS.items():
                event_key = f"lesson:{int(lesson['id'])}:{rtype}"
                if _was_sent(user_id, event_key) or not _due(start, offset, now):
                    continue
                send_func(peer, _lesson_text(lesson, lesson, rtype), linked=True)
                _mark_sent(user_id, event_key)
                sent += 1
        else:
            # Payment communication belongs to the parent whenever one is linked.
            # Do not leak/duplicate it to the student's VK account.
            if payment_reminder_routing.has_parent_recipient(user_id):
                continue
            for rtype, offset in PAYMENT_OFFSETS.items():
                event_key = f"payment:{int(lesson['id'])}:{rtype}"
                if _was_sent(user_id, event_key) or not _due(start, offset, now):
                    continue
                send_func(peer, _payment_text(lesson, rtype), linked=True)
                _mark_sent(user_id, event_key)
                sent += 1
    return sent
