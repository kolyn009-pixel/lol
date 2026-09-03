from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import database
from core import effective_pricing

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
    start = datetime.fromisoformat(str(lesson["start_time"]))
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz())
    else:
        start = start.astimezone(_tz())

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
        f"🕐 {start.strftime('%H:%M')}\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} минут"
    )

    if reminder_type == "LESSON_LINK_10M":
        board_url = str(user["board_url"] or "").strip()
        if board_url:
            text += f"\n\n🔗 Ссылка на занятие:\n{board_url}"
        else:
            text += "\n\n⚠️ Ссылка на занятие ещё не сохранена. Напиши преподавателю."
    return text


def _payment_text(lesson, reminder_type):
    start = datetime.fromisoformat(str(lesson["start_time"]))
    if start.tzinfo is None:
        start = start.replace(tzinfo=_tz())
    else:
        start = start.astimezone(_tz())
    try:
        amount = int(effective_pricing.effective_lesson_price(lesson))
    except Exception:
        amount = int(lesson["price"] or 0)
    tail = "До занятия осталось меньше суток." if reminder_type == "PAYMENT_24H" else "До занятия осталось около 8 часов."
    return (
        "💳 Небольшое напоминание об оплате 💜\n\n"
        f"📅 {start.strftime('%d.%m.%Y в %H:%M')}\n"
        f"💰 {amount:,} ₽\n\n".replace(",", " ")
        f"{tail}\n\n"
        "Пожалуйста, подтверди оплату не позднее чем за 2 часа до занятия."
    )


def tick(send_func):
    """Duplicate actionable Telegram reminders to linked VK accounts.

    send_func(peer_id, text, linked=True) must raise on delivery failure.
    Own delivery log prevents VK duplicates and does not interfere with Telegram reminder flags.
    """
    initialize()
    now = datetime.now(_tz())
    c = database.connect()
    try:
        lessons = c.execute("""
            SELECT l.*, u.name, u.board_url, u.active AS user_active
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE u.active=1
              AND l.lesson_status='CONFIRMED'
              AND l.cancelled_at IS NULL
              AND datetime(l.start_time)>=datetime('now','-20 minutes')
              AND datetime(l.start_time)<=datetime('now','+25 hours')
            ORDER BY datetime(l.start_time)
        """).fetchall()
    finally:
        c.close()

    sent = 0
    for lesson in lessons:
        user_id = int(lesson["user_id"])
        peer = _vk_peer(user_id)
        if not peer:
            continue
        try:
            start = datetime.fromisoformat(str(lesson["start_time"]))
            if start.tzinfo is None:
                start = start.replace(tzinfo=_tz())
            else:
                start = start.astimezone(_tz())
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
            for rtype, offset in PAYMENT_OFFSETS.items():
                event_key = f"payment:{int(lesson['id'])}:{rtype}"
                if _was_sent(user_id, event_key) or not _due(start, offset, now):
                    continue
                send_func(peer, _payment_text(lesson, rtype), linked=True)
                _mark_sent(user_id, event_key)
                sent += 1
    return sent
