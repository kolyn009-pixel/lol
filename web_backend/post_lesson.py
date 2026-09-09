"""Shared short post-lesson survey for web/PWA/desktop and bot adapters."""
from __future__ import annotations

from datetime import datetime

import database
from core import event_center


def ensure_schema():
    conn = database.connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lesson_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            difficulty INTEGER,
            understood INTEGER,
            mood INTEGER,
            comment TEXT,
            next_topic TEXT,
            source TEXT NOT NULL DEFAULT 'WEB',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    cols = {r['name'] for r in conn.execute('PRAGMA table_info(lesson_feedback)').fetchall()}
    if 'next_topic' not in cols:
        conn.execute('ALTER TABLE lesson_feedback ADD COLUMN next_topic TEXT')
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_feedback_user_created ON lesson_feedback(user_id, created_at DESC)")
    conn.commit(); conn.close()


def _lesson_owned(user_id, lesson_id):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson or int(lesson['user_id']) != int(user_id):
        raise PermissionError('lesson_not_found')
    return lesson


def get_feedback(user_id, lesson_id):
    ensure_schema(); lesson = _lesson_owned(user_id, lesson_id)
    if not lesson['finished_at']:
        return {'required': False, 'reason': 'lesson_not_finished', 'feedback': None}
    conn = database.connect()
    row = conn.execute("SELECT * FROM lesson_feedback WHERE lesson_id=? AND user_id=?", (int(lesson_id), int(user_id))).fetchone()
    conn.close()
    return {'required': row is None, 'feedback': dict(row) if row else None}


def submit_feedback(user_id, lesson_id, rating, next_topic=None, comment=None, source='WEB', **_legacy):
    """Save the intentionally short student survey: liked it + next lesson wish."""
    ensure_schema(); lesson = _lesson_owned(user_id, lesson_id)
    if not lesson['finished_at']:
        raise ValueError('lesson_not_finished')
    rating = int(rating)
    if rating < 1 or rating > 3:
        raise ValueError('invalid_rating')
    next_topic = str(next_topic or '').strip()[:500] or None
    comment = str(comment or '').strip()[:500] or None
    now = datetime.now().isoformat(timespec='seconds')
    conn = database.connect()
    conn.execute("""
        INSERT INTO lesson_feedback(lesson_id,user_id,rating,comment,next_topic,source,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)
        ON CONFLICT(lesson_id) DO UPDATE SET
            rating=excluded.rating,comment=excluded.comment,next_topic=excluded.next_topic,
            source=excluded.source,updated_at=excluded.updated_at
    """, (int(lesson_id), int(user_id), rating, comment, next_topic, str(source or 'WEB')[:20], now, now))
    conn.commit(); conn.close()
    user = database.get_user(int(user_id))
    name = user['name'] if user else 'Ученик'
    try:
        if next_topic:
            event_center.push(
                'NEXT_LESSON_WISH', f'Пожелание к следующему уроку: {name}', next_topic,
                'INFO', 'lesson', int(lesson_id), f'next_lesson_wish:{int(lesson_id)}',
            )
        if rating == 1:
            event_center.push(
                'LESSON_FEEDBACK_ATTENTION', f'Обратная связь после урока: {name}',
                'Ученику не понравилось занятие' + (f' · {comment}' if comment else ''),
                'ATTENTION', 'lesson', int(lesson_id), f'lesson_feedback:{int(lesson_id)}',
            )
    except Exception:
        pass
    return {'status': 'ok', 'lesson_id': int(lesson_id), 'saved': True}


def recent_for_teacher(limit=50):
    ensure_schema(); conn = database.connect()
    rows = conn.execute("""
        SELECT f.*,u.name,l.subject,l.study_goal,l.start_time
        FROM lesson_feedback f JOIN users u ON u.id=f.user_id JOIN lessons l ON l.id=f.lesson_id
        ORDER BY f.created_at DESC LIMIT ?
    """, (max(1, min(int(limit), 200)),)).fetchall()
    conn.close(); return [dict(r) for r in rows]
