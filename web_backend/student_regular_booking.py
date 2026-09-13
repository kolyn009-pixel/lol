"""Student self-service requests for one or several weekly recurring lessons."""
from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import secrets
import database
from web_backend import availability_guard

MAX_WEEKLY=7


def ensure_schema():
    c=database.connect()
    try:
        cols={r['name'] for r in c.execute('PRAGMA table_info(regular_schedules)').fetchall()}
        if 'request_group' not in cols:
            c.execute('ALTER TABLE regular_schedules ADD COLUMN request_group TEXT')
        c.execute('CREATE INDEX IF NOT EXISTS idx_regular_request_group ON regular_schedules(request_group,status)')
        c.commit()
    finally:c.close()


def _program(user_id,program_id):
    for row in database.get_student_programs(int(user_id),active_only=True,approved_only=True):
        if int(row['id'])==int(program_id):return row
    raise PermissionError('program_not_found')


def _teacher_tz():
    return ZoneInfo(str(database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'))


def _inside_working_hours(start,end):
    for row in database.get_effective_working_hours(start.date()):
        s=datetime.fromisoformat(f"{start.date().isoformat()}T{str(row['start_time'])[:5]}:00").replace(tzinfo=start.tzinfo)
        e=datetime.fromisoformat(f"{start.date().isoformat()}T{str(row['end_time'])[:5]}:00").replace(tzinfo=start.tzinfo)
        if s<=start and end<=e:return True
    return False


def create_group(user_id,program_id,selections):
    """Create one logical request containing 1..7 permanent weekly slots."""
    ensure_schema();program=_program(user_id,program_id)
    if not isinstance(selections,list) or not 1<=len(selections)<=MAX_WEEKLY:raise ValueError('invalid_schedule_count')
    tz=_teacher_tz();normalized=[];seen=set()
    for raw in selections:
        if not isinstance(raw,dict):raise ValueError('invalid_schedule_item')
        start=datetime.fromisoformat(str(raw.get('start_time') or ''))
        if start.tzinfo is None:start=start.replace(tzinfo=tz)
        else:start=start.astimezone(tz)
        duration=int(raw.get('duration_minutes') or 60)
        if duration<30 or duration>180 or duration%30:raise ValueError('invalid_duration')
        end=start+timedelta(minutes=duration)
        if start<=datetime.now(tz):raise ValueError('slot_in_past')
        if not _inside_working_hours(start,end):raise ValueError('outside_working_hours')
        key=(start.weekday(),start.strftime('%H:%M'),duration)
        if key in seen:raise ValueError('duplicate_weekly_slot')
        seen.add(key);normalized.append((start,end,duration,key))

    group='RS-'+secrets.token_hex(8).upper();now=database.now_iso();c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        for start,end,duration,key in normalized:
            if availability_guard.conflicts(start.replace(tzinfo=None),end.replace(tzinfo=None),conn=c):raise ValueError('slot_unavailable')
            weekday,start_clock,_=key
            overlap=c.execute("""SELECT 1 FROM regular_schedules WHERE COALESCE(active,1)=1 AND status IN ('PENDING','APPROVED') AND weekday=? AND (? < (substr(start_time,1,2)*60+substr(start_time,4,2)+duration_minutes)) AND ((substr(start_time,1,2)*60+substr(start_time,4,2)) < ?) LIMIT 1""",(weekday,start.hour*60+start.minute,(start.hour*60+start.minute)+duration)).fetchone()
            if overlap:raise ValueError('slot_unavailable')
        ids=[]
        for start,end,duration,key in normalized:
            weekday,start_clock,_=key
            cur=c.execute("""INSERT INTO regular_schedules(user_id,study_goal,subject,weekday,start_time,duration_minutes,active,student_approved,admin_approved,status,request_source,requested_at,created_at,updated_at,request_group) VALUES(?,?,?,?,?,?,0,1,0,'PENDING','STUDENT',?,?,?,?,?)""",(int(user_id),program['study_goal'],program['subject'],weekday,start_clock,duration,now,now,now,group))
            ids.append(int(cur.lastrowid))
        c.commit()
    except Exception:
        c.rollback();raise
    finally:c.close()
    return {'status':'ok','request_group':group,'schedule_request_ids':ids,'weekly_count':len(ids)}
