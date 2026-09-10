"""VK payment receipt intake shared with the canonical payments database.

VK attachment URLs may expire, so supported receipts are downloaded immediately
to a protected local spool. The payment then moves to RECEIPT_SENT and the
canonical Yandex Disk worker archives the stable local copy asynchronously.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,urlopen

import database
from .attachment_bridge import vk_attachment_descriptor, vk_forward_to_admin_telegram

RECEIPT_ROOT=Path(os.environ.get('ADELIA_VK_RECEIPT_DIR','/opt/tutorbot/data/vk_receipts'))
MAX_RECEIPT_BYTES=25*1024*1024


def _waiting_payment(user_id):
    c=database.connect()
    try:
        row=c.execute("""SELECT * FROM payments
            WHERE user_id=? AND status='WAITING'
            ORDER BY id DESC LIMIT 1""",(int(user_id),)).fetchone()
        return dict(row) if row else None
    finally:c.close()


def _existing_receipt(payment_id,user_id,fingerprint):
    c=database.connect()
    try:
        row=c.execute("""SELECT id FROM receipts
            WHERE payment_id=? AND user_id=? AND source_platform='VK'
              AND (file_id=? OR file_id LIKE ?)
            ORDER BY id DESC LIMIT 1""",(int(payment_id),int(user_id),str(fingerprint),f'%{fingerprint}%')).fetchone()
        return int(row['id']) if row else None
    finally:c.close()


def _mark_receipt_sent(payment_id):
    c=database.connect()
    try:
        c.execute("UPDATE payments SET status='RECEIPT_SENT' WHERE id=? AND status='WAITING'",(int(payment_id),))
        c.commit()
    finally:c.close()


def _download(url):
    parsed=urlparse(str(url or ''))
    if parsed.scheme!='https' or not parsed.netloc:raise ValueError('invalid_vk_receipt_url')
    with urlopen(Request(str(url),headers={'User-Agent':'TutorBot-VK-Receipt/1.0'}),timeout=30) as resp:
        declared=int(resp.headers.get('Content-Length') or 0)
        if declared>MAX_RECEIPT_BYTES:raise ValueError('receipt_too_large')
        raw=resp.read(MAX_RECEIPT_BYTES+1)
    if not raw:raise ValueError('receipt_empty')
    if len(raw)>MAX_RECEIPT_BYTES:raise ValueError('receipt_too_large')
    return raw


def _extension(descriptor,raw):
    name=str(descriptor.get('filename') or '').lower()
    suffix=Path(name).suffix
    if suffix in {'.pdf','.jpg','.jpeg','.png','.webp'}:return suffix
    if raw.startswith(b'%PDF-'):return '.pdf'
    if raw.startswith(b'\xff\xd8\xff'):return '.jpg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):return '.png'
    if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP':return '.webp'
    return '.bin'


def _persist(user_id,payment_id,descriptor):
    raw=_download(descriptor['url']);digest=hashlib.sha256(raw).hexdigest();RECEIPT_ROOT.mkdir(parents=True,exist_ok=True)
    path=RECEIPT_ROOT/f"{int(user_id)}_{int(payment_id)}_{digest[:16]}_{secrets.token_hex(4)}{_extension(descriptor,raw)}"
    path.write_bytes(raw)
    try:os.chmod(path,0o600)
    except OSError:pass
    return path,digest


def submit(user_id,attachments):
    uid=int(user_id);payment=_waiting_payment(uid)
    if not payment:return {'status':'no_waiting_payment','accepted':0}
    descriptors=[]
    for item in attachments or []:
        d=vk_attachment_descriptor(item)
        if d and d.get('url') and d.get('kind') in {'photo','document'}:descriptors.append(d)
    if not descriptors:return {'status':'no_supported_attachment','accepted':0}
    receipt_ids=[];duplicate_ids=[];errors=[]
    for d in descriptors:
        try:
            path,digest=_persist(uid,int(payment['id']),d)
            existing=_existing_receipt(int(payment['id']),uid,digest)
            if existing:
                duplicate_ids.append(existing)
                try:path.unlink(missing_ok=True)
                except OSError:pass
                continue
            file_type='PHOTO' if d['kind']=='photo' else 'DOCUMENT'
            rid=database.add_receipt(payment_id=int(payment['id']),user_id=uid,file_id=str(path),file_type=file_type,source_platform='VK')
            if rid is not None:
                receipt_ids.append(int(rid))
                try:
                    from web_backend import receipt_cloud_archive
                    receipt_cloud_archive.enqueue(int(rid))
                except Exception:pass
        except Exception as exc:errors.append(type(exc).__name__)
    if not receipt_ids and duplicate_ids:return {'status':'duplicate','accepted':0,'payment_id':int(payment['id']),'receipt_ids':duplicate_ids}
    if not receipt_ids:return {'status':'receipt_store_failed','accepted':0,'errors':errors}
    _mark_receipt_sent(int(payment['id']))
    try:
        u=database.get_user(uid);vk_forward_to_admin_telegram(attachments,f"🧾 Чек из VK · {u['name'] if u else uid}\nПлатёж #{int(payment['id'])}")
    except Exception:pass
    return {'status':'ok','accepted':len(receipt_ids),'payment_id':int(payment['id']),'receipt_ids':receipt_ids,'duplicates':duplicate_ids,'archive_status':'PENDING'}
