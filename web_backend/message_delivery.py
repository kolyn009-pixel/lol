"""Adelia-first outbound messaging.

The Web/Adelia conversation is the source of truth. A teacher message is stored in
``unified_messages`` first and is immediately visible in the student's Adelia chat.
Telegram and VK are optional secondary transports that can be triggered explicitly
for a new or already-existing message.
"""
from __future__ import annotations

import database
from database import get_user
from crm_plus import service as crm_service
from vk_adapter import channel_delivery
from web_backend import unified_messaging as um
from web_backend import message_media


EXTERNAL_CHANNELS={'TELEGRAM','VK'}


def _enabled_channels(user):
    channels=[]
    if user and user['telegram_id']:channels.append('TELEGRAM')
    if user and channel_delivery.vk_peer(int(user['id'])):channels.append('VK')
    return channels


def _normalize_channels(channels):
    requested=[str(x).strip().upper() for x in (channels or [])]
    requested=[x for x in requested if x in EXTERNAL_CHANNELS]
    return list(dict.fromkeys(requested))


def _deliver_existing(mid,uid,body,channels,attachment=None):
    requested=_normalize_channels(channels);result={};any_sent=False
    user=get_user(int(uid))
    if not user or not user['active']:raise ValueError('student_not_found')
    for channel in requested:
        recipient=channel_delivery.telegram_chat(uid) if channel=='TELEGRAM' else channel_delivery.vk_peer(uid)
        if not recipient:
            um.record_delivery(mid,channel,'STUDENT',None,'SKIPPED',error_code='channel_not_linked')
            result[channel.lower()]={'status':'SKIPPED','error':'channel_not_linked'}
            continue
        um.record_delivery(mid,channel,'STUDENT',recipient,'QUEUED')
        try:
            media=message_media.attachment_items(attachment)
            if media:
                from vk_adapter.attachment_bridge import telegram_send_bytes,vk_send_bytes
                ok=True
                for item in media:
                    meta,data=message_media.read(item.get('token'))
                    if channel=='TELEGRAM':
                        sent=telegram_send_bytes(int(recipient),data,meta['name'],body,meta.get('kind')=='photo',meta.get('mime'))
                    else:
                        sent=vk_send_bytes(int(recipient),data,meta['name'],body,meta.get('kind')=='photo',meta.get('mime'))
                    ok=ok and bool(sent)
            else:
                ok=channel_delivery.send_telegram(uid,body) if channel=='TELEGRAM' else channel_delivery.send_vk(uid,body)
        except Exception as exc:
            ok=False
            print(f'[stage10] {channel} delivery error:',repr(exc),flush=True)
        state='SENT' if ok else 'FAILED'
        um.record_delivery(mid,channel,'STUDENT',recipient,state,error_code=None if ok else 'transport_error')
        result[channel.lower()]={'status':state}
        any_sent=any_sent or bool(ok)
    return result,any_sent


def send_teacher_reply(user_id,text,channels=None,teacher_id=None,attachment=None):
    """Create an Adelia chat message; external fan-out is opt-in only."""
    uid=int(user_id);body=str(text or '').strip()
    if not body and not attachment:raise ValueError('text_required')
    if len(body)>4000:raise ValueError('text_too_long')
    user=get_user(uid)
    if not user or not user['active']:raise ValueError('student_not_found')

    requested=_normalize_channels(channels)
    crm_id=crm_service.log_message(uid,'OUT',body,teacher_id,'STUDENT','SENT')
    mid=um.record_message(
        uid,'OUT',body,participant_type='STUDENT',sender_type='TEACHER',sender_id=teacher_id,
        origin_channel='WEB',content_type=str((attachment or {}).get('kind') or 'TEXT').upper(),attachment=attachment,status='SENT',legacy_source='crm_student_messages',legacy_id=crm_id
    )

    # WEB represents visibility in the Adelia chat itself.
    um.record_delivery(mid,'WEB','STUDENT',uid,'DELIVERED')
    result,any_external=_deliver_existing(mid,uid,body,requested,attachment)

    conn=database.connect()
    try:
        stamp=crm_service.now().isoformat(timespec='seconds')
        conn.execute("UPDATE crm_student_messages SET status='SENT',sent_at=COALESCE(sent_at,?),delivered_at=COALESCE(delivered_at,?) WHERE id=?",(stamp,stamp,crm_id))
        conn.execute("UPDATE unified_messages SET status='SENT' WHERE id=?",(mid,))
        conn.commit()
    finally:conn.close()

    return {
        'status':'ok','message_id':mid,'crm_message_id':crm_id,
        'adelia_status':'DELIVERED','external_sent':any_external,'deliveries':result,
    }


def send_existing_message_channels(message_id,channels):
    """Explicitly send a teacher's existing Adelia message to Telegram/VK."""
    mid=int(message_id);requested=_normalize_channels(channels)
    if not requested:raise ValueError('channels_required')
    um.ensure_tables();conn=database.connect()
    try:
        row=conn.execute("SELECT id,student_id,direction,sender_type,participant_type,body,attachment_json FROM unified_messages WHERE id=? LIMIT 1",(mid,)).fetchone()
    finally:conn.close()
    if not row:raise ValueError('message_not_found')
    if str(row['direction']).upper()!='OUT' or str(row['sender_type']).upper()!='TEACHER' or str(row['participant_type']).upper()!='STUDENT':raise ValueError('message_not_student_outbound')
    import json
    try:attachment=json.loads(row['attachment_json'] or 'null')
    except Exception:attachment=None
    result,any_sent=_deliver_existing(mid,int(row['student_id']),str(row['body'] or ''),requested,attachment)
    return {'status':'ok' if any_sent else 'delivery_failed','message_id':mid,'deliveries':result}
