"""Web facade for TutorBot's canonical slot-change / exchange workflow."""
from __future__ import annotations
from datetime import datetime, timedelta
import database
from final_features import slot_change
from web_backend.student_booking import free_slots
ACTIVE_REQUESTS={'PENDING_ADMIN','WAITING_OCCUPANT','WAITING_FINAL_ADMIN'}

def _lesson_owned(user_id,lesson_id):
    lesson=database.get_lesson(int(lesson_id))
    if not lesson or int(lesson['user_id'])!=int(user_id):raise PermissionError('lesson_not_found')
    if str(lesson['lesson_status'] or '').upper()!='CONFIRMED':raise ValueError('lesson_not_confirmed')
    return lesson

def free_slots_for_lesson(user_id,lesson_id,days=14):
    lesson=_lesson_owned(user_id,lesson_id);program_id=lesson['program_id']
    if not program_id:raise ValueError('lesson_program_missing')
    return free_slots(int(user_id),int(program_id),days=int(days),duration_minutes=int(lesson['duration_minutes'] or 60))

def _conflict_preview(req):
    if not req or not req['occupant_lesson_id']:return None
    lesson=database.get_lesson(int(req['occupant_lesson_id']))
    if not lesson:return None
    mode=str(req['exchange_mode'] or 'SWAP').upper()
    out={'mode':mode,'occupant_lesson_id':int(req['occupant_lesson_id']),'occupant_original_start':lesson['start_time'],'occupant_original_end':lesson['end_time']}
    if mode=='SHIFT' and req['occupant_proposed_start'] and req['occupant_proposed_end']:
        out.update({'occupant_proposed_start':req['occupant_proposed_start'],'occupant_proposed_end':req['occupant_proposed_end'],'message':'Выбранное время пересекается с другим занятием. Аделия нашла вариант сдвинуть следующее занятие, не меняя его длительность.'})
    else:out['message']='Выбранное время занято. После предварительного одобрения преподавателя Аделия предложит второму ученику обмен временем.'
    return out

def create_request(user_id,lesson_id,desired_start,note=None):
    lesson=_lesson_owned(user_id,lesson_id);start=datetime.fromisoformat(str(desired_start))
    if start<=datetime.now():raise ValueError('slot_in_past')
    duration=int(lesson['duration_minutes'] or 60);end=start+timedelta(minutes=duration)
    for req in slot_change.requests_for_student(int(user_id),active_only=True):
        if int(req['requester_lesson_id'])==int(lesson_id):raise ValueError('active_reschedule_exists')
    request_id=slot_change.create_request(int(user_id),int(lesson_id),start,end,requested_by=None,note=str(note or 'STUDENT_WEB_REQUEST')[:300]);req=slot_change.get_request(request_id)
    return {'status':'ok','request_id':int(request_id),'request_status':req['status'],'desired_start':req['desired_start'],'desired_end':req['desired_end'],'outside_working_hours':bool(req['outside_working_hours']),'occupied':bool(req['occupant_lesson_id']),'exchange_mode':req['exchange_mode'],'conflict_preview':_conflict_preview(req)}

def outgoing(user_id):return [_serialize_request(row,'requester') for row in slot_change.requests_for_student(int(user_id),active_only=True)]

def incoming(user_id):
    slot_change.ensure_schema();c=database.connect()
    try:rows=c.execute("SELECT * FROM slot_change_requests WHERE occupant_student_id=? AND status='WAITING_OCCUPANT' ORDER BY id DESC",(int(user_id),)).fetchall()
    finally:c.close()
    return [_serialize_request(row,'occupant') for row in rows]

def respond_to_exchange(user_id,request_id,accepted):
    req=slot_change.get_request(int(request_id))
    if not req or int(req['occupant_student_id'] or 0)!=int(user_id):raise PermissionError('exchange_not_found')
    if req['status']!='WAITING_OCCUPANT':raise ValueError('exchange_not_actionable')
    if accepted:
        slot_change.set_status(int(request_id),'WAITING_FINAL_ADMIN',occupant_response='ACCEPTED')
        try:
            from web_backend import push_events
            mode=str(req['exchange_mode'] or 'SWAP').upper()
            label='сдвиг другого занятия' if mode=='SHIFT' else 'обмен временем'
            push_events.teachers('🔁 Перенос готов к подтверждению',f'Второй ученик согласился на {label}. Заявка #{int(request_id)} ждёт финального подтверждения преподавателя.','/teacher/',f'exchange-final-{int(request_id)}',{'type':'schedule_exchange_final','request_id':int(request_id),'mode':mode})
        except Exception:pass
        return {'status':'ok','request_status':'WAITING_FINAL_ADMIN'}
    slot_change.set_status(int(request_id),'DECLINED',occupant_response='DECLINED')
    try:
        from web_backend import push_events
        requester_id=int(req['requester_student_id'])
        push_events.student_and_parents(requester_id,'🔁 Перенос не согласован','Другой ученик не смог согласовать изменение времени. Твоё текущее занятие осталось на прежнем месте. Можно выбрать другой слот или предложить другое время.','/app/?tab=schedule','/app/parent/',f'exchange-declined-{int(request_id)}',{'type':'schedule_exchange_declined','request_id':int(request_id)},mirror_messengers=True)
        push_events.teachers('🔁 Перенос отклонён',f'Второй ученик отказался от изменения времени по заявке #{int(request_id)}. Занятия остались без изменений.','/teacher/',f'exchange-declined-teacher-{int(request_id)}',{'type':'schedule_exchange_declined','request_id':int(request_id)})
    except Exception:pass
    return {'status':'ok','request_status':'DECLINED'}

def cancel_request(user_id,request_id):
    req=slot_change.get_request(int(request_id))
    if not req or int(req['requester_student_id'])!=int(user_id):raise PermissionError('request_not_found')
    previous=str(req['status'])
    if previous not in ACTIVE_REQUESTS:raise ValueError('request_not_actionable')
    slot_change.set_status(int(request_id),'CANCELLED')
    try:
        from web_backend import push_events
        if req['occupant_student_id'] and previous in {'WAITING_OCCUPANT','WAITING_FINAL_ADMIN'}:
            push_events.student_and_parents(int(req['occupant_student_id']),'🔁 Предложение переноса отменено','Другой ученик отменил свою заявку на изменение времени. Твоё занятие остаётся на прежнем месте, никаких действий не требуется.','/app/?tab=schedule','/app/parent/',f'exchange-cancelled-{int(request_id)}',{'type':'schedule_exchange_cancelled','request_id':int(request_id)},mirror_messengers=True)
        if previous in {'WAITING_OCCUPANT','WAITING_FINAL_ADMIN'}:
            push_events.teachers('🔁 Заявка на перенос отменена',f'Инициатор отменил заявку #{int(request_id)}. Все занятия остаются на прежних местах.','/teacher/',f'exchange-cancelled-teacher-{int(request_id)}',{'type':'schedule_exchange_cancelled','request_id':int(request_id)})
    except Exception:pass
    return {'status':'ok','request_status':'CANCELLED','previous_status':previous}

def _serialize_request(req,perspective):
    original=database.get_lesson(int(req['requester_lesson_id']))
    result={'id':int(req['id']),'perspective':perspective,'status':req['status'],'desired_start':req['desired_start'],'desired_end':req['desired_end'],'outside_working_hours':bool(req['outside_working_hours']),'is_exchange':bool(req['occupant_lesson_id']),'exchange_mode':req['exchange_mode'],'original_start':original['start_time'] if original else None,'original_end':original['end_time'] if original else None,'note':req['note'],'conflict_preview':_conflict_preview(req)}
    if perspective=='occupant':
        if str(req['exchange_mode'] or '').upper()=='SHIFT':result.update({'proposal_start':req['occupant_proposed_start'],'proposal_end':req['occupant_proposed_end']})
        else:result.update({'proposal_start':result['original_start'],'proposal_end':result['original_end']})
    return result
