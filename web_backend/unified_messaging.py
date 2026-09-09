"""Stage 10 unified messaging store.

Telegram, VK and Web describe one conversation instead of maintaining separate
histories. Legacy CRM rows are imported idempotently during the transition.
"""
from __future__ import annotations
import json,sqlite3
from database import connect, now_iso

CHANNELS={'TELEGRAM','VK','WEB','SYSTEM','LEGACY'}
PARTICIPANTS={'STUDENT','PARENT','TEACHER'}
DIRECTIONS={'IN','OUT','SYSTEM'}
DELIVERY_STATUSES={'QUEUED','SENT','DELIVERED','READ','FAILED','SKIPPED'}


def ensure_tables():
    conn=connect();conn.executescript("""
    CREATE TABLE IF NOT EXISTS unified_conversations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,participant_type TEXT NOT NULL DEFAULT 'STUDENT',participant_id INTEGER,status TEXT NOT NULL DEFAULT 'OPEN',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(student_id,participant_type,participant_id),FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS unified_messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,conversation_id INTEGER NOT NULL,student_id INTEGER NOT NULL,participant_type TEXT NOT NULL,participant_id INTEGER,direction TEXT NOT NULL,sender_type TEXT NOT NULL,sender_id INTEGER,body TEXT NOT NULL DEFAULT '',origin_channel TEXT NOT NULL DEFAULT 'SYSTEM',content_type TEXT NOT NULL DEFAULT 'TEXT',attachment_json TEXT,status TEXT NOT NULL DEFAULT 'SENT',reply_to_message_id INTEGER,legacy_source TEXT,legacy_id INTEGER,created_at TEXT NOT NULL,edited_at TEXT,read_at TEXT,FOREIGN KEY(conversation_id) REFERENCES unified_conversations(id) ON DELETE CASCADE,FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE,UNIQUE(legacy_source,legacy_id));
    CREATE TABLE IF NOT EXISTS unified_message_deliveries(
      id INTEGER PRIMARY KEY AUTOINCREMENT,message_id INTEGER NOT NULL,channel TEXT NOT NULL,recipient_type TEXT NOT NULL,recipient_id TEXT NOT NULL DEFAULT '',external_message_id TEXT,status TEXT NOT NULL DEFAULT 'QUEUED',error_code TEXT,queued_at TEXT,sent_at TEXT,delivered_at TEXT,read_at TEXT,updated_at TEXT NOT NULL,FOREIGN KEY(message_id) REFERENCES unified_messages(id) ON DELETE CASCADE,UNIQUE(message_id,channel,recipient_type,recipient_id));
    CREATE INDEX IF NOT EXISTS idx_unified_conv_student ON unified_conversations(student_id,updated_at DESC);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_conv_identity ON unified_conversations(student_id,participant_type,COALESCE(participant_id,0));
    CREATE INDEX IF NOT EXISTS idx_unified_msg_conv ON unified_messages(conversation_id,id DESC);
    CREATE INDEX IF NOT EXISTS idx_unified_msg_student ON unified_messages(student_id,id DESC);
    CREATE INDEX IF NOT EXISTS idx_unified_delivery_status ON unified_message_deliveries(status,channel,updated_at);
    """);conn.commit();conn.close()


def _norm(value,allowed,default):
    v=str(value or default).strip().upper();return v if v in allowed else default


def conversation(student_id,participant_type='STUDENT',participant_id=None):
    ensure_tables();uid=int(student_id);ptype=_norm(participant_type,PARTICIPANTS,'STUDENT');pid=int(participant_id) if participant_id not in (None,'') else None;now=now_iso();conn=connect()
    try:
        row=conn.execute("SELECT * FROM unified_conversations WHERE student_id=? AND participant_type=? AND COALESCE(participant_id,0)=COALESCE(?,0) LIMIT 1",(uid,ptype,pid)).fetchone()
        if not row:
            try:cur=conn.execute("INSERT INTO unified_conversations(student_id,participant_type,participant_id,created_at,updated_at) VALUES(?,?,?,?,?)",(uid,ptype,pid,now,now));conn.commit();row=conn.execute('SELECT * FROM unified_conversations WHERE id=?',(int(cur.lastrowid),)).fetchone()
            except sqlite3.IntegrityError:
                conn.rollback();row=conn.execute("SELECT * FROM unified_conversations WHERE student_id=? AND participant_type=? AND COALESCE(participant_id,0)=COALESCE(?,0) LIMIT 1",(uid,ptype,pid)).fetchone()
        return dict(row)
    finally:conn.close()


def record_message(student_id,direction,body,participant_type='STUDENT',participant_id=None,sender_type=None,sender_id=None,origin_channel='SYSTEM',content_type='TEXT',attachment=None,status='SENT',reply_to_message_id=None,legacy_source=None,legacy_id=None):
    conv=conversation(student_id,participant_type,participant_id);direction=_norm(direction,DIRECTIONS,'SYSTEM');origin=_norm(origin_channel,CHANNELS,'SYSTEM');ptype=_norm(participant_type,PARTICIPANTS,'STUDENT');sender=_norm(sender_type or ('TEACHER' if direction=='OUT' else ptype),PARTICIPANTS,'TEACHER' if direction=='OUT' else ptype);state=str(status or 'SENT').strip().upper();now=now_iso();payload=json.dumps(attachment,ensure_ascii=False) if attachment else None;conn=connect()
    try:
        try:
            cur=conn.execute("""INSERT INTO unified_messages(conversation_id,student_id,participant_type,participant_id,direction,sender_type,sender_id,body,origin_channel,content_type,attachment_json,status,reply_to_message_id,legacy_source,legacy_id,created_at,read_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(conv['id'],int(student_id),ptype,int(participant_id) if participant_id not in (None,'') else None,direction,sender,int(sender_id) if sender_id not in (None,'') and str(sender_id).isdigit() else sender_id,str(body or ''),origin,str(content_type or 'TEXT').upper(),payload,state,int(reply_to_message_id) if reply_to_message_id else None,legacy_source,int(legacy_id) if legacy_id is not None else None,now,now if state=='READ' else None));mid=int(cur.lastrowid)
        except sqlite3.IntegrityError:
            if not (legacy_source and legacy_id is not None):raise
            row=conn.execute('SELECT id FROM unified_messages WHERE legacy_source=? AND legacy_id=?',(legacy_source,int(legacy_id))).fetchone()
            if not row:raise
            mid=int(row['id'])
        conn.execute('UPDATE unified_conversations SET updated_at=? WHERE id=?',(now,int(conv['id'])));conn.commit();return mid
    finally:conn.close()


def record_delivery(message_id,channel,recipient_type,recipient_id=None,status='QUEUED',external_message_id=None,error_code=None):
    ensure_tables();mid=int(message_id);ch=_norm(channel,CHANNELS,'SYSTEM');rtype=_norm(recipient_type,PARTICIPANTS,'STUDENT');state=_norm(status,DELIVERY_STATUSES,'QUEUED');now=now_iso();rid=str(recipient_id) if recipient_id is not None else '';conn=connect();old=conn.execute("SELECT id,queued_at,sent_at,delivered_at,read_at FROM unified_message_deliveries WHERE message_id=? AND channel=? AND recipient_type=? AND recipient_id=?",(mid,ch,rtype,rid)).fetchone();queued=(old['queued_at'] if old else None) or now;sent=(old['sent_at'] if old else None) or (now if state in {'SENT','DELIVERED','READ'} else None);delivered=(old['delivered_at'] if old else None) or (now if state in {'DELIVERED','READ'} else None);read=(old['read_at'] if old else None) or (now if state=='READ' else None)
    conn.execute("""INSERT INTO unified_message_deliveries(message_id,channel,recipient_type,recipient_id,external_message_id,status,error_code,queued_at,sent_at,delivered_at,read_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(message_id,channel,recipient_type,recipient_id) DO UPDATE SET external_message_id=COALESCE(excluded.external_message_id,unified_message_deliveries.external_message_id),status=excluded.status,error_code=excluded.error_code,sent_at=COALESCE(excluded.sent_at,unified_message_deliveries.sent_at),delivered_at=COALESCE(excluded.delivered_at,unified_message_deliveries.delivered_at),read_at=COALESCE(excluded.read_at,unified_message_deliveries.read_at),updated_at=excluded.updated_at""",(mid,ch,rtype,rid,str(external_message_id) if external_message_id is not None else None,state,error_code,queued,sent,delivered,read,now));conn.commit();conn.close();return {'status':'ok','message_id':mid,'channel':ch,'delivery_status':state}


def import_legacy(limit=5000):
    ensure_tables();conn=connect()
    try:
        try:
            rows=conn.execute("""SELECT c.* FROM crm_student_messages c LEFT JOIN unified_messages u ON u.legacy_source='crm_student_messages' AND u.legacy_id=c.id WHERE u.id IS NULL ORDER BY c.id LIMIT ?""",(max(1,min(int(limit),50000)),)).fetchall()
        except sqlite3.OperationalError:rows=[]
    finally:conn.close()
    count=0
    for r in rows:
        mid=record_message(r['student_id'],r['direction'],r['body'],participant_type='STUDENT',sender_type='TEACHER' if r['direction']=='OUT' else 'STUDENT',sender_id=r['sender_admin_id'] if r['direction']=='OUT' else r['student_id'],origin_channel='LEGACY',status=r['status'],legacy_source='crm_student_messages',legacy_id=r['id'])
        if mid:count+=1
    return {'status':'ok','imported':count}


def conversations(limit=100,only_unread=False):
    ensure_tables();import_legacy();conn=connect();where="HAVING unread>0" if only_unread else ''
    rows=conn.execute(f"""SELECT c.id,c.student_id,u.name,c.participant_type,c.participant_id,c.status,c.updated_at,MAX(m.created_at) last_at,SUM(CASE WHEN m.direction='IN' AND m.read_at IS NULL THEN 1 ELSE 0 END) unread,(SELECT body FROM unified_messages x WHERE x.conversation_id=c.id ORDER BY x.id DESC LIMIT 1) last_body FROM unified_conversations c JOIN users u ON u.id=c.student_id LEFT JOIN unified_messages m ON m.conversation_id=c.id GROUP BY c.id {where} ORDER BY datetime(COALESCE(last_at,c.updated_at)) DESC LIMIT ?""",(max(1,min(int(limit),500)),)).fetchall();conn.close();return [dict(r) for r in rows]


def history(conversation_id,limit=100):
    ensure_tables();conn=connect();messages=conn.execute("SELECT * FROM unified_messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",(int(conversation_id),max(1,min(int(limit),500)))).fetchall();out=[]
    for r in messages:
        x=dict(r);deliveries=conn.execute("SELECT channel,recipient_type,recipient_id,status,external_message_id,error_code FROM unified_message_deliveries WHERE message_id=? ORDER BY id",(int(r['id']),)).fetchall();x['deliveries']=[dict(d) for d in deliveries]
        try:x['attachment']=json.loads(x.pop('attachment_json') or 'null')
        except (TypeError,ValueError,json.JSONDecodeError):x['attachment']=None
        out.append(x)
    conn.close();return out


def mark_read(conversation_id):
    ensure_tables();now=now_iso();conn=connect();conn.execute("UPDATE unified_messages SET read_at=COALESCE(read_at,?),status=CASE WHEN status IN ('DELIVERED','SENT') THEN 'READ' ELSE status END WHERE conversation_id=? AND direction='IN' AND read_at IS NULL",(now,int(conversation_id)));conn.commit();conn.close();return {'status':'ok'}
