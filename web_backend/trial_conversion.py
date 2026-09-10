"""Convert an expiring public trial into an already-created canonical student.

Both web and bot registration adapters should call claim_continuation_code after
normal account creation/authentication. This avoids a second registration model.
"""
from __future__ import annotations

from datetime import datetime

import database
from web_backend import public_trial


def ensure_schema():
    c=database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS public_trial_conversions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      request_id INTEGER NOT NULL UNIQUE,
      user_id INTEGER NOT NULL,
      trial_start TEXT,
      trial_end TEXT,
      trial_finished_at TEXT,
      subject TEXT,
      study_goal TEXT,
      board_url TEXT,
      converted_at TEXT NOT NULL,
      FOREIGN KEY(request_id) REFERENCES public_trial_requests(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_trial_conversions_user ON public_trial_conversions(user_id,converted_at DESC);
    """)
    c.commit();c.close()


def preview(code):
    return public_trial.validate_continuation_code(code)


def claim_continuation_code(user_id, code):
    """Atomically attach trial history/board to the canonical student and consume code."""
    ensure_schema();uid=int(user_id)
    user=database.get_user(uid)
    if not user:raise PermissionError('student_not_found')
    data=public_trial.validate_continuation_code(code)
    req=public_trial.get(int(data['request_id']))
    if not req:raise ValueError('trial_request_not_found')
    now=datetime.now().isoformat(timespec='seconds')
    c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        # Revalidate under the write lock so the one-time code cannot be claimed twice.
        current=public_trial.validate_continuation_code(code)
        if int(current['request_id'])!=int(req['id']):raise ValueError('invalid_or_expired_code')
        existing=c.execute('SELECT id FROM public_trial_conversions WHERE request_id=?',(int(req['id']),)).fetchone()
        if existing:raise ValueError('code_already_used')
        # Preserve an existing teacher-set board; otherwise inherit the board used at trial.
        board=req.get('board_url')
        row=c.execute('SELECT board_url FROM users WHERE id=?',(uid,)).fetchone()
        if row and not row['board_url'] and board:
            c.execute('UPDATE users SET board_url=? WHERE id=?',(board,uid))
        # A converted public trial is definitively a used trial.
        try:c.execute('UPDATE users SET trial_used=1 WHERE id=?',(uid,))
        except Exception:pass
        c.execute("""INSERT INTO public_trial_conversions(request_id,user_id,trial_start,trial_end,trial_finished_at,subject,study_goal,board_url,converted_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",(int(req['id']),uid,req.get('trial_start'),req.get('trial_end'),req.get('trial_finished_at'),req.get('subject'),req.get('study_goal'),board,now))
        # Consume the hash directly inside this transaction instead of delegating another connection.
        c.execute("""UPDATE public_trial_requests SET status='CONVERTED',continuation_code_used_at=?,converted_user_id=?,updated_at=?,expires_at=?
          WHERE id=? AND continuation_code_used_at IS NULL""",(now,uid,now,now,int(req['id'])))
        c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()
    return {
      'status':'ok','user_id':uid,'request_id':int(req['id']),'board_url':board,
      'trial':{'start':req.get('trial_start'),'end':req.get('trial_end'),'finished_at':req.get('trial_finished_at'),'subject':req.get('subject'),'study_goal':req.get('study_goal')}
    }
