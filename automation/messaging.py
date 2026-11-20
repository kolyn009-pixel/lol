import json
from datetime import datetime
from zoneinfo import ZoneInfo
import database


def create_inbox(body, sender_telegram_id, student_id=None, parent_id=None, category='ORGANIZATIONAL', subject=None, status='OPEN'):
    conn=database.connect(); cur=conn.cursor(); cur.execute('''INSERT INTO teacher_inbox(student_id,parent_id,sender_telegram_id,category,subject,body,status,created_at) VALUES(?,?,?,?,?,?,?,?)''',(student_id,parent_id,sender_telegram_id,category,subject,body,status,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid


def inbox(status='OPEN',limit=100):
    conn=database.connect(); rows=conn.execute('SELECT * FROM teacher_inbox WHERE status=? ORDER BY created_at DESC LIMIT ?',(status,limit)).fetchall(); conn.close(); return rows


def close_inbox(item_id):
    conn=database.connect(); conn.execute("UPDATE teacher_inbox SET status='CLOSED',closed_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),item_id)); conn.commit(); conn.close()


def close_all_inbox():
    conn=database.connect()
    cur=conn.execute(
        "UPDATE teacher_inbox SET status='CLOSED',closed_at=? WHERE status IN ('OPEN','QUEUED')",
        (datetime.now().isoformat(timespec='seconds'),),
    )
    conn.commit(); count=cur.rowcount; conn.close(); return int(count or 0)


# scheduled_messages.send_at storage convention: naive Europe/Moscow wall clock.
STORAGE_TZ=ZoneInfo('Europe/Moscow')


def to_storage_send_at(value):
    """Normalize a send moment to the storage convention (naive MSK ISO).

    Aware datetimes / ISO strings with an offset are converted; naive values
    are assumed to already be MSK (legacy convention of the queue).
    """
    dt=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
    if dt.tzinfo is not None:
        dt=dt.astimezone(STORAGE_TZ).replace(tzinfo=None)
    return dt.isoformat(timespec='seconds')


def parse_send_at(value):
    """Stored send_at -> aware datetime (naive = MSK, offset strings honoured)."""
    dt=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
    return dt.replace(tzinfo=STORAGE_TZ) if dt.tzinfo is None else dt


def schedule(created_by,text,send_at,target_type='ALL',target_id=None,segment=None):
    send_at=to_storage_send_at(send_at)
    conn=database.connect(); cur=conn.cursor(); cur.execute('''INSERT INTO scheduled_messages(created_by,target_type,target_id,segment_json,text,send_at,status,created_at) VALUES(?,?,?,?,?,?,'PENDING',?)''',(created_by,target_type,target_id,json.dumps(segment or {},ensure_ascii=False),text,send_at,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid


def due(now=None):
    """Pending messages whose moment has come, compared as aware datetimes."""
    now=parse_send_at(now) if now is not None else datetime.now(STORAGE_TZ)
    conn=database.connect()
    try: rows=conn.execute("SELECT * FROM scheduled_messages WHERE status='PENDING'").fetchall()
    finally: conn.close()
    out=[]
    for r in rows:
        try: at=parse_send_at(r['send_at'])
        except Exception: continue
        if at<=now: out.append((at,r))
    out.sort(key=lambda x:(x[0],x[1]['id']))
    return [r for _,r in out]


def mark_sent(mid,error=None):
    conn=database.connect(); conn.execute("UPDATE scheduled_messages SET status=?,sent_at=?,error_text=? WHERE id=?",('FAILED' if error else 'SENT',datetime.now().isoformat(timespec='seconds'),error,mid)); conn.commit(); conn.close()


def target_telegram_ids(row):
    conn=database.connect(); typ=row['target_type']; ids=[]
    if typ=='TELEGRAM' and row['target_id']:
        ids=[int(row['target_id'])]
    elif typ=='STUDENT' and row['target_id']:
        r=conn.execute('SELECT telegram_id FROM users WHERE id=?',(row['target_id'],)).fetchone(); ids=[r['telegram_id']] if r and r['telegram_id'] else []
    elif typ=='ALL': ids=[r['telegram_id'] for r in conn.execute('SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL').fetchall()]
    elif typ=='PARENTS': ids=[r['telegram_id'] for r in conn.execute('SELECT telegram_id FROM parent_accounts WHERE telegram_id IS NOT NULL').fetchall()]
    conn.close(); return list(dict.fromkeys(ids))
