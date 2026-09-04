from __future__ import annotations

from datetime import datetime, timedelta

import database
from core.lesson_time import actual_datetime, lesson_timezone, schedule_datetime

from . import schema


SUBJECT_NAMES = {
    "PHYSICS": "Физика",
    "CHEMISTRY": "Химия",
}


def _timezone():
    return lesson_timezone()


def _schedule_dt(raw):
    return schedule_datetime(raw)


def _actual_dt(raw):
    return actual_datetime(raw)


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
        cur = c.execute("""
            INSERT OR IGNORE INTO vk_teacher_notification_log(dedupe_key,sent_at)
            VALUES(?,?)
        """, (str(key), database.now_iso()))
        c.commit()
        return cur.rowcount > 0
    finally:
        c.close()


def _subject(value):
    raw = str(value or "").upper()
    return SUBJECT_NAMES.get(raw, raw or "Занятие")


def _board_line(board_url):
    value = str(board_url or "").strip()
    if not value:
        return ""
    return "\n\n📝 Доска занятия:\n" + value


def _confirmed_lessons():
    c = database.connect()
    try:
        return list(c.execute("""
            SELECT l.id,l.user_id,l.start_time,l.subject,u.name,u.board_url
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.lesson_status='CONFIRMED' AND l.cancelled_at IS NULL
            ORDER BY l.start_time LIMIT 300
        """).fetchall())
    finally:
        c.close()


def _started_lessons():
    c = database.connect()
    try:
        return list(c.execute("""
            SELECT l.id,l.user_id,l.start_time,l.started_at,l.subject,u.name,u.board_url
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.lesson_status='IN_PROGRESS' AND l.cancelled_at IS NULL
            ORDER BY l.start_time LIMIT 100
        """).fetchall())
    finally:
        c.close()


def _send_before(peers, send_teacher):
    now = datetime.now(_timezone())
    sent = 0
    for lesson in _confirmed_lessons():
        try:
            start = _schedule_dt(lesson["start_time"])
        except Exception:
            continue
        seconds = (start - now).total_seconds()
        if 15 * 60 <= seconds <= 20 * 60:
            key = f"lesson20:{lesson['id']}:{start:%Y%m%d%H%M}"
            if _claim(key):
                text = (
                    "⏰ ЗАНЯТИЕ ЧЕРЕЗ 20 МИНУТ\n\n"
                    f"👤 {lesson['name']}\n📖 {_subject(lesson['subject'])}\n🕐 {start:%H:%M}"
                    f"{_board_line(lesson['board_url'])}"
                    "\n\nОткрой «📅 Сегодня», чтобы подготовить ссылку, доску или ДЗ."
                )
                for peer in peers:
                    send_teacher(int(peer), text)
                    sent += 1
        if 0 <= seconds <= 5 * 60:
            key = f"lesson5:{lesson['id']}:{start:%Y%m%d%H%M}"
            if _claim(key):
                text = (
                    "🔔 ЗАНЯТИЕ ЧЕРЕЗ 5 МИНУТ\n\n"
                    f"👤 {lesson['name']}\n📖 {_subject(lesson['subject'])}\n🕐 {start:%H:%M}"
                    f"{_board_line(lesson['board_url'])}"
                    "\n\nМожно отправить ссылку и затем отдельно нажать «▶️ Начать занятие»."
                )
                for peer in peers:
                    send_teacher(int(peer), text)
                    sent += 1
    return sent


def _send_started(peers, send_teacher):
    sent = 0
    for lesson in _started_lessons():
        key = f"lesson_started:{lesson['id']}"
        if not _claim(key):
            continue
        try:
            actual = _actual_dt(lesson["started_at"])
            time_text = f"{actual:%H:%M}"
        except Exception:
            try:
                time_text = f"{_schedule_dt(lesson['start_time']):%H:%M}"
            except Exception:
                time_text = str(lesson["start_time"])
        text = (
            "▶️ ЗАНЯТИЕ НАЧАЛОСЬ\n\n"
            f"👤 {lesson['name']}\n📖 {_subject(lesson['subject'])}\n▶️ Фактически: {time_text}"
            f"{_board_line(lesson['board_url'])}"
        )
        for peer in peers:
            send_teacher(int(peer), text)
            sent += 1
    return sent


def _ending_lessons():
    c = database.connect()
    try:
        return list(c.execute("""
            SELECT l.id,l.user_id,l.start_time,l.end_time,l.started_at,l.duration_minutes,
                   l.subject,u.name,u.board_url
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.lesson_status='IN_PROGRESS' AND l.cancelled_at IS NULL
              AND l.started_at IS NOT NULL AND l.end_time IS NOT NULL
            ORDER BY l.end_time
        """).fetchall())
    finally:
        c.close()


def _next_lesson(current):
    c = database.connect()
    try:
        return c.execute("""
            SELECT l.id,l.user_id,l.start_time,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.id<>? AND l.cancelled_at IS NULL
              AND l.lesson_status IN ('CONFIRMED','IN_PROGRESS')
              AND l.start_time>=?
            ORDER BY l.start_time LIMIT 1
        """, (int(current["id"]), str(current["end_time"]))).fetchone()
    finally:
        c.close()


def _send_ending(peers, send_teacher):
    now = datetime.now(_timezone())
    sent = 0
    for lesson in _ending_lessons():
        try:
            plan_start = _schedule_dt(lesson["start_time"])
            plan_end = _schedule_dt(lesson["end_time"])
            actual_start = _actual_dt(lesson["started_at"])
            duration = int(lesson["duration_minutes"] or round((plan_end - plan_start).total_seconds() / 60))
            actual_end = actual_start + timedelta(minutes=duration)
        except Exception:
            continue
        delta = round((actual_start - plan_start).total_seconds() / 60)
        late = max(delta, 0)
        early = max(-delta, 0)
        notification_end = actual_end if actual_start < plan_start else plan_end
        seconds = (notification_end - now).total_seconds()
        if not (0 <= seconds <= 5 * 60):
            continue
        key = f"lesson_smart_end5:{lesson['id']}:{notification_end:%Y%m%d%H%M}"
        if not _claim(key):
            continue
        text = (
            "⏳ ДО КОНЦА ЗАНЯТИЯ 5 МИНУТ\n\n"
            f"👤 {lesson['name']}\n📖 {_subject(lesson['subject'])}\n\n"
            f"📅 План: {plan_start:%H:%M}–{plan_end:%H:%M}\n"
            f"▶️ Фактически начали: {actual_start:%H:%M}\n"
        )
        if early:
            text += f"⏹ Полное время закончится: {actual_end:%H:%M}\n✅ Начали раньше на {early} мин."
        elif late:
            text += (
                f"🕐 По расписанию до: {plan_end:%H:%M}\n"
                f"⏱ Полные {duration} минут: до {actual_end:%H:%M}\n"
                f"⚠️ Нужно задержаться на {late} мин."
            )
            nxt = _next_lesson(lesson)
            if nxt:
                try:
                    next_start = _schedule_dt(nxt["start_time"])
                    delay = max(round((actual_end - next_start).total_seconds() / 60), 0)
                    if delay:
                        text += f"\n\n👤 Следующий ученик: {nxt['name']} в {next_start:%H:%M}. Возможная задержка: {delay} мин."
                except Exception:
                    pass
        else:
            text += f"⏹ Окончание: {plan_end:%H:%M}"
        text += _board_line(lesson["board_url"])
        text += "\n\nОткрой карточку занятия: там доступны действия завершения и предупреждения следующего ученика."
        for peer in peers:
            send_teacher(int(peer), text)
            sent += 1
    return sent


def tick(send_teacher):
    initialize()
    peers = schema.get_admin_external_ids("VK")
    if not peers:
        return 0
    sent = 0
    sent += _send_before(peers, send_teacher)
    sent += _send_started(peers, send_teacher)
    sent += _send_ending(peers, send_teacher)
    return sent
