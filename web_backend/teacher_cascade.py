"""Teacher-facing cascade shift analysis and approval facade."""
from __future__ import annotations
import json
import database
from final_features import cascade_shift, slot_change

ACTIVE={'PENDING_ADMIN','WAITING_OCCUPANT','WAITING_FINAL_ADMIN'}

def _student_name(user_id):
    u=database.get_user(int(user_id)) if user_id else None
    return u['name'] if u else 'Ученик'

def _plan_for_request(request_id):
    cascade_shift.ensure_schema();c=database.connect()
    row=c.execute("SELECT * FROM cascade_shift_plans WHERE request_id=? AND status IN ('ANALYZED','APPROVED') ORDER BY id DESC LIMIT 1",(int(request_id),)).fetchone();c.close()
    if not row:return None
    out=dict(row);out['plan']=json.loads(out.pop('plan_json'));return out

def list_requests(limit=50):
    slot_change.ensure_schema();cascade_shift.ensure_schema();c=database.connect()
    rows=c.execute("SELECT * FROM slot_change_requests WHERE status IN ('PENDING_ADMIN','WAITING_OCCUPANT','WAITING_FINAL_ADMIN') ORDER BY id DESC LIMIT ?",(max(1,min(int(limit),100)),)).fetchall();c.close()
    items=[]
    for r in rows:
        lesson=database.get_lesson(int(r['requester_lesson_id']))
        plan=_plan_for_request(int(r['id']))
        items.append({'id':int(r['id']),'status':r['status'],'requester_student_id':int(r['requester_student_id']),'requester_name':_student_name(r['requester_student_id']),'lesson_id':int(r['requester_lesson_id']),'original_start':lesson['start_time'] if lesson else None,'original_end':lesson['end_time'] if lesson else None,'desired_start':r['desired_start'],'desired_end':r['desired_end'],'outside_working_hours':bool(r['outside_working_hours']),'exchange_mode':r['exchange_mode'] if 'exchange_mode' in r.keys() else None,'note':r['note'],'plan':plan})
    return items

def analyze_request(request_id):
    req=slot_change.get_request(int(request_id))
    if not req:raise ValueError('request_not_found')
    if req['status'] not in ACTIVE:raise ValueError('request_not_actionable')
    result=cascade_shift.analyze(int(request_id))
    for move in result.get('moves',[]):move['student_name']=_student_name(move['user_id'])
    return result

def approve_plan(plan_id,teacher_id):
    result=cascade_shift.approve(int(plan_id),int(teacher_id))
    plan=cascade_shift.get_plan(int(plan_id))
    return {**result,'plan':plan['plan'] if plan else None,'next_step':'REQUEST_STUDENT_CONSENTS'}
