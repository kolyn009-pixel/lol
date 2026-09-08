"""Unified conversation store shared by WEB, TELEGRAM and VK adapters.

Adapters should ingest incoming messages here and delivery workers can mark
outgoing messages delivered per channel. This prevents separate chat histories.
"""
from database import connect, now_iso

CHANNELS={"WEB","TELEGRAM","VK","SYSTEM"}


def ensure_tables():
    conn=connect(); conn.executescript("""
    CREATE TABLE IF NOT EXISTS conversation_messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      direction TEXT NOT NULL,
      sender_role TEXT NOT NULL,
      source_channel TEXT NOT NULL,
      external_message_id TEXT,
      text TEXT,
      attachment_type TEXT,
      attachment_ref TEXT,
      attachment_name TEXT,
      created_at TEXT NOT NULL,
      read_at TEXT,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_conv_external ON conversation_messages(source_channel,external_message_id) WHERE external_message_id IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_conv_user_time ON conversation_messages(user_id,created_at DESC);
    CREATE TABLE IF NOT EXISTS message_deliveries(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      message_id INTEGER NOT NULL,
      channel TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'PENDING',
      external_message_id TEXT,
      attempted_at TEXT,
      delivered_at TEXT,
      error TEXT,
      UNIQUE(message_id,channel),
      FOREIGN KEY(message_id) REFERENCES conversation_messages(id) ON DELETE CASCADE
    );
    """); conn.commit(); conn.close()


def add_message(user_id,direction,sender_role,source_channel,text=None,external_message_id=None,attachment_type=None,attachment_ref=None,attachment_name=None):
    ensure_tables(); source=str(source_channel).upper()
    if source not in CHANNELS: raise ValueError('invalid_channel')
    conn=connect()
    if external_message_id:
        old=conn.execute("SELECT id FROM conversation_messages WHERE source_channel=? AND external_message_id=?",(source,str(external_message_id))).fetchone()
        if old: conn.close(); return int(old['id'])
    cur=conn.execute("""INSERT INTO conversation_messages(user_id,direction,sender_role,source_channel,external_message_id,text,attachment_type,attachment_ref,attachment_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",(int(user_id),str(direction).upper(),str(sender_role).upper(),source,str(external_message_id) if external_message_id else None,str(text or ''),attachment_type,attachment_ref,attachment_name,now_iso()))
    mid=int(cur.lastrowid); conn.commit(); conn.close(); return mid


def queue_teacher_reply(user_id,text,channels=("TELEGRAM","VK")):
    mid=add_message(user_id,"OUT","TEACHER","WEB",text=text)
    conn=connect()
    for channel in channels:
        c=str(channel).upper()
        if c in {"TELEGRAM","VK"}: conn.execute("INSERT OR IGNORE INTO message_deliveries(message_id,channel,status) VALUES(?,?, 'PENDING')",(mid,c))
    conn.commit(); conn.close(); return mid


def conversation(user_id,limit=100):
    ensure_tables(); conn=connect(); rows=conn.execute("SELECT * FROM conversation_messages WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT ?",(int(user_id),int(limit))).fetchall(); conn.close(); return [dict(r) for r in reversed(rows)]


def inbox(limit=100):
    ensure_tables(); conn=connect(); rows=conn.execute("""SELECT m.*,u.name FROM conversation_messages m JOIN users u ON u.id=m.user_id WHERE m.id IN (SELECT MAX(id) FROM conversation_messages GROUP BY user_id) ORDER BY m.created_at DESC LIMIT ?""",(int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]
