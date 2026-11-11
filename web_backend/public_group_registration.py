"""Public recruitment leads, separate from membership and lesson booking."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlsplit
import database
from web_backend import group_lessons


def ensure_schema():
    group_lessons.ensure_schema()
    c = database.connect()
    try:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS public_group_registrations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          group_id INTEGER NOT NULL REFERENCES study_groups(id),
          name TEXT NOT NULL, grade INTEGER NOT NULL,
          contact TEXT NOT NULL, contact_key TEXT NOT NULL,
          timezone TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'NEW',
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          consent_at TEXT NOT NULL, reviewed_by INTEGER);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_public_group_open_contact
          ON public_group_registrations(group_id,contact_key)
          WHERE status IN ('NEW','CONTACTED','WAITLIST');
        ''')
        c.commit()
    finally:
        c.close()


def _public_group(c, group_id):
    row = c.execute('''SELECT id,name,subject,study_goal,description,
        price_per_lesson,max_members,recruitment_status
        FROM study_groups WHERE id=? AND active=1
        AND recruitment_status IN ('OPEN','WAITLIST')''', (int(group_id),)).fetchone()
    if row is None:
        raise ValueError('group_not_available')
    g = dict(row)
    count = c.execute("SELECT COUNT(*) FROM group_members WHERE group_id=? AND status IN ('ACTIVE','PAUSED')", (g['id'],)).fetchone()[0]
    g['seats_left'] = max(0, int(g['max_members']) - count) if g['max_members'] else None
    g['waitlist'] = g['recruitment_status'] == 'WAITLIST' or g['seats_left'] == 0
    return g


def preview(group_id):
    ensure_schema()
    from core.lesson_time import lesson_timezone
    tz = lesson_timezone()
    today = datetime.now(tz).date().isoformat()
    c = database.connect()
    try:
        g = _public_group(c, group_id)
        # Slot validity windows are optional on installations without invitations.
        windows = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_slot_windows'").fetchone()
        join = 'LEFT JOIN group_slot_windows w ON w.slot_id=s.id' if windows else ''
        valid = 'AND (w.ends_on IS NULL OR w.ends_on>=?)' if windows else ''
        args = (g['id'], today) if windows else (g['id'],)
        slots = [dict(r) for r in c.execute(f'''SELECT s.weekday,s.start_time,s.duration_minutes
            FROM group_schedule_slots s {join} WHERE s.group_id=? AND s.active=1 {valid}
            ORDER BY s.weekday,s.start_time''', args)]
        return {'group': g, 'slots': slots, 'timezone': str(tz)}
    finally:
        c.close()


def _text(value, limit, required=False):
    text = ' '.join(str(value or '').split())
    if len(text) > limit or (required and not text):
        raise ValueError('invalid_fields')
    return text


def normalize_contact(value):
    """Validate supported contact syntax without contacting messenger services."""
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValueError('invalid_contact')
    text = value.strip()
    if re.fullmatch(r'\+?[0-9\s()\-]+', text):
        digits = re.sub(r'[^0-9]', '', text)
        if text.count('(') != text.count(')') or text.count('(') > 1 or (')' in text and text.index(')') < text.index('(')):
            raise ValueError('invalid_contact')
        if not text.startswith('+'):
            if len(digits) == 10:
                digits = '7' + digits
            elif len(digits) == 11 and digits[0] in '78':
                digits = '7' + digits[1:]
            else:
                raise ValueError('invalid_contact')
        if not 8 <= len(digits) <= 15 or digits[0] == '0' or len(set(digits)) < 2:
            raise ValueError('invalid_contact')
        if digits.startswith('7') and len(digits) != 11:
            raise ValueError('invalid_contact')
        return '+' + digits, 'phone:' + digits
    if re.fullmatch(r'@[A-Za-z][A-Za-z0-9_]{4,31}', text):
        username = text[1:].lower()
        return '@' + username, 'telegram:' + username
    if re.search(r'\s', text) or '\\' in text:
        raise ValueError('invalid_contact')
    try:
        url = urlsplit(text if '://' in text else 'https://' + text)
        if url.scheme not in {'http', 'https'} or url.username or url.password or url.port:
            raise ValueError('invalid_contact')
        host = (url.hostname or '').lower()
        path = url.path.strip('/')
    except ValueError:
        raise ValueError('invalid_contact') from None
    if host in {'t.me', 'www.t.me', 'telegram.me', 'www.telegram.me'} and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', path):
        username = path.lower()
        return '@' + username, 'telegram:' + username
    if host in {'vk.com', 'www.vk.com', 'm.vk.com', 'vk.ru', 'www.vk.ru', 'm.vk.ru'}:
        screen = path.lower()
        reserved = {'feed', 'im', 'join', 'login', 'settings', 'support', 'help', 'away', 'search', 'apps', 'friends', 'groups', 'video', 'videos', 'clips', 'audio', 'audios', 'market', 'wall', 'photo', 'photos', 'album', 'albums', 'topic', 'page'}
        if (re.fullmatch(r'id[1-9][0-9]*', screen) or re.fullmatch(r'[a-z][a-z0-9_.]{2,63}', screen)) and screen not in reserved and not re.match(r'^(?:club|public|event|wall|photo|video|album|topic|page|app)[0-9_-]', screen):
            return 'https://vk.ru/' + screen, 'vk:' + screen
    raise ValueError('invalid_contact')


def register(body):
    if not isinstance(body, dict):
        raise ValueError('invalid_fields')
    if body.get('consent') is not True:
        raise ValueError('consent_required')
    name = _text(body.get('name'), 80, True)
    contact, key = normalize_contact(body.get('contact'))
    grade = int(body.get('grade') or 0)
    if grade not in range(5, 12):
        raise ValueError('invalid_grade')
    timezone = _text(body.get('timezone'), 80, True)
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('invalid_timezone') from None
    note = _text(body.get('note'), 600)
    source = _text(body.get('source'), 200)
    ensure_schema()
    c = database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        g = _public_group(c, body.get('group_id'))
        existing = c.execute("SELECT id,status FROM public_group_registrations WHERE group_id=? AND contact_key=? AND status IN ('NEW','CONTACTED','WAITLIST')", (g['id'], key)).fetchone()
        if not existing:
            # Older versions stored raw contact keys. Compare without rewriting
            # existing leads or altering their names, notes and review history.
            for row in c.execute("SELECT id,status,contact FROM public_group_registrations WHERE group_id=? AND status IN ('NEW','CONTACTED','WAITLIST')", (g['id'],)):
                try:
                    same = normalize_contact(row['contact'])[1] == key
                except ValueError:
                    continue
                if same:
                    existing = row
                    break
        if existing:
            # Do not expose an existing person's request id, contact or status.
            c.rollback()
            return {'status': 'ok', 'waitlist': g['waitlist']}
        now = database.now_iso()
        status = 'WAITLIST' if g['waitlist'] else 'NEW'
        cur = c.execute('''INSERT INTO public_group_registrations
            (group_id,name,grade,contact,contact_key,timezone,note,source,status,created_at,updated_at,consent_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', (g['id'], name, grade, contact, key, timezone, note, source, status, now, now, now))
        rid = cur.lastrowid
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    try:
        from core import event_center
        event_center.push('GROUP_REGISTRATION', 'Заявка в группу: ' + g['name'],
            name + ' · ' + str(grade) + ' класс', 'ACTION',
            'public_group_registration', rid, 'group-registration:' + str(rid))
    except Exception as exc:
        print('[group-registration] event notification:', type(exc).__name__, flush=True)
    return {'status': 'ok', 'waitlist': g['waitlist']}


def list_for_teacher(limit=100):
    ensure_schema()
    c = database.connect()
    try:
        return [dict(r) for r in c.execute('''SELECT r.id,r.group_id,r.name,r.grade,
            r.contact,r.timezone,r.note,r.source,r.status,r.created_at,g.name AS group_name
            FROM public_group_registrations r JOIN study_groups g ON g.id=r.group_id
            WHERE r.status IN ('NEW','CONTACTED','WAITLIST')
            ORDER BY r.created_at,r.id LIMIT ?''', (max(1, min(int(limit), 300)),))]
    finally:
        c.close()


def review(request_id, status, teacher_id):
    if status not in {'CONTACTED', 'CLOSED'}:
        raise ValueError('invalid_status')
    ensure_schema()
    c = database.connect()
    try:
        with c:
            cur = c.execute("UPDATE public_group_registrations SET status=?,updated_at=?,reviewed_by=? WHERE id=? AND status IN ('NEW','CONTACTED','WAITLIST')", (status, database.now_iso(), int(teacher_id), int(request_id)))
            if not cur.rowcount:
                raise ValueError('registration_not_found')
        return {'status': 'ok'}
    finally:
        c.close()
