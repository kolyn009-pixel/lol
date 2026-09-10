"""Teacher-facing orchestration for mock exams, seminars and attendance."""
from __future__ import annotations

import database
from web_backend import attendance_tracking, group_portal, open_event_policy, telemost_runtime

PAID_STATUSES={"PAID","WAIVED"}


def _now(): return database.now_iso()


def choices():
    open_event_policy.ensure_schema();c=database.connect()
    students=[dict(r) for r in c.execute("SELECT id,name,grade,main_subject FROM users WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()]
    groups=[dict(r) for r in c.execute("SELECT id,name,subject,study_goal FROM study_groups WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()]
    c.close();return {"students":students,"groups":groups}


def _materialize(event_id):
    eid=int(event_id);ids=open_event_policy.eligible_student_ids(eid);c=database.connect()
    event=c.execute("SELECT price_per_student FROM open_learning_events WHERE id=?",(eid,)).fetchone()
    if not event:c.close();raise ValueError("event_not_found")
    pay='WAIVED' if int(event['price_per_student'] or 0)==0 else 'UNPAID';now=_now()
    for uid in ids:
        c.execute("""INSERT INTO open_event_participants(event_id,user_id,status,payment_status,teacher_decision,access_granted,registered_at,updated_at)
          VALUES(?,?,'REGISTERED',?,'APPROVED',0,?,?)
          ON CONFLICT(event_id,user_id) DO UPDATE SET status='REGISTERED',teacher_decision='APPROVED',updated_at=excluded.updated_at""",(eid,uid,pay,now,now))
    c.commit();c.close();return ids


def create(payload,teacher_id):
    r=open_event_policy.create_event(payload.get('title'),payload.get('starts_at'),int(payload.get('duration_minutes') or 60),event_type=payload.get('event_type'),price_per_student=int(payload.get('price_per_student') or 0),subject=payload.get('subject'),topic=payload.get('topic'),grade_min=payload.get('grade_min'),grade_max=payload.get('grade_max'),max_participants=payload.get('max_participants'),registration_deadline=payload.get('registration_deadline'),group_ids=payload.get('group_ids') or [],student_ids=payload.get('student_ids') or [],board_url=payload.get('board_url'),created_by=int(teacher_id))
    ids=_materialize(r['event_id']);return {**r,'assigned_user_ids':ids}


def list_events(limit=100):
    open_event_policy.ensure_schema();c=database.connect();rows=c.execute("""SELECT e.*,
      (SELECT COUNT(*) FROM open_event_participants p WHERE p.event_id=e.id AND p.status='REGISTERED') participants,
      (SELECT COUNT(*) FROM open_event_participants p WHERE p.event_id=e.id AND p.status='REGISTERED' AND p.payment_status IN ('PAID','WAIVED')) paid_count
      FROM open_learning_events e ORDER BY datetime(e.starts_at) DESC LIMIT ?""",(max(1,min(int(limit),300)),)).fetchall();c.close();return [dict(r) for r in rows]


def detail(event_id):
    open_event_policy.ensure_schema();attendance_tracking.ensure_schema();eid=int(event_id);c=database.connect()
    e=c.execute("SELECT * FROM open_learning_events WHERE id=?",(eid,)).fetchone()
    if not e:c.close();return None
    rows=c.execute("""SELECT p.*,u.name,u.grade FROM open_event_participants p JOIN users u ON u.id=p.user_id
      WHERE p.event_id=? ORDER BY u.name COLLATE NOCASE""",(eid,)).fetchall()
    groups=[dict(r) for r in c.execute("SELECT g.id,g.name FROM open_event_groups x JOIN study_groups g ON g.id=x.group_id WHERE x.event_id=? ORDER BY g.name",(eid,)).fetchall()];c.close()
    participants=[]
    for r in rows:
        item=dict(r);item['attendance']=attendance_tracking.summary('OPEN_EVENT',eid,int(r['user_id']));participants.append(item)
    return {'event':dict(e),'groups':groups,'participants':participants}


def set_payment(event_id,user_id,status):
    status=str(status or '').upper()
    if status not in {'UNPAID','PAID','WAIVED'}:raise ValueError('invalid_event_payment_status')
    c=database.connect();cur=c.execute("UPDATE open_event_participants SET payment_status=?,updated_at=? WHERE event_id=? AND user_id=?",(status,_now(),int(event_id),int(user_id)));c.commit();c.close()
    if not cur.rowcount:raise ValueError('event_participant_not_found')
    return {'status':'ok','payment_status':status}


def attendance(event_id,user_id,event_type,teacher_id,happened_at=None):
    return attendance_tracking.record('OPEN_EVENT',int(event_id),int(user_id),event_type,happened_at=happened_at,source='TEACHER',actor_id=int(teacher_id))


def group_attendance(lesson_id,user_id,event_type,teacher_id,happened_at=None):
    return attendance_tracking.record('GROUP_LESSON',int(lesson_id),int(user_id),event_type,happened_at=happened_at,source='TEACHER',actor_id=int(teacher_id))


def group_roster(lesson_id): return attendance_tracking.roster('GROUP_LESSON',int(lesson_id))


def save_result(event_id,user_id,score,max_score=None,note=None):
    return group_portal.save_open_event_result(int(event_id),int(user_id),score,max_score,note)


def start(event_id):
    eid=int(event_id);r=telemost_runtime.start_open_event(eid);c=database.connect();e=c.execute("SELECT price_per_student FROM open_learning_events WHERE id=?",(eid,)).fetchone()
    price=int(e['price_per_student'] or 0) if e else 0
    c.execute("""UPDATE open_event_participants SET access_granted=CASE
      WHEN teacher_decision='APPROVED' AND (?=0 OR payment_status IN ('PAID','WAIVED')) THEN 1 ELSE 0 END,updated_at=? WHERE event_id=?""",(price,_now(),eid));c.commit();c.close();return r


def finish(event_id):
    eid=int(event_id)
    # Close any participant still marked present at the event finish moment.
    for item in attendance_tracking.roster('OPEN_EVENT',eid):
        if item['attendance']['present']:
            attendance_tracking.record('OPEN_EVENT',eid,int(item['user_id']),'LEAVE',source='SYSTEM')
    return telemost_runtime.finish_open_event(eid)
