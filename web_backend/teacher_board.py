"""Teacher-facing management of each student's persistent lesson board."""
from __future__ import annotations

from urllib.parse import urlparse

import database

MAX_URL = 1200


def _student(user_id):
    row = database.get_user(int(user_id))
    if not row:
        raise ValueError('student_not_found')
    return row


def get_board(user_id):
    row = _student(user_id)
    return {
        'student_id': int(row['id']),
        'student_name': row['name'],
        'board_url': row['board_url'] if 'board_url' in row.keys() else None,
    }


def _validated_url(value):
    value = str(value or '').strip()
    if not value:
        return None
    if len(value) > MAX_URL:
        raise ValueError('board_url_too_long')
    parsed = urlparse(value)
    if parsed.scheme not in {'https', 'http'} or not parsed.netloc:
        raise ValueError('invalid_board_url')
    return value


def set_board(user_id, board_url):
    row = _student(user_id)
    value = _validated_url(board_url)
    conn = database.connect()
    cur = conn.execute('UPDATE users SET board_url=? WHERE id=?', (value, int(row['id'])))
    conn.commit(); conn.close()
    if cur.rowcount != 1:
        raise ValueError('student_not_found')
    return {
        'status': 'ok',
        'student_id': int(row['id']),
        'student_name': row['name'],
        'board_url': value,
    }


def clear_board(user_id):
    return set_board(user_id, None)
