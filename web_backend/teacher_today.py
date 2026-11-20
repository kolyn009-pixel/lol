"""GET /api/teacher/today: one payload for the teacher's main screen (lessons, attention, week, counters)."""
from __future__ import annotations
from datetime import datetime, timedelta
import database
from web_backend import teacher_portal, finance_receipts, teacher_request_center, group_portal

TTL = 15.0
MAX_ITEMS = 3
GROUP_DONE = {'CANCELLED'}


def _short(text, n=80):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= n else text[:n - 1] + '…'


def _lessons(dash, today, tomorrow):
    out = []
    for r in dash['today_lessons']:
        out.append({'id': int(r['id']), 'kind': 'lesson', 'format': 'INDIVIDUAL', 'start_at': r['start_time'], 'end_at': r['end_time'],
                    'title': r.get('name') or '', 'student_name': r.get('name'), 'group_title': None, 'members_count': 1,
                    'subject': r.get('subject'), 'goal': r.get('study_goal'), 'lesson_status': r.get('lesson_status'),
                    'payment_status': r.get('payment_status'), 'price': r.get('price'),
                    'payment_wait_confirmed_at': r.get('payment_wait_confirmed_at'), 'user_id': r.get('user_id')})
    cards = [c for c in group_portal.teacher_schedule_cards(today, tomorrow) if c['kind'] == 'GROUP' and str(c['start_time'])[:10] == today]
    meta = {}
    if cards:
        ids = [int(c['id']) for c in cards]
        conn = database.connect()
        try:
            for m in conn.execute("SELECT l.id,l.price_per_student,g.name,g.subject,g.study_goal FROM group_lessons l JOIN study_groups g ON g.id=l.group_id WHERE l.id IN (%s)" % ','.join('?' * len(ids)), ids).fetchall():
                meta[int(m['id'])] = m
        finally:
            conn.close()
    for c in cards:
        m = meta.get(int(c['id']))
        name = (m['name'] if m else str(c.get('title') or '').lstrip('👥 ')) or ''
        out.append({'id': int(c['id']), 'kind': 'group_lesson', 'format': 'GROUP', 'start_at': c['start_time'], 'end_at': c['end_time'],
                    'title': name, 'student_name': None, 'group_title': name, 'members_count': int(c.get('participants') or 0),
                    'subject': m['subject'] if m else None, 'goal': m['study_goal'] if m else None, 'lesson_status': c.get('status'),
                    'payment_status': None, 'price': m['price_per_student'] if m else None, 'payment_wait_confirmed_at': None, 'user_id': None})
    out.sort(key=lambda x: (str(x['start_at']), x['id']))
    return out


def _week(now):
    start = now.date()
    end = start + timedelta(days=7)
    counts = {(start + timedelta(days=i)).isoformat(): 0 for i in range(7)}
    conn = database.connect()
    try:
        for r in conn.execute("SELECT substr(start_time,1,10) d,COUNT(*) n FROM lessons WHERE start_time>=? AND start_time<? AND lesson_status NOT IN ('CANCELLED','LATE_CANCELLED','REJECTED','SICKNESS') GROUP BY 1", (start.isoformat(), end.isoformat())).fetchall():
            if r['d'] in counts:
                counts[r['d']] += int(r['n'])
        try:
            for r in conn.execute("SELECT substr(start_time,1,10) d,COUNT(*) n FROM group_lessons WHERE start_time>=? AND start_time<? AND status<>'CANCELLED' GROUP BY 1", (start.isoformat(), end.isoformat())).fetchall():
                if r['d'] in counts:
                    counts[r['d']] += int(r['n'])
        except Exception:
            pass
    finally:
        conn.close()
    return [{'date': d, 'lessons_count': n} for d, n in counts.items()]


def _messages():
    conn = database.connect()
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='unified_messages' LIMIT 1").fetchone():
            return 0, []
        total = int(conn.execute("SELECT COUNT(DISTINCT conversation_id) n FROM unified_messages WHERE direction='IN' AND read_at IS NULL").fetchone()['n'] or 0)
        rows = conn.execute("SELECT m.conversation_id,m.student_id,u.name,COUNT(*) n,MAX(m.id) last_id,MAX(m.created_at) last_at FROM unified_messages m LEFT JOIN users u ON u.id=m.student_id WHERE m.direction='IN' AND m.read_at IS NULL GROUP BY m.conversation_id ORDER BY last_id DESC LIMIT ?", (MAX_ITEMS,)).fetchall()
        items = []
        for r in rows:
            body = conn.execute("SELECT body FROM unified_messages WHERE id=?", (r['last_id'],)).fetchone()
            items.append({'id': int(r['conversation_id']), 'title': r['name'] or 'Ученик', 'subtitle': _short(body['body'] if body else '') or f"Новых: {r['n']}", 'link': '/app/teacher.html#messages'})
        return total, items
    finally:
        conn.close()


def build():
    tz, now = teacher_portal._teacher_now()
    today = now.date().isoformat()
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    dash = teacher_portal.dashboard()
    lessons = _lessons(dash, today, tomorrow)

    pend = dash.get('pending_reviews') or []
    hw_total = int(dash['stats'].get('submissions') or len(pend))
    hw_items = [{'id': int(p['submission_id']), 'title': _short(p.get('title') or 'Домашнее задание'), 'subtitle': p.get('name') or '', 'link': '/app/teacher.html#homework'} for p in pend[:MAX_ITEMS]]

    try:
        rc_total = int(finance_receipts.summary().get('waiting') or 0)
        rc_items = [{'id': int(r['receipt_id']), 'title': r.get('name') or 'Ученик', 'subtitle': f"{int(r.get('total_amount') or 0)} ₽", 'link': '/app/teacher.html#finance'} for r in finance_receipts.list_receipts('WAITING', MAX_ITEMS)]
    except Exception as exc:
        print('[teacher-today] receipts unavailable:', type(exc).__name__, exc, flush=True)
        rc_total, rc_items = 0, []

    req = teacher_request_center.list_all(50)
    rq_items = []
    for x in (req.get('lesson_requests') or []):
        rq_items.append({'id': int(x['id']), 'title': x.get('name') or 'Ученик', 'subtitle': f"Запрос урока {str(x.get('start_time') or '')[:16].replace('T', ' ')}", 'link': '/app/teacher.html#requests'})
    for x in (req.get('trials') or []):
        if x.get('status') in {'NEW', 'CONTACTED'}:
            rq_items.append({'id': int(x.get('id') or 0), 'title': str(x.get('name') or x.get('student_name') or 'Пробное занятие'), 'subtitle': 'Пробное занятие', 'link': '/app/teacher.html#requests'})
    for x in (req.get('schedule_groups') or []):
        rq_items.append({'id': int(x['items'][0]['id']) if x.get('items') else 0, 'title': x.get('name') or 'Ученик', 'subtitle': 'Запрос расписания', 'link': '/app/teacher.html#requests'})
    for x in (req.get('group_registrations') or []):
        rq_items.append({'id': int(x.get('id') or 0), 'title': str(x.get('name') or x.get('student_name') or 'Запись в группу'), 'subtitle': 'Запись в группу', 'link': '/app/teacher.html#requests'})
    c = req.get('counts') or {}
    rq_total = int(c.get('group', 0)) + int(c.get('trial', 0)) + int(c.get('lesson', 0)) + int(c.get('schedule_groups', 0))

    msg_total, msg_items = _messages()
    attention = [
        {'kind': 'homework', 'count': hw_total, 'items': hw_items[:MAX_ITEMS]},
        {'kind': 'receipt', 'count': rc_total, 'items': rc_items[:MAX_ITEMS]},
        {'kind': 'request', 'count': rq_total, 'items': rq_items[:MAX_ITEMS]},
        {'kind': 'message', 'count': msg_total, 'items': msg_items[:MAX_ITEMS]},
    ]
    live = [x for x in lessons if x['lesson_status'] not in ('CANCELLED', 'LATE_CANCELLED', 'REJECTED', 'SICKNESS')]
    counters = {'lessons_today': len(live), 'group_lessons_today': sum(1 for x in live if x['kind'] == 'group_lesson'),
                'students': int(dash['stats'].get('students') or 0), 'unpaid_week': dash['stats'].get('expected_week') or 0,
                'homework': hw_total, 'receipts': rc_total, 'requests': rq_total, 'messages': msg_total}
    return {'generated_at': now.isoformat(timespec='seconds'), 'tz': tz, 'lessons': lessons, 'attention': attention, 'week': _week(now), 'counters': counters}


def today(teacher_id=0):
    return teacher_portal._cached(('today', int(teacher_id or 0)), TTL, build)
