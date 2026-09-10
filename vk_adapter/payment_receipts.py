"""VK payment receipt intake shared with the canonical payments database.

The receipt is attached to the student's latest WAITING payment. Cloud archival
is queued best-effort and never blocks payment review.
"""
from __future__ import annotations

import database
from .attachment_bridge import vk_attachment_descriptor, vk_forward_to_admin_telegram


def _waiting_payment(user_id):
    c=database.connect()
    try:
        row=c.execute("""SELECT * FROM payments
            WHERE user_id=? AND status='WAITING'
            ORDER BY id DESC LIMIT 1""",(int(user_id),)).fetchone()
        return dict(row) if row else None
    finally:c.close()


def _mark_receipt_sent(payment_id):
    c=database.connect()
    try:
        c.execute("UPDATE payments SET status='RECEIPT_SENT' WHERE id=? AND status='WAITING'",(int(payment_id),))
        c.commit()
    finally:c.close()


def submit(user_id,attachments):
    uid=int(user_id);payment=_waiting_payment(uid)
    if not payment:return {'status':'no_waiting_payment','accepted':0}
    descriptors=[]
    for item in attachments or []:
        d=vk_attachment_descriptor(item)
        if d and d.get('url') and d.get('kind') in {'photo','document'}:descriptors.append(d)
    if not descriptors:return {'status':'no_supported_attachment','accepted':0}
    receipt_ids=[]
    for d in descriptors:
        file_type='PHOTO' if d['kind']=='photo' else 'DOCUMENT'
        rid=database.add_receipt(payment_id=int(payment['id']),user_id=uid,file_id=str(d['url']),file_type=file_type,source_platform='VK')
        if rid is not None:
            receipt_ids.append(int(rid))
            try:
                from web_backend import receipt_cloud_archive
                receipt_cloud_archive.enqueue(int(rid))
            except Exception:pass
    if not receipt_ids:return {'status':'receipt_store_failed','accepted':0}
    _mark_receipt_sent(int(payment['id']))
    try:
        u=database.get_user(uid);vk_forward_to_admin_telegram(attachments,f"🧾 Чек из VK · {u['name'] if u else uid}\nПлатёж #{int(payment['id'])}")
    except Exception:pass
    return {'status':'ok','accepted':len(receipt_ids),'payment_id':int(payment['id']),'receipt_ids':receipt_ids,'archive_status':'PENDING'}
