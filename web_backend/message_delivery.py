"""Tracked Stage 10 outbound delivery for teacher replies.

One logical teacher message is stored once in ``unified_messages`` and then gets a
separate delivery row for every transport. Existing CRM history is kept in sync as
a compatibility source until the old admin screens are retired.
"""
from __future__ import annotations

from database import get_user
from crm_plus import service as crm_service
from vk_adapter import channel_delivery
from web_backend import unified_messaging as um


def _enabled_channels(user):
    channels=[]
    if user and user['telegram_id']:channels.append('TELEGRAM')
    if user and channel_delivery.vk_peer(int(user['id'])):channels.append('VK')
    return channels


def send_teacher_reply(user_id,text,channels=None,teacher_id=None):
    uid=int(user_id);body=str(text or '').strip()
    if not body:raise ValueError('text_required')
    if len(body)>4000:raise ValueError('text_too_long')
    user=get_user(uid)
    if not user or not user['active']:raise ValueError('student_not_found')

    requested=[str(x).strip().upper() for x in (channels or _enabled_channels(user))]
    requested=[x for x in requested if x in {'TELEGRAM','VK'}]
    requested=list(dict.fromkeys(requested))
    if not requested:requested=_enabled_channels(user)

    crm_id=crm_service.log_message(uid,'OUT',body,teacher_id,'STUDENT','QUEUED')
    mid=um.record_message(
        uid,'OUT',body,participant_type='STUDENT',sender_type='TEACHER',sender_id=teacher_id,
        origin_channel='WEB',status='QUEUED',legacy_source='crm_student_messages',legacy_id=crm_id
    )

    result={}
    any_sent=False
    for channel in ('TELEGRAM','VK'):
        if channel not in requested:
            recipient=channel_delivery.telegram_chat(uid) if channel=='TELEGRAM' else channel_delivery.vk_peer(uid)
            um.record_delivery(mid,channel,'STUDENT',recipient,'SKIPPED')
            result[channel.lower()]={'status':'SKIPPED'}
            continue
        recipient=channel_delivery.telegram_chat(uid) if channel=='TELEGRAM' else channel_delivery.vk_peer(uid)
        if not recipient:
            um.record_delivery(mid,channel,'STUDENT',None,'SKIPPED',error_code='channel_not_linked')
            result[channel.lower()]={'status':'SKIPPED','error':'channel_not_linked'}
            continue
        um.record_delivery(mid,channel,'STUDENT',recipient,'QUEUED')
        try:
            ok=channel_delivery.send_telegram(uid,body) if channel=='TELEGRAM' else channel_delivery.send_vk(uid,body)
        except Exception as exc:
            ok=False
            print(f'[stage10] {channel} delivery error:',repr(exc),flush=True)
        state='SENT' if ok else 'FAILED'
        um.record_delivery(mid,channel,'STUDENT',recipient,state,error_code=None if ok else 'transport_error')
        result[channel.lower()]={'status':state}
        any_sent=any_sent or bool(ok)

    # Keep the old CRM screen useful during migration without creating another
    # logical message: unified record is already tied to this exact CRM id.
    conn=__import__('database').connect()
    try:
        stamp=crm_service.now().isoformat(timespec='seconds')
        conn.execute("UPDATE crm_student_messages SET status=?,sent_at=CASE WHEN ?='SENT' THEN COALESCE(sent_at,?) ELSE sent_at END,delivered_at=CASE WHEN ?='SENT' THEN COALESCE(delivered_at,?) ELSE delivered_at END WHERE id=?",('SENT' if any_sent else 'FAILED','SENT' if any_sent else 'FAILED',stamp,'SENT' if any_sent else 'FAILED',stamp,crm_id))
        conn.commit()
    finally:conn.close()

    # Logical status means at least one real transport accepted the message;
    # per-channel truth remains available in deliveries.
    conn=__import__('database').connect()
    try:
        conn.execute('UPDATE unified_messages SET status=? WHERE id=?',('SENT' if any_sent else 'FAILED',mid));conn.commit()
    finally:conn.close()
    return {'status':'ok' if any_sent else 'delivery_failed','message_id':mid,'crm_message_id':crm_id,'deliveries':result}
