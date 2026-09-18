"""Inbound bridge for messages written in the student Adelia chat.

The message body remains inside Adelia. Telegram/VK only notify the teacher that a
new chat message exists, so external messengers are notification transports rather
than copies of the private conversation. Teacher PWA push is delivered through the
same event fanout layer as other Adelia notifications.
"""
from __future__ import annotations

import database
from automation import messaging
from core import admin_roles, event_center
from crm_plus import service as crm_service
from vk_adapter import channel_delivery, schema as vk_schema
from web_backend import unified_messaging as um


def _teacher_alert_text(user,body=None):
    return f"💬 Вам новое сообщение в чате Adelia\nОт: {user['name']}\n\nОткройте раздел «Сообщения» в личном кабинете."


def _notify_teacher_channels(user,body=None):
    text=_teacher_alert_text(user);result={'telegram':0,'vk':0,'failed':0}
    for admin in admin_roles.list_admins():
        if str(admin.get('role') or '').upper() not in {'OWNER','ADMIN'}:continue
        tid=admin.get('telegram_id')
        if not tid:continue
        try:
            if channel_delivery.send_telegram_chat(int(tid),text):result['telegram']+=1
            else:result['failed']+=1
        except Exception as exc:
            result['failed']+=1;print('[stage10] WEB->admin Telegram error:',repr(exc),flush=True)
    try:
        from vk_adapter import app as vk_app
        for peer in vk_schema.get_admin_external_ids('VK'):
            try:
                vk_app.send(int(peer),text,linked=True,mode='teacher');result['vk']+=1
            except Exception as exc:
                result['failed']+=1;print('[stage10] WEB admin VK bridge error:',repr(exc),flush=True)
    except Exception as exc:
        print('[stage10] WEB admin VK bridge error:',repr(exc),flush=True)
    return result


def _notify_teacher_push(user,inbox_id):
    try:
        from web_backend import push_events
        name=str(user['name'] or 'Ученик')
        return push_events.teachers(
            '💬 Новое сообщение',
            f'{name} написал в чате Аделии.',
            '/teacher/',
            f'teacher-message-{int(inbox_id)}',
            {'type':'message','inbox_id':int(inbox_id),'user_id':int(user['id'])},
        )
    except Exception as exc:
        print('[stage10] WEB teacher push error:',type(exc).__name__,repr(exc),flush=True)
        return {'status':'failed','sent':0,'failed':1}


def receive_web_student_message(user_id,text,attachment=None):
    uid=int(user_id);body=str(text or '').strip()
    if not body and not attachment:raise ValueError('text_required')
    if len(body)>4000:raise ValueError('text_too_long')
    user=database.get_user(uid)
    if not user or not user['active']:raise ValueError('student_not_found')

    accepting,deliver_at=crm_service.inbound_delivery_state()
    inbox_status='OPEN' if accepting else 'QUEUED'
    source_tid=int(user['telegram_id'] or 0) if 'telegram_id' in user.keys() else 0
    iid=messaging.create_inbox(body,source_tid,student_id=uid,subject='Сообщение ученика в Adelia',status=inbox_status)
    crm_id=crm_service.log_message(
        uid,'IN',body,None,'TEACHER','DELIVERED' if accepting else 'QUEUED',
        None if accepting else deliver_at.isoformat(timespec='seconds'),inbox_id=iid
    )
    mid=um.record_message(
        uid,'IN',body,participant_type='STUDENT',sender_type='STUDENT',sender_id=uid,
        origin_channel='WEB',content_type=str((attachment or {}).get('kind') or 'TEXT').upper(),attachment=attachment,status='DELIVERED' if accepting else 'QUEUED',
        legacy_source='crm_student_messages',legacy_id=crm_id
    )
    event_center.push(
        'TEACHER_INBOX',f"Новое сообщение в Adelia от {user['name']}",'Откройте чат Adelia, чтобы прочитать сообщение.',
        priority='ACTION',entity_type='teacher_inbox',entity_id=iid,dedupe_key=f'inbox:{iid}'
    )
    notified=_notify_teacher_channels(user) if accepting else {'telegram':0,'vk':0,'failed':0}
    push=_notify_teacher_push(user,iid)
    return {
        'status':'ok','message_id':mid,'inbox_id':iid,'delivery':'IMMEDIATE' if accepting else 'QUEUED',
        'scheduled_for':None if accepting else deliver_at.isoformat(timespec='seconds'),
        'teacher_notifications':notified,'teacher_push':push,
    }
