"""Deliver durable homework events to the existing Telegram/VK channel layer."""
from __future__ import annotations

import os
import time

from web_backend.homework_notifications import claim_pending, mark_delivered, mark_failed
from vk_adapter.channel_delivery import send_student

POLL_SECONDS=float(os.getenv('ADELIA_HOMEWORK_NOTIFY_POLL','5') or 5)
BATCH_SIZE=int(os.getenv('ADELIA_HOMEWORK_NOTIFY_BATCH','50') or 50)


def _teacher_ids():
    """Resolve active OWNER/ADMIN Telegram users without coupling to one hardcoded id."""
    try:
        import database
        conn=database.connect()
        cols={r['name'] for r in conn.execute('PRAGMA table_info(admins)').fetchall()}
        if cols and 'user_id' in cols:
            active=" AND active=1" if 'active' in cols else ''
            role=" AND role IN ('OWNER','ADMIN')" if 'role' in cols else ''
            rows=conn.execute(f"SELECT user_id FROM admins WHERE 1=1{active}{role}").fetchall()
            conn.close();return [int(r['user_id']) for r in rows]
        conn.close()
    except Exception:
        pass
    return []


def _with_action(item):
    text=str(item.get('text') or '').strip();url=str(item.get('action_url') or '').strip();label=str(item.get('action_label') or '').strip()
    if url:
        if url.startswith('/'):
            base=os.getenv('ADELIA_PUBLIC_URL','https://adeliatutor.ru').rstrip('/');url=base+url
        text += f"\n\n{label or 'Открыть'}: {url}"
    return text


def deliver(item):
    recipient=str(item.get('recipient_type') or '').upper();text=_with_action(item);uid=item.get('user_id')
    if recipient=='STUDENT':
        if uid is None:return False,'student_id_missing'
        result=send_student(int(uid),text,telegram=True,vk=True)
        return any(result.values()),f"telegram={result.get('telegram')} vk={result.get('vk')}"
    if recipient=='TEACHER':
        ids=_teacher_ids()
        if not ids:return False,'teacher_recipient_missing'
        delivered=False;parts=[]
        for teacher_id in ids:
            result=send_student(teacher_id,text,telegram=True,vk=True);delivered=delivered or any(result.values());parts.append(f"{teacher_id}:tg={result.get('telegram')},vk={result.get('vk')}")
        return delivered,'; '.join(parts)
    return False,'unsupported_recipient'


def tick(limit=BATCH_SIZE):
    items=claim_pending(limit);sent=0
    for item in items:
        try:
            ok,detail=deliver(item)
            if ok:mark_delivered(item['id']);sent+=1
            else:mark_failed(item['id'],detail)
        except Exception as exc:
            mark_failed(item['id'],repr(exc))
    return {'claimed':len(items),'delivered':sent}


def main():
    while True:
        try:tick()
        except Exception as exc:print('[homework-delivery]',repr(exc),flush=True)
        time.sleep(max(1.0,POLL_SECONDS))

if __name__=='__main__':main()
