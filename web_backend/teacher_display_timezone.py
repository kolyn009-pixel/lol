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


def dashboard_with_instants():
    """Add explicit instants without mutating the cached teacher dashboard."""
    from web_backend.teacher_portal import dashboard

    result = dashboard()
    base = str(result.get('week', {}).get('timezone') or _base_zone())
    tz = ZoneInfo(base)

    def lesson(row):
        item = dict(row)
        for field in ('start_time', 'end_time'):
            raw = item.get(field)
            if raw:
                parsed = datetime.fromisoformat(raw)
                item[field.replace('_time', '_at')] = (parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)).isoformat()
        return item

    return {**result, **{key: [lesson(row) for row in result.get(key, [])]
                       for key in ('today_lessons', 'week_lessons', 'next_lessons')}}
