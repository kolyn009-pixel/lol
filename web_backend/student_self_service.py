"""Student self-service facade reusing TutorBot's canonical scheduling rules.

No separate web-only state is introduced: sickness, cancellation and regular
schedule pauses write through the same database functions used by TutorBot.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import database


def _lesson_owned(user_id, lesson_id):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson or int(lesson['user_id']) != int(user_id):
        raise PermissionError('lesson_not_found')
    return lesson


def _schedule_owned(user_id, schedule_id):
    schedule = database.get_regular_schedule(int(schedule_id))
    if not schedule or int(schedule['user_id']) != int(user_id):
        raise PermissionError('schedule_not_found')
    return schedule


def _teacher_day_off_applies(lesson):
    try:
        from web_backend import teacher_day_off_state
        if teacher_day_off_state.is_marked(int(lesson['id'])):return True
    except Exception:
        pass
    start=datetime.fromisoformat(str(lesson['start_time']));end=datetime.fromisoformat(str(lesson['end_time']))
    for row in database.get_schedule_exceptions(start.date().isoformat()):
        item=dict(row)
        if str(item.get('exception_type') or '').upper()!='CLOSED':continue
        if not item.get('start_time') or not item.get('end_time'):return True
        sh,sm=map(int,str(item['start_time'])[:5].split(':'));eh,em=map(int,str(item['end_time'])[:5].split(':'))
        closed_start=start.replace(hour=sh,minute=sm,second=0,microsecond=0);closed_end=start.replace(hour=eh,minute=em,second=0,microsecond=0)
        if start<closed_end and end>closed_start:return True
    return False


def regular_schedules(user_id):
    rows = database.get_regular_schedules(user_id=int(user_id), approved_only=False)
    result = []
    for row in rows:
        item = dict(row)
        result.append({
            'id': int(item['id']), 'subject': item.get('subject'), 'study_goal': item.get('study_goal'),
            'weekday': item.get('weekday'), 'start_time': item.get('start_time'),
            'duration_minutes': item.get('duration_minutes'), 'status': item.get('status'),
            'active': bool(item.get('active')), 'pause_until': item.get('pause_until'),
            'start_date': item.get('start_date'), 'end_date': item.get('end_date'),
        })
    return result


def _validated_pause_until(pause_until):
    if not pause_until: raise ValueError('pause_until_required')
    try: until = date.fromisoformat(str(pause_until))
    except ValueError: raise ValueError('invalid_pause_until') from None
    today = date.today()
    if until < today: raise ValueError('pause_until_in_past')
    if until > today + timedelta(days=180): raise ValueError('pause_too_long')
    return until


def pause_schedule(user_id, schedule_id, pause_until):
    _schedule_owned(user_id, schedule_id); until = _validated_pause_until(pause_until)
    database.pause_regular_schedule(int(schedule_id), until.isoformat())
    return {'status': 'ok', 'schedule_id': int(schedule_id), 'pause_until': until.isoformat()}


def resume_schedule(user_id, schedule_id):
    _schedule_owned(user_id, schedule_id); database.resume_regular_schedule(int(schedule_id))
    return {'status': 'ok', 'schedule_id': int(schedule_id)}


def vacation(user_id, pause_until):
    until = _validated_pause_until(pause_until); schedules = database.get_regular_schedules(user_id=int(user_id), approved_only=False); affected = []
    for row in schedules:
        item = dict(row)
        if not item.get('active'): continue
        if str(item.get('status') or '').upper() in {'REJECTED', 'CANCELLED'}: continue
        sid = int(item['id']); database.pause_regular_schedule(sid, until.isoformat()); affected.append(sid)
    return {'status': 'ok', 'pause_until': until.isoformat(), 'affected_schedule_ids': affected, 'affected_count': len(affected)}


def resume_all(user_id):
    schedules = database.get_regular_schedules(user_id=int(user_id), approved_only=False); affected = []
    for row in schedules:
        item = dict(row)
        if not item.get('active'): continue
        if str(item.get('status') or '').upper() != 'PAUSED' and not item.get('pause_until'): continue
        sid = int(item['id']); database.resume_regular_schedule(sid); affected.append(sid)
    return {'status': 'ok', 'affected_schedule_ids': affected, 'affected_count': len(affected)}


def sickness(user_id, lesson_id, comment=None):
    lesson = _lesson_owned(user_id, lesson_id)
    if str(lesson['lesson_status']).upper() != 'CONFIRMED': raise ValueError('lesson_not_confirmed')
    result = database.request_sickness(int(lesson_id), int(user_id), str(comment or '').strip()[:500])
    return {'status': 'ok', **result}


def cancel_lesson(user_id, lesson_id):
    lesson = _lesson_owned(user_id, lesson_id)
    if str(lesson['lesson_status']).upper() != 'CONFIRMED': raise ValueError('lesson_not_confirmed')
    teacher_day_off=_teacher_day_off_applies(lesson)
    if teacher_day_off:
        from web_backend import teacher_lesson_actions
        result=teacher_lesson_actions.cancel(int(lesson_id),'Выходной преподавателя — ученик выбрал отмену')
        return {'status':'ok','lesson_id':int(lesson_id),'late':False,'teacher_day_off':True,'lesson_status':'CANCELLED','refunded':bool(result.get('refunded')),'integrations':result.get('integrations')}
    late = database.get_hours_until_lesson(lesson) < 2
    updated = database.cancel_lesson_by_student(int(lesson_id), int(user_id), late=late, reason='STUDENT_CANCEL_WEB')
    integrations = None
    try:
        from integrations.lesson_sync import cancel_lesson as cancel_external
        integrations = cancel_external(int(lesson_id))
    except Exception as exc:
        integrations = {'google': {'status': 'error', 'error': str(exc)}, 'telemost': None}
    return {'status': 'ok', 'lesson_id': int(lesson_id), 'late': bool(late),
            'teacher_day_off':False,
            'lesson_status': updated['lesson_status'] if updated else ('LATE_CANCELLED' if late else 'CANCELLED'),
            'integrations': integrations}


def request_reschedule(user_id, lesson_id, reason=None):
    lesson = _lesson_owned(user_id, lesson_id)
    if str(lesson['lesson_status']).upper() != 'CONFIRMED': raise ValueError('lesson_not_confirmed')
    database.create_pending_reschedule(int(lesson_id), str(reason or 'STUDENT_WEB_REQUEST')[:300])
    return {'status': 'ok', 'lesson_id': int(lesson_id), 'request_status': 'PENDING'}


def lesson_actions(user_id, lesson_id):
    lesson = _lesson_owned(user_id, lesson_id); status = str(lesson['lesson_status'] or '').upper()
    if status != 'CONFIRMED': return {'can_cancel': False, 'can_reschedule': False, 'can_sickness': False, 'late_cancel': False, 'teacher_day_off':False}
    teacher_day_off=_teacher_day_off_applies(lesson);hours = database.get_hours_until_lesson(lesson)
    return {'can_cancel': True, 'can_reschedule': True, 'can_sickness': True, 'late_cancel': False if teacher_day_off else hours < 2, 'teacher_day_off':teacher_day_off, 'hours_until': round(float(hours), 2)}
