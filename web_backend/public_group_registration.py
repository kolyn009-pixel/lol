"""Public recruitment leads, separate from membership and lesson booking."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
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


def register(body):
    if not isinstance(body, dict):
        raise ValueError('invalid_fields')
    if body.get('consent') is not True:
        raise ValueError('consent_required')
    name = _text(body.get('name'), 80, True)
    contact = _text(body.get('contact'), 160, True)
    # A contact is entered explicitly; it is never inferred from an existing account.
    if len(contact) < 5:
        raise ValueError('invalid_contact')
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
    key = contact.casefold()
    if re.fullmatch(r'[+\d\s()\-]+', contact):
        key = re.sub(r'\D', '', contact)
    ensure_schema()
    c = database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        g = _public_group(c, body.get('group_id'))
        existing = c.execute("SELECT id,status FROM public_group_registrations WHERE group_id=? AND contact_key=? AND status IN ('NEW','CONTACTED','WAITLIST')", (g['id'], key)).fetchone()
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
