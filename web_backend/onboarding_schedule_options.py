"""Real weekly schedule options for returning-student onboarding.

Options are generated from teacher working hours, existing recurring schedules and
student timezone. One-off lessons do not permanently block a weekly slot; the final
teacher approval remains authoritative.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import database
from web_backend import student_onboarding

STEP_MINUTES = 30
DURATION_MINUTES = 60
DAY_KEYS = ['MON','TUE','WED','THU','FRI','SAT','SUN']


def _minutes(value):
    h,m=[int(x) for x in str(value)[:5].split(':')]
    return h*60+m


def _recurring_busy(weekday,start_min,end_min):
    c=database.connect()
    try:
        rows=c.execute("""
            SELECT start_time,duration_minutes
            FROM regular_schedules
            WHERE weekday=? AND status IN ('PENDING','APPROVED')
        """,(int(weekday),)).fetchall()
        for r in rows:
            rs=_minutes(r['start_time']);re=rs+int(r['duration_minutes'] or 60)
            if start_min<re and rs<end_min:
                return True
        return False
    finally:
        c.close()


def _closed_by_exception(day,start_min,end_min):
    for raw in database.get_schedule_exceptions(day.isoformat()):
        row=dict(raw)
        if str(row.get('exception_type') or '').upper()!='CLOSED':
            continue
        if not row.get('start_time') and not row.get('end_time'):
            return True
        if not row.get('start_time') or not row.get('end_time'):
            continue
        cs=_minutes(row['start_time']);ce=_minutes(row['end_time'])
        if start_min<ce and cs<end_min:
            return True
    return False


def feed(token):
    if str(database.get_setting('teacher_schedule_booking_paused','0') or '0').lower() in {'1','true','on','yes'}:
        state=student_onboarding.status_payload(token)
        return {'timezone': state.get('timezone'), 'teacher_timezone': str(database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'), 'duration_minutes': DURATION_MINUTES, 'items': [], 'booking_paused': True}
    state=student_onboarding.status_payload(token)
    if state['status'] not in {'REGION_SET','SCHEDULE_SET'}:
        raise ValueError('region_not_set')
    client_tz=ZoneInfo(state['timezone'])
    teacher_tz_name=database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'
    teacher_tz=ZoneInfo(teacher_tz_name)
    now=datetime.now(teacher_tz)
    result=[]
    for offset in range(1,8):
        day=(now+timedelta(days=offset)).date()
        weekday=day.weekday()
        slots=[]
        for hours in database.get_effective_working_hours(day):
            ws=_minutes(hours['start_time']);we=_minutes(hours['end_time']);cur=ws
            while cur+DURATION_MINUTES<=we:
                if not _closed_by_exception(day,cur,cur+DURATION_MINUTES) and not _recurring_busy(weekday,cur,cur+DURATION_MINUTES):
                    h,m=divmod(cur,60)
                    teacher_dt=datetime(day.year,day.month,day.day,h,m,tzinfo=teacher_tz)
                    local_dt=teacher_dt.astimezone(client_tz)
                    slots.append({
                        'weekday':DAY_KEYS[local_dt.weekday()],
                        'time':local_dt.strftime('%H:%M'),
                        'duration_minutes':DURATION_MINUTES,
                        'teacher_weekday':weekday,
                        'teacher_time':f'{h:02d}:{m:02d}',
                        'local_iso':local_dt.isoformat(timespec='minutes'),
                    })
                cur+=STEP_MINUTES
        if slots:
            result.append({
                'date':slots[0]['local_iso'][:10],
                'weekday':DAY_KEYS[datetime.fromisoformat(slots[0]['local_iso']).weekday()],
                'slots':slots,
            })
    return {'timezone':state['timezone'],'teacher_timezone':teacher_tz_name,'duration_minutes':DURATION_MINUTES,'items':result}
