"""Stage 10 inbound bridge for messages written in the student Web cabinet.

The Web transport follows the same reception/DND rules as Telegram and VK. The
logical message is written once to the unified store and mirrored to the legacy CRM
only while old admin screens still depend on it. Immediate teacher alerts fan out
to Telegram and VK when reception is open; otherwise the message stays queued.
"""
from __future__ import annotations

import database
from automation import messaging
from core import admin_roles, event_center
from crm_plus import service as crm_service
from vk_adapter import channel_delivery, schema as vk_schema
from web_backend import unified_messaging as um


def _teacher_alert_text(user,body):
    return f"💬 Новое сообщение с сайта от {user['name']}\n\n{body}"


def _notify_teacher_channels(user,body):
    text=_teacher_alert_text(user,body);result={'telegram':0,'vk':0,'failed':0}
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
                result['failed']+=1;print('[stage10] WEB->admin VK error:',repr(exc),flush=True)
    except Exception as exc:
        print('[stage10] WEB admin VK bridge error:',repr(exc),flush=True)
    return result


def receive_web_student_message(user_id,text):
    uid=int(user_id);body=str(text or '').strip()
    if not body:raise ValueError('text_required')
    if len(body)>4000:raise ValueError('text_too_long')
    user=database.get_user(uid)
    if not user or not user['active']:raise ValueError('student_not_found')

    accepting,deliver_at=crm_service.inbound_delivery_state()
    inbox_status='OPEN' if accepting else 'QUEUED'
    source_tid=int(user['telegram_id'] or 0) if 'telegram_id' in user.keys() else 0
    iid=messaging.create_inbox(body,source_tid,student_id=uid,subject='Сообщение от ученика с сайта',status=inbox_status)
    crm_id=crm_service.log_message(
        uid,'IN',body,None,'TEACHER','DELIVERED' if accepting else 'QUEUED',
        None if accepting else deliver_at.isoformat(timespec='seconds'),inbox_id=iid
    )
    mid=um.record_message(
        uid,'IN',body,participant_type='STUDENT',sender_type='STUDENT',sender_id=uid,
        origin_channel='WEB',status='DELIVERED' if accepting else 'QUEUED',
        legacy_source='crm_student_messages',legacy_id=crm_id
    )
    event_center.push(
        'TEACHER_INBOX',f"Сообщение с сайта от {user['name']}",body[:500],
        priority='ACTION',entity_type='teacher_inbox',entity_id=iid,dedupe_key=f'inbox:{iid}'
    )
    notified=_notify_teacher_channels(user,body) if accepting else {'telegram':0,'vk':0,'failed':0}
    return {
        'status':'ok','message_id':mid,'inbox_id':iid,'delivery':'IMMEDIATE' if accepting else 'QUEUED',
        'scheduled_for':None if accepting else deliver_at.isoformat(timespec='seconds'),'teacher_notifications':notified,
    }
