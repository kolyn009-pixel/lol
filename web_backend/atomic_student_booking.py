"""Atomic creation of student lesson requests.

The public slot list is only a read model. This helper takes a SQLite write
reservation before the final collision checks and INSERT, so two concurrent web
requests cannot both reserve the same teacher interval.
"""
from __future__ import annotations

from datetime import datetime

import database

BLOCKING = ('PENDING', 'CONFIRMED', 'IN_PROGRESS')


def create_request(*, user_id, program_id, study_goal, subject, start_time, end_time,
                   duration_minutes, hourly_rate, price, is_trial):
    user_id = int(user_id)
    start = datetime.fromisoformat(str(start_time))
    end = datetime.fromisoformat(str(end_time))
    if end <= start:
        raise ValueError('invalid_interval')

    conn = database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')

        pending = conn.execute(
            """SELECT 1 FROM lessons
               WHERE user_id=? AND request_source='STUDENT' AND lesson_status='PENDING'
               LIMIT 1""",
            (user_id,),
        ).fetchone()
        if pending:
            raise ValueError('У вас уже есть заявка на подтверждении.')

        same_day = conn.execute(
            """SELECT 1 FROM lessons
               WHERE user_id=? AND DATE(start_time)=?
                 AND lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS','COMPLETED')
               LIMIT 1""",
            (user_id, start.date().isoformat()),
        ).fetchone()
        if same_day:
            raise ValueError('В этот день у вас уже есть занятие или заявка.')

        overlap = conn.execute(
            """SELECT 1 FROM lessons
               WHERE lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
                 AND start_time < ? AND end_time > ?
               LIMIT 1""",
            (end.isoformat(), start.isoformat()),
        ).fetchone()
        if overlap:
            raise ValueError('Это время уже занято.')

        if is_trial:
            user = conn.execute('SELECT trial_used FROM users WHERE id=?', (user_id,)).fetchone()
            if not user or int(user['trial_used'] or 0):
                raise ValueError('trial_unavailable')

        now = database.now_iso()
        cur = conn.execute(
            """INSERT INTO lessons(
                   user_id,program_id,study_goal,subject,start_time,end_time,
                   duration_minutes,hourly_rate,price,lesson_status,request_source,
                   requested_at,payment_status,charged,is_trial,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,'PENDING','STUDENT',?,?,0,?,?)""",
            (
                user_id, int(program_id) if program_id is not None else None,
                study_goal, subject, start.isoformat(), end.isoformat(),
                int(duration_minutes), int(hourly_rate), int(price), now,
                'FREE' if is_trial else 'RESERVED_BALANCE',
                int(bool(is_trial)), now,
            ),
        )
        lesson_id = int(cur.lastrowid)
        conn.commit()
        return lesson_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
