"""Teacher-side quick actions for today's lessons."""
from __future__ import annotations
from datetime import datetime,timedelta
import database
from final_features import slot_change
from web_backend import push_events

def _lesson(lesson_id):
    lesson=database.get_lesson(int(lesson_id))
    if not lesson:raise ValueError('lesson_not_found')
    return lesson

def _student_name(user_id):
    row=database.get_user(int(user_id));return str(row['name'] or 'Ученик') if row else 'Ученик'

def warn(lesson_id,text):
    lesson=_lesson(lesson_id);body=str(text or '').strip()
    if not body:raise ValueError('message_required')
    if len(body)>800:raise ValueError('message_too_long')
    result=push_events.student_and_parents(int(lesson['user_id']),'⚠️ Сообщение от преподавателя',body,f'/app/lesson/?id={int(lesson_id)}','/app/parent/',f'teacher-warning-{int(lesson_id)}-{int(datetime.now().timestamp())}',{'type':'teacher_warning','lesson_id':int(lesson_id)},mirror_messengers=True)
    return {'status':'ok','lesson_id':int(lesson_id),'delivery':result}

def remind_payment(lesson_id):
    lesson=_lesson(lesson_id)
    if str(lesson['lesson_status'] or '').upper() not in {'PENDING','CONFIRMED'}:raise ValueError('lesson_not_active')
    if str(lesson['payment_status'] or '').upper()!='AWAITING_PAYMENT':raise ValueError('payment_not_awaiting')
    body='До занятия осталось немного времени. Оплата за занятие ещё не подтверждена. Чтобы подключение прошло без задержки, оплатите занятие заранее.';student_id=int(lesson['user_id'])
    try:
        from core import payment_reminder_routing
        mirror_student=not payment_reminder_routing.has_parent_recipient(student_id)
    except Exception:mirror_student=False
    delivery=push_events.student_and_parents(student_id,'💳 Напоминание об оплате',body,f'/app/lesson/?id={int(lesson_id)}','/app/parent/',f'payment-reminder-teacher-{int(lesson_id)}-{int(datetime.now().timestamp())}',{'type':'reminder','lesson_id':int(lesson_id),'reason':'teacher_payment_reminder'},mirror_messengers=mirror_student)
    return {'status':'ok','lesson_id':int(lesson_id),'payment_status':'AWAITING_PAYMENT','delivery':delivery}

def confirm_payment_wait(lesson_id,teacher_id=None,notify=True):
    lesson=_lesson(lesson_id)
    if str(lesson['payment_status'] or '').upper()!='AWAITING_PAYMENT':raise ValueError('payment_not_awaiting')
    from core import payment_wait_control
    state=payment_wait_control.confirm_wait(int(lesson_id),teacher_id)
    already=bool(state.get('already_confirmed'))
    delivery=None if already or not notify else remind_payment(int(lesson_id))['delivery']
    return {'status':'ok','lesson_id':int(lesson_id),'payment_status':'AWAITING_PAYMENT','payment_wait_confirmed':True,'already_confirmed':already,'state':state,'delivery':delivery}

def cancel(lesson_id,reason=None):
    lesson=_lesson(lesson_id);status=str(lesson['lesson_status'] or '').upper()
    if status in {'CANCELLED','REJECTED','NO_SHOW','LATE_CANCELLED','SICKNESS','COMPLETED'}:
        return {'status':'ok','lesson_id':int(lesson_id),'already_cancelled':True,'refunded':False,'payment_status':str(lesson['payment_status'] or ''),'integrations':None,'delivery':None}
    if status not in {'PENDING','CONFIRMED'}:raise ValueError('lesson_not_cancellable')
    refunded=False
    if bool(lesson['charged']):refunded=bool(database.refund_lesson_balance(int(lesson_id),lesson['package_id']))
    payment_status=str(lesson['payment_status'] or '')
    if refunded:payment_status='REFUNDED'
    elif payment_status in {'AWAITING_PAYMENT','UNPAID'}:payment_status='UNPAID_CANCELLED'
    now=database.now_iso();conn=database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE');conn.execute("UPDATE lessons SET lesson_status='CANCELLED', attendance_status='CANCELLED', payment_status=?, charged=CASE WHEN ? THEN 0 ELSE charged END, updated_at=? WHERE id=?",(payment_status,1 if refunded else 0,now,int(lesson_id)));conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.close()
    try:
        from integrations.lesson_sync import cancel_lesson as cancel_external
        integrations=cancel_external(int(lesson_id))
    except Exception as exc:integrations={'status':'warning','error':type(exc).__name__}
    when=datetime.fromisoformat(str(lesson['start_time'])).strftime('%d.%m в %H:%M');detail=str(reason or '').strip();body=f'Преподаватель отменил занятие {when}. Оплата и минуты не сгорают.'
    if detail:body+=f' Причина: {detail[:300]}'
    delivery=push_events.student_and_parents(int(lesson['user_id']),'🗓️ Занятие отменено преподавателем',body,'/app/?tab=schedule','/app/parent/',f'teacher-cancel-{int(lesson_id)}',{'type':'lesson_cancelled_by_teacher','lesson_id':int(lesson_id)},mirror_messengers=True)
    return {'status':'ok','lesson_id':int(lesson_id),'refunded':refunded,'payment_status':payment_status,'integrations':integrations,'delivery':delivery}

def propose_move(lesson_id,desired_start,teacher_id,note=None):
    lesson=_lesson(lesson_id)
    if str(lesson['lesson_status'] or '').upper()!='CONFIRMED':raise ValueError('lesson_not_confirmed')
    start=datetime.fromisoformat(str(desired_start))
    if start <= datetime.now(start.tzinfo) if start.tzinfo else start <= datetime.now():raise ValueError('slot_in_past')
    duration=int(lesson['duration_minutes'] or 60);end=start+timedelta(minutes=duration);rid=slot_change.create_request(int(lesson['user_id']),int(lesson_id),start,end,requested_by=int(teacher_id) if teacher_id else None,note=str(note or 'TEACHER_WEB_REQUEST')[:300]);req=slot_change.get_request(rid)
    if not req:raise ValueError('reschedule_request_not_found')
    if not req['occupant_lesson_id']:
        moved=slot_change.move_to_requested(rid);slot_change.set_status(rid,'APPLIED',admin_preapproved_by=int(teacher_id),admin_final_by=int(teacher_id));push_events.student_and_parents(int(lesson['user_id']),'🔁 Занятие перенесено',f'Новое время: {start.strftime("%d.%m в %H:%M")}.',f'/app/lesson/?id={int(lesson_id)}','/app/parent/',f'teacher-move-{int(lesson_id)}',{'type':'schedule','lesson_id':int(lesson_id),'reason':'teacher_reschedule'},mirror_messengers=True);return {'status':'applied','request_id':int(rid),'lesson_id':int(lesson_id),'new_start':moved['start_time'] if moved else start.isoformat()}
    slot_change.set_status(rid,'WAITING_OCCUPANT',admin_preapproved_by=int(teacher_id));mode=str(req['exchange_mode'] or 'SWAP').upper();occupant_id=int(req['occupant_student_id'])
    if mode=='SHIFT' and req['occupant_proposed_start']:
        proposed=datetime.fromisoformat(str(req['occupant_proposed_start']));body=f'Чтобы освободить время для другого занятия, преподаватель предлагает сдвинуть твоё занятие на {proposed.strftime("%d.%m в %H:%M")}. Согласиться или отказаться можно в Аделии.'
    else:body='Преподаватель предлагает обмен времени занятий с другим учеником. Согласиться или отказаться можно в Аделии.'
    push_events.student_and_parents(occupant_id,'🔁 Предложение переноса',body,'/app/?tab=schedule','/app/parent/',f'exchange-{int(rid)}',{'type':'schedule_exchange','request_id':int(rid),'mode':mode},mirror_messengers=True);return {'status':'waiting_occupant','request_id':int(rid),'lesson_id':int(lesson_id),'mode':mode,'occupant_student_id':occupant_id,'occupant_proposed_start':req['occupant_proposed_start'],'occupant_proposed_end':req['occupant_proposed_end']}

def finalize_move(request_id,teacher_id):
    rid=int(request_id);tid=int(teacher_id);conn=database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT status,requester_lesson_id,occupant_lesson_id,updated_at FROM slot_change_requests WHERE id=?',(rid,)).fetchone()
        if not row:raise ValueError('request_not_found')
        status=str(row['status'])
        if status=='APPLIED':
            conn.rollback();return {'status':'ok','request_id':rid,'already_applied':True,'lesson_ids':[int(row['requester_lesson_id']),int(row['occupant_lesson_id'])]}
        if status=='APPLYING':
            try:stale=datetime.fromisoformat(str(row['updated_at'])) <= datetime.now()-timedelta(minutes=2)
            except Exception:stale=False
            if not stale:raise ValueError('request_applying')
            cur=conn.execute("UPDATE slot_change_requests SET status='APPLYING',admin_final_by=?,updated_at=? WHERE id=? AND status='APPLYING' AND updated_at=?",(tid,database.now_iso(),rid,row['updated_at']))
            if cur.rowcount!=1:raise ValueError('request_applying')
            conn.commit()
        else:
            if status!='WAITING_FINAL_ADMIN':raise ValueError('request_not_ready')
            cur=conn.execute("UPDATE slot_change_requests SET status='APPLYING',admin_final_by=?,updated_at=? WHERE id=? AND status='WAITING_FINAL_ADMIN'",(tid,database.now_iso(),rid))
            if cur.rowcount!=1:raise ValueError('request_not_ready')
            conn.commit()
    except Exception:
        conn.rollback();raise
    finally:conn.close()
    try:
        first,second=slot_change.swap_times(rid)
    except Exception:
        slot_change.set_status(rid,'WAITING_FINAL_ADMIN')
        raise
    slot_change.set_status(rid,'APPLIED',admin_final_by=tid)
    for item in (first,second):
        if not item:continue
        push_events.student_and_parents(int(item['user_id']),'🔁 Время занятия изменено',f'Новое время: {datetime.fromisoformat(str(item["start_time"])).strftime("%d.%m в %H:%M")}.',f'/app/lesson/?id={int(item["id"])}','/app/parent/',f'exchange-applied-{rid}-{int(item["id"])}',{'type':'schedule','lesson_id':int(item['id']),'request_id':rid},mirror_messengers=True)
    return {'status':'ok','request_id':rid,'already_applied':False,'lesson_ids':[int(first['id']),int(second['id'])]}
