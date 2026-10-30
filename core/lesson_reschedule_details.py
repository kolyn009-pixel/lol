"""Shared, explicit reschedule details; never infer a student's grade."""
from __future__ import annotations
from zoneinfo import ZoneInfo
import database
from core.lesson_time import schedule_datetime


def get(row, key, default=None):
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def grade_label(value):
    value = str(value or '').strip()
    if not value:
        return 'Класс не указан'
    return value + ' класс' if value.isdigit() else value


def interval(lesson):
    start = schedule_datetime(get(lesson, 'start_time')).astimezone(ZoneInfo('Europe/Moscow'))
    end = schedule_datetime(get(lesson, 'end_time')).astimezone(ZoneInfo('Europe/Moscow'))
    if start.date() == end.date():
        return start.strftime('%d.%m.%Y · %H:%M') + '–' + end.strftime('%H:%M')
    return start.strftime('%d.%m.%Y · %H:%M') + ' — ' + end.strftime('%d.%m.%Y · %H:%M')


def message(before, after, user=None):
    user = user if user is not None else database.get_user(int(after['user_id']))
    name = str(get(user, 'name') or 'Ученик')
    subject = str(get(after, 'subject') or 'Занятие').capitalize()
    return (f"{name} · {grade_label(get(user, 'grade'))} · {subject}\n"
            f"Было: {interval(before)}\nСтало: {interval(after)}\nВремя московское (МСК).")


def previous(lesson):
    """Known replacement link or durable exchange snapshot; no fuzzy matching."""
    parent = get(lesson, 'rescheduled_from_lesson_id')
    if parent:
        row = database.get_lesson(int(parent))
        if row:
            return dict(row)
    c = database.connect()
    try:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='slot_change_requests'").fetchone()
        if not exists:
            return None
        columns = {r['name'] for r in c.execute('PRAGMA table_info(slot_change_requests)')}
        if 'apply_requester_before_start' not in columns:
            return None
        rows = c.execute("""SELECT * FROM slot_change_requests
          WHERE (requester_lesson_id=? OR occupant_lesson_id=?)
            AND status NOT IN ('DECLINED','CANCELLED') ORDER BY id DESC""",
                         (int(lesson['id']), int(lesson['id']))).fetchall()
        for row in rows:
            key = 'requester' if int(row['requester_lesson_id']) == int(lesson['id']) else 'occupant'
            start, end = row['apply_'+key+'_before_start'], row['apply_'+key+'_before_end']
            if not start or not end:
                continue
            # A stored snapshot alone is not proof that the move was applied.
            if key == 'requester':
                target = row['desired_start'] if row['exchange_mode'] == 'SHIFT' else row['apply_occupant_before_start']
            else:
                target = row['occupant_proposed_start'] if row['exchange_mode'] == 'SHIFT' else row['apply_requester_before_start']
            if target and schedule_datetime(target) == schedule_datetime(lesson['start_time']) and schedule_datetime(start) != schedule_datetime(target):
                return dict(lesson, start_time=start, end_time=end)
        return None
    finally:
        c.close()
