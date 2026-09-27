"""Per-teacher display timezone; never changes booking or bot schedule timezone."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import connect, get_setting


def _base_zone():
    name = str(get_setting('bot_timezone', 'Europe/Samara') or 'Europe/Samara')
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        name = 'Europe/Samara'
    return name


def _ensure(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS teacher_display_timezones (
        admin_telegram_id INTEGER PRIMARY KEY,
        timezone TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )''')


def preference(admin_id):
    base = _base_zone()
    conn = connect()
    try:
        _ensure(conn)
        row = conn.execute('SELECT timezone FROM teacher_display_timezones WHERE admin_telegram_id=?',
                           (int(admin_id),)).fetchone()
    finally:
        conn.close()
    name = row['timezone'] if row else base
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        name = base
    return {'timezone': {'zone': name, 'selected': bool(row), 'schedule_zone': base}}


def set_preference(admin_id, zone):
    name = str(zone or '').strip()
    if not name or len(name) > 100:
        raise ValueError('invalid_timezone')
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('invalid_timezone')
    conn = connect()
    try:
        _ensure(conn)
        conn.execute('''INSERT INTO teacher_display_timezones(admin_telegram_id,timezone,updated_at)
                        VALUES(?,?,?) ON CONFLICT(admin_telegram_id) DO UPDATE SET
                        timezone=excluded.timezone,updated_at=excluded.updated_at''',
                     (int(admin_id), name, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()
    return {'timezone': {'zone': name, 'selected': True, 'schedule_zone': _base_zone()}}
