from __future__ import annotations

from datetime import datetime, timedelta
import json
import database
from final_features import slot_change

MAX_CASCADE = 6
STEP_MINUTES = 30


def ensure_schema():
    c = database.connect()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS cascade_shift_plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      request_id INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'ANALYZED',
      plan_json TEXT NOT NULL,
      analyzed_at TEXT NOT NULL,
      approved_by INTEGER,
      approved_at TEXT,
      applied_at TEXT,
      invalidated_reason TEXT,
      FOREIGN KEY(request_id) REFERENCES slot_change_requests(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cascade_shift_request_active
      ON cascade_shift_plans(request_id, status);
    """)
    c.commit(); c.close()


def _dt(v): return v if isinstance(v, datetime) else datetime.fromisoformat(str(v))

def _lesson_duration(row): return _dt(row['end_time']) - _dt(row['start_time'])

def _active_lessons_for_day(day):
    start = datetime.combine(day, datetime.min.time()).isoformat()
    end = (datetime.combine(day, datetime.min.time()) + timedelta(days=1)).isoformat()
    c = database.connect()
    rows = c.execute("""
      SELECT * FROM lessons
      WHERE lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
        AND start_time < ? AND end_time > ?
      ORDER BY start_time,id
    """, (end, start)).fetchall()
    c.close(); return rows


def analyze(request_id):
    """Build a no-write cascade proposal. Never changes lesson times."""
    ensure_schema(); slot_change.ensure_schema()
    req = slot_change.get_request(int(request_id))
    if not req: raise ValueError('request_not_found')
    requester = database.get_lesson(int(req['requester_lesson_id']))
    if not requester: raise ValueError('requester_lesson_not_found')
    desired_start, desired_end = _dt(req['desired_start']), _dt(req['desired_end'])
    day_lessons = _active_lessons_for_day(desired_start.date())
    by_id = {int(x['id']): x for x in day_lessons}
    moving = [{'lesson_id': int(requester['id']), 'user_id': int(requester['user_id']), 'from_start': requester['start_time'], 'from_end': requester['end_time'], 'to_start': desired_start.isoformat(), 'to_end': desired_end.isoformat(), 'role': 'requester'}]
    occupied_ids = {int(requester['id'])}
    cursor_end = desired_end

    for _ in range(MAX_CASCADE):
        conflict = None
        for row in day_lessons:
            lid = int(row['id'])
            if lid in occupied_ids: continue
            rs, re = _dt(row['start_time']), _dt(row['end_time'])
            if rs < cursor_end and re > desired_start:
                conflict = row; break
        if conflict is None: break
        occupied_ids.add(int(conflict['id']))
        duration = _lesson_duration(conflict)
        proposed_start = cursor_end
        proposed_end = proposed_start + duration
        if proposed_start.date() != desired_start.date() or proposed_end.date() != desired_start.date():
            return _save_plan(req, moving, False, 'cascade_crosses_day')
        if not slot_change.is_inside_working_hours(proposed_start, proposed_end):
            return _save_plan(req, moving, False, 'outside_working_hours')
        third = slot_change.find_occupant(proposed_start, proposed_end, exclude_lesson_ids=list(occupied_ids))
        moving.append({'lesson_id': int(conflict['id']), 'user_id': int(conflict['user_id']), 'from_start': conflict['start_time'], 'from_end': conflict['end_time'], 'to_start': proposed_start.isoformat(), 'to_end': proposed_end.isoformat(), 'role': 'displaced'})
        cursor_end = proposed_end
        if third is None: break
        # Loop continues; the next conflicting lesson is shifted after the newly moved one.
        desired_start = proposed_start
    else:
        return _save_plan(req, moving, False, 'cascade_too_long')

    return _save_plan(req, moving, True, None)


def _save_plan(req, moves, feasible, reason):
    payload = {'request_id': int(req['id']), 'feasible': bool(feasible), 'reason': reason, 'moves': moves, 'requires_teacher_approval': True, 'student_consents_required': [m['user_id'] for m in moves if m['role'] == 'displaced']}
    now = datetime.now().isoformat(timespec='seconds')
    c = database.connect()
    c.execute("UPDATE cascade_shift_plans SET status='SUPERSEDED',invalidated_reason='reanalyzed' WHERE request_id=? AND status IN ('ANALYZED','APPROVED')", (int(req['id']),))
    cur = c.execute("INSERT INTO cascade_shift_plans(request_id,status,plan_json,analyzed_at,invalidated_reason) VALUES(?,?,?,?,?)", (int(req['id']), 'ANALYZED', json.dumps(payload, ensure_ascii=False), now, reason))
    pid = cur.lastrowid; c.commit(); c.close()
    return {'plan_id': int(pid), **payload}


def get_plan(plan_id):
    ensure_schema(); c=database.connect(); row=c.execute('SELECT * FROM cascade_shift_plans WHERE id=?',(int(plan_id),)).fetchone(); c.close()
    if not row: return None
    out=dict(row); out['plan']=json.loads(out.pop('plan_json')); return out


def approve(plan_id, teacher_id):
    """Teacher approval only. Still does not modify lessons."""
    plan = get_plan(plan_id)
    if not plan: raise ValueError('plan_not_found')
    if plan['status'] != 'ANALYZED': raise ValueError('plan_not_actionable')
    if not plan['plan'].get('feasible'): raise ValueError('plan_not_feasible')
    now=datetime.now().isoformat(timespec='seconds'); c=database.connect(); c.execute("UPDATE cascade_shift_plans SET status='APPROVED',approved_by=?,approved_at=? WHERE id=?",(int(teacher_id),now,int(plan_id))); c.commit(); c.close()
    return {'status':'ok','plan_id':int(plan_id),'plan_status':'APPROVED'}


def apply_approved(plan_id, teacher_id):
    """Apply atomically only after explicit teacher approval and fresh conflict validation."""
    plan = get_plan(plan_id)
    if not plan: raise ValueError('plan_not_found')
    if plan['status'] != 'APPROVED' or int(plan['approved_by'] or 0) != int(teacher_id): raise PermissionError('teacher_approval_required')
    moves = plan['plan'].get('moves') or []
    ids = [int(m['lesson_id']) for m in moves]
    for m in moves:
        lesson = database.get_lesson(int(m['lesson_id']))
        if not lesson or lesson['lesson_status'] != 'CONFIRMED': raise ValueError('lesson_state_changed')
        if lesson['start_time'] != m['from_start'] or lesson['end_time'] != m['from_end']: raise ValueError('schedule_changed_since_analysis')
        start,end=_dt(m['to_start']),_dt(m['to_end'])
        if not slot_change.is_inside_working_hours(start,end): raise ValueError('outside_working_hours')
        if slot_change.find_occupant(start,end,exclude_lesson_ids=ids): raise ValueError('new_conflict_detected')
    c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE'); now=datetime.now().isoformat(timespec='seconds')
        for m in moves:
            c.execute('UPDATE lessons SET start_time=?,end_time=?,updated_at=? WHERE id=?',(m['to_start'],m['to_end'],now,int(m['lesson_id'])))
        c.execute("UPDATE cascade_shift_plans SET status='APPLIED',applied_at=? WHERE id=?",(now,int(plan_id)))
        c.execute("UPDATE slot_change_requests SET status='APPLIED',admin_final_by=?,resolved_at=?,updated_at=? WHERE id=?",(int(teacher_id),now,now,int(plan['request_id'])))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:c.close()
    return {'status':'ok','plan_id':int(plan_id),'moved_lessons':len(moves)}
