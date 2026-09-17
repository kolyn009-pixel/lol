from __future__ import annotations

import database


def ensure_schema():
    conn=database.connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS lesson_payment_wait_overrides (
                lesson_id INTEGER PRIMARY KEY,
                risk_notified_at TEXT,
                teacher_wait_confirmed_at TEXT,
                teacher_id INTEGER,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get(lesson_id):
    ensure_schema();conn=database.connect()
    try:
        row=conn.execute("SELECT * FROM lesson_payment_wait_overrides WHERE lesson_id=?",(int(lesson_id),)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def mark_risk(lesson_id):
    ensure_schema();now=database.now_iso();conn=database.connect()
    try:
        conn.execute("""
            INSERT INTO lesson_payment_wait_overrides(lesson_id,risk_notified_at,updated_at)
            VALUES(?,?,?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                risk_notified_at=COALESCE(lesson_payment_wait_overrides.risk_notified_at,excluded.risk_notified_at),
                updated_at=excluded.updated_at
        """,(int(lesson_id),now,now))
        conn.commit()
        return get(lesson_id)
    finally:
        conn.close()


def confirm_wait(lesson_id,teacher_id=None):
    lesson=database.get_lesson(int(lesson_id))
    if not lesson: raise ValueError('lesson_not_found')
    if str(lesson['lesson_status'] or '').upper() not in {'PENDING','CONFIRMED'}: raise ValueError('lesson_not_active')
    if str(lesson['payment_status'] or '').upper()!='AWAITING_PAYMENT': raise ValueError('payment_not_awaiting')
    ensure_schema();now=database.now_iso();conn=database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute("SELECT * FROM lesson_payment_wait_overrides WHERE lesson_id=?",(int(lesson_id),)).fetchone()
        if row and row['teacher_wait_confirmed_at']:
            state=dict(row);state['already_confirmed']=True;conn.rollback();return state
        if row:
            conn.execute("""
                UPDATE lesson_payment_wait_overrides
                SET risk_notified_at=COALESCE(risk_notified_at,?),
                    teacher_wait_confirmed_at=?,
                    teacher_id=COALESCE(teacher_id,?),
                    updated_at=?
                WHERE lesson_id=? AND teacher_wait_confirmed_at IS NULL
            """,(now,now,int(teacher_id) if teacher_id else None,now,int(lesson_id)))
        else:
            conn.execute("""
                INSERT INTO lesson_payment_wait_overrides(lesson_id,risk_notified_at,teacher_wait_confirmed_at,teacher_id,updated_at)
                VALUES(?,?,?,?,?)
            """,(int(lesson_id),now,now,int(teacher_id) if teacher_id else None,now))
        conn.commit()
        row=conn.execute("SELECT * FROM lesson_payment_wait_overrides WHERE lesson_id=?",(int(lesson_id),)).fetchone()
        state=dict(row) if row else {}
        state['already_confirmed']=False
        return state
    except Exception:
        conn.rollback();raise
    finally:
        conn.close()


def suppress_auto_cancel(lesson_id):
    row=get(int(lesson_id))
    return bool(row and (row.get('risk_notified_at') or row.get('teacher_wait_confirmed_at')))


def pending_teacher_decision(lesson_id):
    row=get(int(lesson_id))
    return bool(row and row.get('risk_notified_at') and not row.get('teacher_wait_confirmed_at'))
