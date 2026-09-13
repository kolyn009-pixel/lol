"""One-off and trial student booking facade using TutorBot's canonical schedule data."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import database
from web_backend import availability_guard

STEP_MINUTES = 30
DEFAULT_DURATION = 60


def _program_owned(user_id, program_id):
    rows = database.get_student_programs(int(user_id), active_only=True, approved_only=True)
    for row in rows:
        if int(row['id']) == int(program_id):
            return row
    raise PermissionError('program_not_found')


def programs(user_id):
    user = database.get_user(int(user_id))
    if not user:
        raise PermissionError('student_not_found')
    result = []
    for row in database.get_student_programs(int(user_id), active_only=True, approved_only=True):
        rate = row['custom_hourly_rate'] or database.get_default_rate(row['study_goal'], row['subject'], user['grade'])
        result.append({
            'id': int(row['id']),
            'study_goal': row['study_goal'],
            'subject': row['subject'],
            'hourly_rate': int(rate or 0),
            'duration_minutes': DEFAULT_DURATION,
        })
    return result


def _has_paid_booking(user_id):
    conn = database.connect()
    row = conn.execute("""
        SELECT 1 FROM lessons
        WHERE user_id=? AND COALESCE(is_trial,0)=0
          AND lesson_status NOT IN ('REJECTED','CANCELLED')
        LIMIT 1
    """, (int(user_id),)).fetchone()
    conn.close()
    return bool(row)


def trial_status(user_id):
    user = database.get_user(int(user_id))
    if not user:
        raise PermissionError('student_not_found')
    paid_started = _has_paid_booking(user_id)
    used = bool(user['trial_used'])
    return {
        'available': not used and not paid_started,
        'trial_used': used,
        'paid_booking_started': paid_started,
        'duration_minutes': DEFAULT_DURATION,
    }


def free_slots(user_id, program_id, days=14, duration_minutes=DEFAULT_DURATION):
    """Return free student-booking slots using one collision snapshot per request."""
    _program_owned(user_id, program_id)
    duration = int(duration_minutes or DEFAULT_DURATION)
    if duration < 30 or duration > 180 or duration % 30:
        raise ValueError('invalid_duration')
    span_days = max(1, min(int(days), 31))
    today = date.today()
    now = datetime.now()
    range_start = datetime.combine(today, datetime.min.time())
    range_end = range_start + timedelta(days=span_days + 1)
    snapshot = availability_guard.availability_snapshot(range_start, range_end)
    out = []
    for offset in range(span_days):
        day = today + timedelta(days=offset)
        values = []
        for row in database.get_effective_working_hours(day):
            start = datetime.fromisoformat(f"{day.isoformat()}T{row['start_time']}:00")
            end = datetime.fromisoformat(f"{day.isoformat()}T{row['end_time']}:00")
            cur = start
            while cur + timedelta(minutes=duration) <= end:
                finish = cur + timedelta(minutes=duration)
                if cur > now and availability_guard.is_available_from_snapshot(cur, finish, snapshot):
                    values.append({'start_time': cur.isoformat(), 'end_time': finish.isoformat(), 'label': cur.strftime('%H:%M')})
                cur += timedelta(minutes=STEP_MINUTES)
        if values:
            out.append({'date': day.isoformat(), 'slots': values})
    return out


def _request(user_id, program_id, start_time, duration_minutes, is_trial):
    program = _program_owned(user_id, program_id)
    user = database.get_user(int(user_id))
    if not user:
        raise PermissionError('student_not_found')
    if is_trial:
        status = trial_status(user_id)
        if not status['available']:
            raise ValueError('trial_unavailable')
    duration = int(duration_minutes or DEFAULT_DURATION)
    if duration < 30 or duration > 180 or duration % 30:
        raise ValueError('invalid_duration')
    start = datetime.fromisoformat(str(start_time))
    if start <= datetime.now():
        raise ValueError('slot_in_past')
    end = start + timedelta(minutes=duration)
    # Keep an independent fresh check before creating the request. The list shown
    # to the student is only a read model and may be stale by the time they click.
    availability_guard.assert_available(start, end)
    allowed = False
    for day in free_slots(user_id, program_id, days=31, duration_minutes=duration):
        if any(s['start_time'] == start.isoformat() for s in day['slots']):
            allowed = True
            break
    if not allowed:
        raise ValueError('slot_unavailable')
    if database.has_student_lesson_on_date(int(user_id), start.date()):
        raise ValueError('student_already_has_lesson_that_day')
    hourly_rate = program['custom_hourly_rate'] or database.get_default_rate(program['study_goal'], program['subject'], user['grade'])
    price = 0 if is_trial else int(round(int(hourly_rate or 0) * duration / 60))
    lesson_id = database.create_lesson_request(
        user_id=int(user_id),
        program_id=int(program_id),
        study_goal=program['study_goal'],
        subject=program['subject'],
        start_time=start.isoformat(),
        end_time=end.isoformat(),
        duration_minutes=duration,
        hourly_rate=int(hourly_rate or 0),
        price=price,
        is_trial=bool(is_trial),
    )
    return {'status': 'ok', 'lesson_id': int(lesson_id), 'price': price, 'is_trial': bool(is_trial), 'start_time': start.isoformat(), 'end_time': end.isoformat()}


def request_one_off(user_id, program_id, start_time, duration_minutes=DEFAULT_DURATION):
    return _request(user_id, program_id, start_time, duration_minutes, False)


def request_trial(user_id, program_id, start_time, duration_minutes=DEFAULT_DURATION):
    return _request(user_id, program_id, start_time, duration_minutes, True)


def cancel_pending(user_id, lesson_id):
    database.cancel_pending_request(int(lesson_id), int(user_id))
    return {'status': 'ok', 'lesson_id': int(lesson_id)}
