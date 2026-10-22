"""Add a weekly group session and its concrete lessons as one atomic operation."""
from datetime import datetime, date, time, timedelta
from core.lesson_time import lesson_timezone, schedule_datetime
import database
from web_backend import group_workspace as workspace


def _clock(raw):
    value=datetime.strptime(str(raw),'%H:%M')
    if value.minute%15:raise ValueError('quarter_hour_required')
    return value.hour*60+value.minute


def add(gid, body):
    workspace.ensure_schema()
    weekday=int(body.get('weekday')); duration=int(body.get('duration_minutes',60)); weeks=int(body.get('weeks',8))
    start_minute=_clock(body.get('start_time'))
    if weekday not in range(7):raise ValueError('invalid_weekday')
    if duration<30 or duration>240 or duration%15:raise ValueError('invalid_duration')
    if not 1<=weeks<=26:raise ValueError('invalid_weeks')
    if start_minute+duration>1440:raise ValueError('lesson_crosses_midnight')
    now=datetime.now(lesson_timezone()).replace(tzinfo=None)
    begins=date.fromisoformat(str(body.get('starts_on') or now.date().isoformat()))
    first=begins+timedelta(days=(weekday-begins.weekday())%7)
    start=datetime.combine(first,time(start_minute//60,start_minute%60))
    if start<=now:raise ValueError('start_time_in_past')
    if start>now+timedelta(days=366):raise ValueError('start_date_too_far')
    starts=[start+timedelta(weeks=i) for i in range(weeks)]
    ends_on=starts[-1].date().isoformat(); starts_on=first.isoformat(); clock=start.strftime('%H:%M')
    from web_backend import availability_guard as guard
    with workspace.connection() as c:
        c.execute('BEGIN IMMEDIATE');g=workspace._group(c,gid)
        # The response can be lost after commit; retrying must not add duplicates.
        prior=c.execute('''SELECT s.id FROM group_schedule_slots s JOIN group_slot_windows w ON w.slot_id=s.id
          WHERE s.group_id=? AND s.active=1 AND s.weekday=? AND s.start_time=? AND s.duration_minutes=?
          AND w.starts_on=? AND w.ends_on=?''',(int(gid),weekday,clock,duration,starts_on,ends_on)).fetchone()
        if prior:return {'status':'ok','slot_id':prior['id'],'already_created':True,'lesson_count':weeks,'starts_on':starts_on,'ends_on':ends_on}
        snapshot=guard.availability_snapshot(starts[0],starts[-1]+timedelta(minutes=duration),conn=c)
        concrete=[dict(r) for r in c.execute("SELECT start_time,end_time FROM group_lessons WHERE status IN ('SCHEDULED','STARTED','IN_PROGRESS')")]
        recurring=[dict(r) for r in c.execute('''SELECT s.*,w.starts_on,w.ends_on FROM group_schedule_slots s
          JOIN study_groups g ON g.id=s.group_id LEFT JOIN group_slot_windows w ON w.slot_id=s.id
          WHERE s.active=1 AND g.active=1''')]
        conflicts=[]
        for s in starts:
            end=s+timedelta(minutes=duration)
            busy=bool(guard.conflicts_from_snapshot(s,end,snapshot))
            busy=busy or any(s<schedule_datetime(r['end_time']).replace(tzinfo=None) and schedule_datetime(r['start_time']).replace(tzinfo=None)<end for r in concrete)
            for slot in recurring:
                day=s.date()
                if slot['starts_on'] and day<date.fromisoformat(slot['starts_on']):continue
                if slot['ends_on'] and day>date.fromisoformat(slot['ends_on']):continue
                # Include an overnight slot carried over from the previous day.
                for offset in (0,-1):
                    slot_day=day+timedelta(days=offset)
                    if slot_day.weekday()!=int(slot['weekday']):continue
                    h,m=map(int,str(slot['start_time'])[:5].split(':'))
                    rs=datetime.combine(slot_day,time(h,m));re=rs+timedelta(minutes=int(slot['duration_minutes']))
                    if s<re and rs<end:busy=True
            if busy:conflicts.append(s.strftime('%d.%m.%Y %H:%M'))
        if conflicts:raise ValueError('schedule_conflict:'+','.join(conflicts[:5]))
        stamp=database.now_iso()
        cur=c.execute('''INSERT INTO group_schedule_slots(group_id,weekday,start_time,duration_minutes,active,created_at,updated_at)
           VALUES(?,?,?,?,1,?,?)''',(int(gid),weekday,clock,duration,stamp,stamp));sid=int(cur.lastrowid)
        c.execute('INSERT INTO group_slot_windows VALUES(?,?,?)',(sid,starts_on,ends_on))
        members=c.execute("SELECT user_id FROM group_members WHERE group_id=? AND status='ACTIVE'",(int(gid),)).fetchall()
        for s in starts:
            lesson=c.execute('''INSERT INTO group_lessons(group_id,slot_id,start_time,end_time,price_per_student,status,board_url,created_at,updated_at)
              VALUES(?,?,?,?,?,'SCHEDULED',?,?,?)''',(int(gid),sid,s.isoformat(),(s+timedelta(minutes=duration)).isoformat(),int(g['price_per_lesson']),g['board_url'],stamp,stamp))
            for member in members:
                c.execute('''INSERT INTO group_lesson_participants(lesson_id,user_id,participation_kind,payment_status,access_granted,attendance_status,created_at,updated_at)
                  VALUES(?,?,'PERMANENT','PENDING',0,'EXPECTED',?,?)''',(int(lesson.lastrowid),member['user_id'],stamp,stamp))
    return {'status':'ok','slot_id':sid,'already_created':False,'lesson_count':weeks,'starts_on':starts_on,'ends_on':ends_on}
