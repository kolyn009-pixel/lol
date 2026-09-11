"""Public, read-only landing feed for groups with open recruitment and upcoming events."""
from __future__ import annotations

from datetime import datetime
import database
from web_backend import group_lessons, group_portal


def _now():
    return database.now_iso()


def _event_label(kind):
    return {
        'MOCK_EXAM': 'Пробник',
        'INTENSIVE': 'Интенсив',
        'WORKSHOP': 'Разбор',
        'WEBINAR': 'Событие',
    }.get(str(kind or '').upper(), 'Событие')


def feed(group_limit=12, event_limit=12):
    """Return only public-safe data. Open/WAITLIST groups publish automatically."""
    group_lessons.ensure_schema()
    group_portal.ensure_schema()
    now = _now()
    c = database.connect()
    groups = c.execute(
        """
        SELECT g.id,g.name,g.subject,g.study_goal,g.description,g.price_per_lesson,
               g.max_members,g.recruitment_status,
               (SELECT COUNT(*) FROM group_members m
                WHERE m.group_id=g.id AND m.status IN ('ACTIVE','PAUSED')) AS member_count,
               (SELECT MIN(l.start_time) FROM group_lessons l
                WHERE l.group_id=g.id AND l.start_time>=? AND l.status='SCHEDULED') AS next_lesson
        FROM study_groups g
        WHERE g.active=1 AND g.recruitment_status IN ('OPEN','WAITLIST')
        ORDER BY CASE g.recruitment_status WHEN 'OPEN' THEN 0 ELSE 1 END, g.updated_at DESC
        LIMIT ?
        """,
        (now, max(1, min(int(group_limit), 50))),
    ).fetchall()
    events = c.execute(
        """
        SELECT e.id,e.title,e.event_type,e.subject,e.grade_min,e.grade_max,e.starts_at,e.ends_at,
               e.price_per_student,e.max_participants,e.registration_deadline,e.status,
               (SELECT COUNT(*) FROM open_event_participants p
                WHERE p.event_id=e.id AND p.status='REGISTERED') AS participant_count
        FROM open_learning_events e
        WHERE e.status='OPEN' AND e.starts_at>=?
          AND (e.registration_deadline IS NULL OR e.registration_deadline='' OR e.registration_deadline>=?)
        ORDER BY e.starts_at ASC
        LIMIT ?
        """,
        (now, now, max(1, min(int(event_limit), 50))),
    ).fetchall()
    c.close()

    out_groups = []
    for row in groups:
        r = dict(row)
        max_members = int(r.get('max_members') or 0)
        members = int(r.get('member_count') or 0)
        out_groups.append({
            'kind': 'GROUP',
            'id': int(r['id']),
            'title': r['name'],
            'subject': r.get('subject'),
            'study_goal': r.get('study_goal'),
            'description': r.get('description'),
            'price': int(r.get('price_per_lesson') or 0),
            'recruitment_status': r.get('recruitment_status'),
            'member_count': members,
            'max_members': max_members,
            'seats_left': max(max_members - members, 0) if max_members else None,
            'next_lesson': r.get('next_lesson'),
        })

    out_events = []
    for row in events:
        r = dict(row)
        maximum = int(r.get('max_participants') or 0)
        count = int(r.get('participant_count') or 0)
        out_events.append({
            'kind': 'EVENT',
            'id': int(r['id']),
            'title': r['title'],
            'event_type': r.get('event_type'),
            'event_label': _event_label(r.get('event_type')),
            'subject': r.get('subject'),
            'grade_min': r.get('grade_min'),
            'grade_max': r.get('grade_max'),
            'starts_at': r.get('starts_at'),
            'price': int(r.get('price_per_student') or 0),
            'participant_count': count,
            'max_participants': maximum,
            'seats_left': max(maximum - count, 0) if maximum else None,
        })

    return {'groups': out_groups, 'events': out_events}
