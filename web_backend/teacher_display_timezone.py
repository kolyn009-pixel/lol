"""Per-teacher display timezone; never changes booking or bot schedule timezone."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from database import connect, get_setting


def _base_zone():
    name = str(get_setting('bot_timezone', 'Europe/Samara') or 'Europe/Samara')
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
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
    if name == 'schedule':
        conn = connect()
        try:
            _ensure(conn)
            conn.execute('DELETE FROM teacher_display_timezones WHERE admin_telegram_id=?', (int(admin_id),))
            conn.commit()
        finally:
            conn.close()
        return preference(admin_id)
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


def dashboard_with_instants(admin_id=None):
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

    enriched = {**result, **{key: [lesson(row) for row in result.get(key, [])]
                           for key in ('today_lessons', 'week_lessons', 'next_lessons')}}
    if admin_id is None:
        return enriched
    display = preference(admin_id)['timezone']
    now = datetime.now(ZoneInfo(display['zone']))
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    end = start + timedelta(days=7)
    # Include adjacent schedule dates: a local week can start on a different
    # schedule day. Keep stored timestamps untouched; filter exact instants below.
    from web_backend.teacher_portal import _lesson_select
    conn = connect()
    try:
        rows = conn.execute(_lesson_select() + "WHERE l.start_time>=? AND l.start_time<? AND l.lesson_status!='REJECTED'",
                            ((start - timedelta(days=2)).date().isoformat(),
                             (end + timedelta(days=2)).date().isoformat())).fetchall()
    finally:
        conn.close()
    return project_dashboard(enriched, [lesson(row) for row in rows], display, now)


def project_dashboard(result, rows, display, now):
    """Read-only projection, including day/week boundaries in a travel timezone."""
    zone = ZoneInfo(display['zone'])
    now = now.astimezone(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    end = start + timedelta(days=7)
    def local(row):
        return datetime.fromisoformat(row['start_at']).astimezone(zone)
    ordered = sorted(rows, key=lambda row: datetime.fromisoformat(row['start_at']).timestamp())
    week = [row for row in ordered if start <= local(row) < end]
    today = [row for row in ordered if local(row).date() == now.date() or
             (row.get('lesson_status') == 'IN_PROGRESS' and not row.get('finished_at'))]
    excluded = {'CANCELLED', 'LATE_CANCELLED', 'REJECTED', 'SICKNESS', 'NO_SHOW'}
    candidates = {row['id']: row for row in [*result.get('next_lessons', []), *ordered]}
    upcoming = sorted((row for row in candidates.values() if row.get('lesson_status') not in excluded | {'COMPLETED'} and
                      (local(row) >= now or row.get('lesson_status') == 'IN_PROGRESS')),
                      key=lambda row: datetime.fromisoformat(row['start_at']).timestamp())[:8]
    counts = {
        'worked': sum(row.get('lesson_status') == 'COMPLETED' for row in week),
        'remaining': sum(local(row) >= now and row.get('lesson_status') not in excluded | {'COMPLETED'} for row in week),
        'cancelled': sum(row.get('lesson_status') in {'CANCELLED', 'LATE_CANCELLED'} for row in week),
        'sickness': sum(row.get('lesson_status') == 'SICKNESS' for row in week),
        'planned': sum(row.get('lesson_status') not in excluded for row in week),
    }
    expected = sum(int(row.get('price') or 0) for row in week if row.get('lesson_status') not in excluded and row.get('payment_status') in {'AWAITING_PAYMENT', 'UNPAID'})
    return {**result, 'display_timezone': display, 'today_lessons': today,
            'week_lessons': week, 'next_lessons': upcoming,
            'stats': {**result.get('stats', {}), 'lessons_today': sum(row.get('lesson_status') not in excluded for row in today),
                      'unpaid': expected, 'expected_week': expected},
            'week': {**result.get('week', {}), **counts, 'start': start.isoformat(), 'end': end.isoformat(),
                     'today': now.date().isoformat(), 'timezone': display['zone'], 'schedule_timezone': display['schedule_zone']}}
