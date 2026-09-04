from __future__ import annotations

from datetime import datetime, timedelta

import database
from . import schema


def initialize():
    c = database.connect()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS vk_teacher_notification_log (
                dedupe_key TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            )
        """)
        c.commit()
    finally:
        c.close()


def _claim(key: str):
    c = database.connect()
    try:
        cur = c.execute(
            "INSERT OR IGNORE INTO vk_teacher_notification_log(dedupe_key,sent_at) VALUES(?,?)",
            (str(key), database.now_iso()),
        )
        c.commit()
        return cur.rowcount > 0
    finally:
        c.close()


def _upcoming(minutes=20):
    now = datetime.now()
    until = now + timedelta(minutes=int(minutes))
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT l.id,l.start_time,l.subject,l.duration,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.start_time>=? AND l.start_time<=?
              AND l.cancelled_at IS NULL
              AND l.lesson_status='CONFIRMED'
            ORDER BY l.start_time
            """,
            (now.isoformat(), until.isoformat()),
        ).fetchall())
    finally:
        c.close()


def tick(send_teacher):
    initialize()
    peers = schema.get_admin_external_ids("VK")
    if not peers:
        return 0
    sent = 0
    for lesson in _upcoming(20):
        key = f"lesson20:{lesson['id']}:{str(lesson['start_time'])[:16]}"
        if not _claim(key):
            continue
        dt = datetime.fromisoformat(str(lesson["start_time"]))
        subject = {"PHYSICS": "Физика", "CHEMISTRY": "Химия"}.get(
            str(lesson["subject"] or "").upper(), str(lesson["subject"] or "Занятие")
        )
        text = (
            "⏰ СКОРО ЗАНЯТИЕ\n\n"
            f"👤 {lesson['name']}\n"
            f"📖 {subject}\n"
            f"🕐 {dt:%H:%M}\n\n"
            "Открой «📅 Сегодня» и выбери занятие, чтобы отправить ссылку или задать ДЗ."
        )
        for peer in peers:
            send_teacher(int(peer), text)
            sent += 1
    return sent
