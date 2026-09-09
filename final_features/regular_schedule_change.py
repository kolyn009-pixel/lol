from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import database

HORIZON_DAYS = 56
ACTIVE_LESSON_STATUSES = ('PENDING','CONFIRMED')


def ensure_schema():
    c = database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS regular_schedule_change_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      regular_schedule_id INTEGER NOT NULL,
      proposed_weekday INTEGER NOT NULL,
      proposed_start_time TEXT NOT NULL,
      proposed_duration_minutes INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING_TEACHER',
      request_source TEXT NOT NULL DEFAULT 'WEB',
      analysis_json TEXT,
      requested_at TEXT NOT NULL,
      approved_by INTEGER,
      approved_at TEXT,
      applied_at TEXT,
      rejected_at TEXT,
      note TEXT,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(regular_schedule_id) REFERENCES regular_schedules(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_regular_change_user_status
      ON regular_schedule_change_requests(user_id,status,requested_at DESC);
    CREATE INDEX IF NOT EXISTS idx_regular_change_schedule_status
      ON regular_schedule_change_requests(regular_schedule_id,status);
    """)
    c.commit(); c.close()


def _schedule(schedule_id):
    c=database.connect();row=c.execute('SELECT * FROM regular_schedules WHERE id=?',(int(schedule_id),)).fetchone();c.close();return row


def schedules_for_student(user_id):
    ensure_schema(); c=database.connect()
    rows=c.execute("""SELECT * FROM regular_schedules
      WHERE user_id=? AND active=1 AND COALESCE(status,'APPROVED') NOT IN ('REJECTED','CANCELLED')
      ORDER BY weekday,start_time,id""",(int(user_id),)).fetchall();c.close()
    return [dict(r) for r in rows]


def _first_weekday_on_or_after(start_day, weekday):
    return start_day + timedelta(days=(int(weekday)-start_day.weekday()) % 7)


def _future_lessons(schedule_id):
    now=datetime.now().isoformat(timespec='seconds');c=database.connect()
    marks=','.join('?' for _ in ACTIVE_LESSON_STATUSES)
    rows=c.execute(f"""SELECT * FROM lessons WHERE regular_schedule_id=? AND start_time>=?
      AND lesson_status IN ({marks}) ORDER BY start_time,id""",(int(schedule_id),now,*ACTIVE_LESSON_STATUSES)).fetchall();c.close();return rows


def analyze(user_id,schedule_id,weekday,start_time,duration_minutes):
    ensure_schema(); schedule=_schedule(schedule_id)
    if not schedule or int(schedule['user_id'])!=int(user_id):raise PermissionError('regular_schedule_not_found')
    weekday=int(weekday);duration=int(duration_minutes)
    if weekday<0 or weekday>6:raise ValueError('invalid_weekday')
    if duration<30 or duration>180 or duration%30:raise ValueError('invalid_duration')
    try:hh,mm=map(int,str(start_time).split(':')[:2]); assert 0<=hh<=23 and 0<=mm<=59
    except Exception:raise ValueError('invalid_start_time') from None
    lessons=_future_lessons(schedule_id); affected_ids=[int(x['id']) for x in lessons]
    base=max(date.today(),datetime.fromisoformat(lessons[0]['start_time']).date() if lessons else date.today())
    first=_first_weekday_on_or_after(base,weekday)
    proposed=[];conflicts=[]
    c=database.connect()
    for i,lesson in enumerate(lessons):
        d=first+timedelta(days=7*i);start=datetime.combine(d,datetime.min.time()).replace(hour=hh,minute=mm);end=start+timedelta(minutes=duration)
        if (start-date.today().__class__.fromisoformat(d.isoformat()) if False else None):pass
        marks=','.join('?' for _ in affected_ids) if affected_ids else 'NULL'
        params=[end.isoformat(),start.isoformat()]
        sql="SELECT l.id,l.user_id,l.start_time,l.end_time,u.name FROM lessons l JOIN users u ON u.id=l.user_id WHERE l.lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS') AND l.start_time < ? AND l.end_time > ?"
        if affected_ids:
            sql+=f" AND l.id NOT IN ({marks})";params.extend(affected_ids)
        hit=c.execute(sql,params).fetchone()
        item={'lesson_id':int(lesson['id']),'from_start':lesson['start_time'],'from_end':lesson['end_time'],'to_start':start.isoformat(),'to_end':end.isoformat()}
        if hit:
            item['conflict']={'lesson_id':int(hit['id']),'student_id':int(hit['user_id']),'student_name':hit['name'],'start_time':hit['start_time'],'end_time':hit['end_time']};conflicts.append(item['conflict'])
        proposed.append(item)
    c.close()
    return {'feasible':not conflicts,'user_id':int(user_id),'regular_schedule_id':int(schedule_id),'weekday':weekday,'start_time':f'{hh:02d}:{mm:02d}','duration_minutes':duration,'affected_lessons':proposed,'conflicts':conflicts,'requires_teacher_approval':True}


def create_request(user_id,schedule_id,weekday,start_time,duration_minutes,source='WEB',note=None):
    analysis=analyze(user_id,schedule_id,weekday,start_time,duration_minutes)
    now=datetime.now().isoformat(timespec='seconds');c=database.connect()
    c.execute("UPDATE regular_schedule_change_requests SET status='SUPERSEDED' WHERE user_id=? AND regular_schedule_id=? AND status IN ('PENDING_TEACHER','APPROVED')",(int(user_id),int(schedule_id)))
    cur=c.execute("""INSERT INTO regular_schedule_change_requests(user_id,regular_schedule_id,proposed_weekday,proposed_start_time,proposed_duration_minutes,status,request_source,analysis_json,requested_at,note)
      VALUES(?,?,?,?,?,'PENDING_TEACHER',?,?,?,?)""",(int(user_id),int(schedule_id),int(weekday),analysis['start_time'],int(duration_minutes),str(source or 'WEB')[:20],json.dumps(analysis,ensure_ascii=False),now,str(note or '')[:500] or None))
    rid=cur.lastrowid;c.commit();c.close();return {'status':'ok','request_id':int(rid),'analysis':analysis}


def get_request(request_id):
    ensure_schema();c=database.connect();r=c.execute('SELECT * FROM regular_schedule_change_requests WHERE id=?',(int(request_id),)).fetchone();c.close()
    if not r:return None
    out=dict(r);out['analysis']=json.loads(out.pop('analysis_json') or '{}');return out


def requests_for_student(user_id,active_only=True):
    ensure_schema();c=database.connect();sql='SELECT * FROM regular_schedule_change_requests WHERE user_id=?';p=[int(user_id)]
    if active_only:sql+=" AND status IN ('PENDING_TEACHER','APPROVED')"
    rows=c.execute(sql+' ORDER BY id DESC',p).fetchall();c.close();out=[]
    for r in rows:
        d=dict(r);d['analysis']=json.loads(d.pop('analysis_json') or '{}');out.append(d)
    return out


def approve(request_id,teacher_id):
    req=get_request(request_id)
    if not req:raise ValueError('request_not_found')
    if req['status']!='PENDING_TEACHER':raise ValueError('request_not_actionable')
    fresh=analyze(req['user_id'],req['regular_schedule_id'],req['proposed_weekday'],req['proposed_start_time'],req['proposed_duration_minutes'])
    if not fresh['feasible']:raise ValueError('schedule_conflicts_detected')
    now=datetime.now().isoformat(timespec='seconds');c=database.connect();c.execute("UPDATE regular_schedule_change_requests SET status='APPROVED',approved_by=?,approved_at=?,analysis_json=? WHERE id=?",(int(teacher_id),now,json.dumps(fresh,ensure_ascii=False),int(request_id)));c.commit();c.close();return {'status':'ok','request_id':int(request_id),'analysis':fresh}


def apply_approved(request_id,teacher_id):
    req=get_request(request_id)
    if not req:raise ValueError('request_not_found')
    if req['status']!='APPROVED' or int(req['approved_by'] or 0)!=int(teacher_id):raise PermissionError('teacher_approval_required')
    fresh=analyze(req['user_id'],req['regular_schedule_id'],req['proposed_weekday'],req['proposed_start_time'],req['proposed_duration_minutes'])
    if not fresh['feasible']:raise ValueError('schedule_changed_since_approval')
    now=datetime.now().isoformat(timespec='seconds');c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute("UPDATE regular_schedules SET weekday=?,start_time=?,duration_minutes=?,updated_at=? WHERE id=? AND user_id=?",(req['proposed_weekday'],req['proposed_start_time'],req['proposed_duration_minutes'],now,req['regular_schedule_id'],req['user_id']))
        for item in fresh['affected_lessons']:
            c.execute("UPDATE lessons SET start_time=?,end_time=?,duration_minutes=?,updated_at=? WHERE id=? AND regular_schedule_id=?",(item['to_start'],item['to_end'],req['proposed_duration_minutes'],now,item['lesson_id'],req['regular_schedule_id']))
        c.execute("UPDATE regular_schedule_change_requests SET status='APPLIED',applied_at=?,analysis_json=? WHERE id=?",(now,json.dumps(fresh,ensure_ascii=False),int(request_id)))
        c.commit()
    except Exception:c.rollback();raise
    finally:c.close()
    return {'status':'ok','request_id':int(request_id),'regular_schedule_id':int(req['regular_schedule_id']),'affected_lesson_ids':[x['lesson_id'] for x in fresh['affected_lessons']],'calendar_sync_required':True}


def reject(request_id,teacher_id=None):
    req=get_request(request_id)
    if not req:raise ValueError('request_not_found')
    now=datetime.now().isoformat(timespec='seconds');c=database.connect();c.execute("UPDATE regular_schedule_change_requests SET status='REJECTED',rejected_at=? WHERE id=? AND status IN ('PENDING_TEACHER','APPROVED')",(now,int(request_id)));c.commit();c.close();return {'status':'ok','request_id':int(request_id)}
