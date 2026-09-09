"""Compatibility facade for the Stage 10 unified messaging store.

Legacy web-chat rows are imported incrementally into the canonical Stage 10 store.
Student-facing compatibility responses expose only message content needed by the UI;
internal delivery identifiers/errors remain teacher-side.
"""
from __future__ import annotations
import hashlib
import threading
from database import connect
from web_backend import unified_messaging as um

CHANNELS={"WEB","TELEGRAM","VK","SYSTEM"}
_MIGRATION_LOCK=threading.Lock()
_MIGRATION_DONE=False


def _table_exists(conn,name):
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(str(name),)).fetchone())


def _external_legacy_id(channel,external_message_id):
    raw=f"{str(channel).upper()}:{external_message_id}".encode('utf-8')
    return int(hashlib.sha256(raw).hexdigest()[:15],16)


def _attachment_from_old(row):
    kind=row['attachment_type'] if 'attachment_type' in row.keys() else None
    ref=row['attachment_ref'] if 'attachment_ref' in row.keys() else None
    name=row['attachment_name'] if 'attachment_name' in row.keys() else None
    if not any((kind,ref,name)):return None
    return {'kind':kind,'ref':ref,'name':name}


def _migrate_old(limit=50000):
    """Import only legacy rows not already represented in unified_messages."""
    um.ensure_tables();conn=connect()
    if not _table_exists(conn,'conversation_messages'):
        conn.close();return {'messages':0,'deliveries':0}
    rows=conn.execute("""
      SELECT c.*
      FROM conversation_messages c
      LEFT JOIN unified_messages u
        ON u.legacy_source='conversation_messages' AND u.legacy_id=c.id
      WHERE u.id IS NULL
      ORDER BY c.id
      LIMIT ?
    """,(max(1,min(int(limit),100000)),)).fetchall()
    deliveries=[]
    if rows and _table_exists(conn,'message_deliveries'):
        ids=[int(r['id']) for r in rows];marks=','.join('?' for _ in ids)
        deliveries=conn.execute(f"SELECT * FROM message_deliveries WHERE message_id IN ({marks}) ORDER BY id",ids).fetchall()
    conn.close();mapped={};migrated=0
    for r in rows:
        source=str(r['source_channel'] or 'LEGACY').upper();origin=source if source in um.CHANNELS else 'LEGACY';sender=str(r['sender_role'] or ('TEACHER' if str(r['direction']).upper()=='OUT' else 'STUDENT')).upper();state='READ' if ('read_at' in r.keys() and r['read_at']) else 'SENT'
        mid=um.record_message(int(r['user_id']),str(r['direction'] or 'IN').upper(),str(r['text'] or ''),participant_type='STUDENT',sender_type=sender,sender_id=int(r['user_id']) if sender=='STUDENT' else None,origin_channel=origin,content_type=str(r['attachment_type'] or 'TEXT').upper() if 'attachment_type' in r.keys() else 'TEXT',attachment=_attachment_from_old(r),status=state,legacy_source='conversation_messages',legacy_id=int(r['id']))
        if mid:mapped[int(r['id'])]=mid;migrated+=1
    delivery_count=0
    for d in deliveries:
        mid=mapped.get(int(d['message_id']))
        if not mid:continue
        state=str(d['status'] or 'QUEUED').upper();state={'PENDING':'QUEUED','ERROR':'FAILED'}.get(state,state)
        if state not in um.DELIVERY_STATUSES:state='QUEUED'
        um.record_delivery(mid,str(d['channel'] or 'SYSTEM'),'STUDENT',None,state,d['external_message_id'] if 'external_message_id' in d.keys() else None,d['error'] if 'error' in d.keys() else None);delivery_count+=1
    return {'messages':migrated,'deliveries':delivery_count}


def ensure_tables():
    global _MIGRATION_DONE
    um.ensure_tables()
    if _MIGRATION_DONE:return
    with _MIGRATION_LOCK:
        if _MIGRATION_DONE:return
        _migrate_old();_MIGRATION_DONE=True


def add_message(user_id,direction,sender_role,source_channel,text=None,external_message_id=None,attachment_type=None,attachment_ref=None,attachment_name=None):
    ensure_tables();source=str(source_channel).upper()
    if source not in CHANNELS:raise ValueError('invalid_channel')
    attachment={'kind':attachment_type,'ref':attachment_ref,'name':attachment_name} if any((attachment_type,attachment_ref,attachment_name)) else None
    legacy_source=None;legacy_id=None
    if external_message_id not in (None,''):
        legacy_source=f'external:{source}';legacy_id=_external_legacy_id(source,external_message_id)
    return um.record_message(int(user_id),str(direction).upper(),str(text or ''),participant_type='STUDENT',sender_type=str(sender_role).upper(),sender_id=int(user_id) if str(sender_role).upper()=='STUDENT' else None,origin_channel=source,content_type=str(attachment_type or 'TEXT').upper(),attachment=attachment,status='DELIVERED' if str(direction).upper()=='IN' else 'SENT',legacy_source=legacy_source,legacy_id=legacy_id)


def queue_teacher_reply(user_id,text,channels=("TELEGRAM","VK")):
    mid=add_message(user_id,"OUT","TEACHER","WEB",text=text)
    for channel in channels:
        c=str(channel).upper()
        if c in {"TELEGRAM","VK"}:um.record_delivery(mid,c,'STUDENT',int(user_id),'QUEUED')
    return mid


def _compat(row,include_deliveries=False):
    attachment=row.get('attachment') or {}
    item={'id':row.get('id'),'user_id':row.get('student_id'),'direction':row.get('direction'),'sender_role':row.get('sender_type'),'source_channel':row.get('origin_channel'),'external_message_id':None,'text':row.get('body') or '','attachment_type':attachment.get('kind') if isinstance(attachment,dict) else None,'attachment_ref':attachment.get('ref') if isinstance(attachment,dict) else None,'attachment_name':attachment.get('name') if isinstance(attachment,dict) else None,'created_at':row.get('created_at'),'read_at':row.get('read_at')}
    if include_deliveries:item['deliveries']=row.get('deliveries') or []
    return item


def conversation(user_id,limit=100):
    ensure_tables();conv=um.conversation(int(user_id),'STUDENT',None);rows=um.history(conv['id'],limit);return [_compat(r,False) for r in reversed(rows)]


def inbox(limit=100):
    ensure_tables();items=[]
    for c in um.conversations(limit):
        rows=um.history(c['id'],1);last=_compat(rows[0],True) if rows else {'id':None,'text':'','created_at':c.get('updated_at'),'direction':None,'source_channel':None,'deliveries':[]}
        last.update({'name':c.get('name'),'user_id':c.get('student_id'),'unread':int(c.get('unread') or 0),'conversation_id':c.get('id')});items.append(last)
    return items
