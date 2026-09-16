"""Atomic creation of student lesson requests.

The public slot list is only a read model. This helper takes a SQLite write
reservation before the final collision checks and INSERT, so two concurrent web
requests cannot both reserve the same teacher interval. Paid one-off lessons may
be requested without prepaid balance; they remain AWAITING_PAYMENT until paid.
"""
from __future__ import annotations

from datetime import datetime

import database
from core import minute_balance

BLOCKING = ('PENDING', 'CONFIRMED', 'IN_PROGRESS')


def _available_minutes(conn, user_id, hourly_rate):
    rows = conn.execute(
        """SELECT source_type,
                  COALESCE(SUM(MAX(COALESCE(minutes_total,0)-COALESCE(minutes_used,0),0)),0) AS remaining
           FROM lesson_packages
           WHERE user_id=? AND status='ACTIVE'
             AND COALESCE(minutes_used,0) < COALESCE(minutes_total,0)
             AND (source_type='BONUS' OR hourly_rate=?)
           GROUP BY source_type""",
        (int(user_id), int(hourly_rate)),
    ).fetchall()
    return sum(int(row['remaining'] or 0) for row in rows)


def create_request(*, user_id, program_id, study_goal, subject, start_time, end_time,
                   duration_minutes, hourly_rate, price, is_trial):
    user_id = int(user_id)
    duration_minutes = int(duration_minutes)
    hourly_rate = int(hourly_rate or 0)
    start = datetime.fromisoformat(str(start_time))
    end = datetime.fromisoformat(str(end_time))
    if end <= start:
        raise ValueError('invalid_interval')

    minute_balance.ensure_schema()
    conn = database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        pending = conn.execute(
            """SELECT 1 FROM lessons WHERE user_id=? AND request_source='STUDENT'
               AND lesson_status='PENDING' LIMIT 1""", (user_id,),
        ).fetchone()
        if pending:raise ValueError('У вас уже есть заявка на подтверждении.')
        same_day = conn.execute(
            """SELECT 1 FROM lessons WHERE user_id=? AND DATE(start_time)=?
               AND lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS','COMPLETED') LIMIT 1""",
            (user_id,start.date().isoformat()),
        ).fetchone()
        if same_day:raise ValueError('В этот день у вас уже есть занятие или заявка.')
        overlap = conn.execute(
            """SELECT 1 FROM lessons WHERE lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
               AND start_time < ? AND end_time > ? LIMIT 1""",(end.isoformat(),start.isoformat()),
        ).fetchone()
        if overlap:raise ValueError('Это время уже занято.')

        if is_trial:
            user=conn.execute('SELECT trial_used FROM users WHERE id=?',(user_id,)).fetchone()
            if not user or int(user['trial_used'] or 0):raise ValueError('trial_unavailable')
            payment_status='FREE'
        else:
            available=_available_minutes(conn,user_id,hourly_rate)
            payment_status='RESERVED_BALANCE' if available>=duration_minutes else 'AWAITING_PAYMENT'

        now=database.now_iso()
        cur=conn.execute(
            """INSERT INTO lessons(user_id,program_id,study_goal,subject,start_time,end_time,
               duration_minutes,hourly_rate,price,lesson_status,request_source,requested_at,
               payment_status,charged,is_trial,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,'PENDING','STUDENT',?,?,0,?,?)""",
            (user_id,int(program_id) if program_id is not None else None,study_goal,subject,
             start.isoformat(),end.isoformat(),duration_minutes,hourly_rate,int(price),now,
             payment_status,int(bool(is_trial)),now),
        )
        lesson_id=int(cur.lastrowid);conn.commit();return lesson_id
    except Exception:
        conn.rollback();raise
    finally:conn.close()
