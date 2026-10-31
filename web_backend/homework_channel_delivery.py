"""Durable per-recipient/channel receipts, shared by all homework worker retries."""
import time,uuid
import database
from web_backend import reliable_channel_send as provider
from vk_adapter import channel_delivery as identities

def schema():
 c=database.connect()
 try:
  c.executescript('''CREATE TABLE IF NOT EXISTS homework_delivery_batches(item_id INTEGER PRIMARY KEY,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS homework_delivery_targets(item_id INTEGER NOT NULL,user_id INTEGER NOT NULL,channel TEXT NOT NULL,recipient_id INTEGER NOT NULL,status TEXT NOT NULL,claim_token TEXT,claimed_at REAL,error TEXT,external_id TEXT,updated_at TEXT NOT NULL,PRIMARY KEY(item_id,user_id,channel));''');c.commit()
 finally:c.close()

def deliver(item,text,user_ids):
 schema();iid=int(item['id']);c=database.connect()
 try:
  c.execute('BEGIN IMMEDIATE')
  if not c.execute('SELECT 1 FROM homework_delivery_batches WHERE item_id=?',(iid,)).fetchone():
   for uid in dict.fromkeys(map(int,user_ids)):
    for channel,rid in [('TELEGRAM',identities.telegram_chat(uid)),('VK',identities.vk_peer(uid))]:
     if rid:c.execute("INSERT INTO homework_delivery_targets(item_id,user_id,channel,recipient_id,status,updated_at) VALUES(?,?,?,?,'PENDING',?)",(iid,uid,channel,int(rid),database.now_iso()))
   c.execute('INSERT INTO homework_delivery_batches VALUES(?,?)',(iid,database.now_iso()))
  c.commit();targets=[dict(r) for r in c.execute('SELECT * FROM homework_delivery_targets WHERE item_id=? ORDER BY user_id,channel',(iid,))]
 finally:c.close()
 if not targets:return False,'no_linked_channels'
 for t in targets:
  c=database.connect();token=uuid.uuid4().hex
  try:
   c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM homework_delivery_targets WHERE item_id=? AND user_id=? AND channel=?',(iid,t['user_id'],t['channel'])).fetchone()
   if row['status'] in {'SENT','FAILED','UNKNOWN','SKIPPED'}:c.rollback();continue
   if row['status']=='CLAIMED':
    if float(row['claimed_at'] or 0)<time.time()-300:c.execute("UPDATE homework_delivery_targets SET status='UNKNOWN',error='worker_interrupted_check_delivery',claim_token=NULL WHERE item_id=? AND user_id=? AND channel=?",(iid,t['user_id'],t['channel']));c.commit()
    else:c.rollback()
    continue
   current=identities.telegram_chat(t['user_id']) if t['channel']=='TELEGRAM' else identities.vk_peer(t['user_id'])
   if not current or int(current)!=int(t['recipient_id']):
    c.execute("UPDATE homework_delivery_targets SET status='SKIPPED',error='recipient_link_changed' WHERE item_id=? AND user_id=? AND channel=?",(iid,t['user_id'],t['channel']));c.commit();continue
   c.execute("UPDATE homework_delivery_targets SET status='CLAIMED',claim_token=?,claimed_at=?,updated_at=? WHERE item_id=? AND user_id=? AND channel=?",(token,time.time(),database.now_iso(),iid,t['user_id'],t['channel']));c.commit()
  finally:c.close()
  status='SENT';error=None;external=None
  try:external=provider.send(t['channel'],t['recipient_id'],text,iid)
  except provider.Retryable as exc:status='RETRY';error=str(exc)
  except provider.Permanent as exc:status='FAILED';error=str(exc)
  except Exception as exc:status='UNKNOWN';error=str(exc) if isinstance(exc,provider.Uncertain) else type(exc).__name__
  c=database.connect()
  try:c.execute("UPDATE homework_delivery_targets SET status=?,error=?,external_id=?,claim_token=NULL,updated_at=? WHERE item_id=? AND user_id=? AND channel=? AND status='CLAIMED' AND claim_token=?",(status,error,external,database.now_iso(),iid,t['user_id'],t['channel'],token));c.commit()
  finally:c.close()
 c=database.connect()
 try:states=[r['status'] for r in c.execute('SELECT status FROM homework_delivery_targets WHERE item_id=?',(iid,))]
 finally:c.close()
 return all(s=='SENT' for s in states),' '.join(s+':'+str(states.count(s)) for s in sorted(set(states)))
