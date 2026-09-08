"""Durable homework notification outbox shared by WEB/TG/VK.

Workers atomically claim rows with a lease. Failed deliveries are rescheduled
with exponential backoff; abandoned claims become eligible after the lease.
"""
import json
from datetime import datetime,timedelta
from database import connect,now_iso

LEASE_SECONDS=120
MAX_ATTEMPTS=8

def ensure_tables():
 conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS homework_notification_outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe_key TEXT NOT NULL UNIQUE,recipient_type TEXT NOT NULL,user_id INTEGER,event_type TEXT NOT NULL,text TEXT NOT NULL,action_url TEXT,action_label TEXT,payload_json TEXT,status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,claimed_at TEXT,delivered_at TEXT,last_error TEXT,next_attempt_at TEXT);CREATE INDEX IF NOT EXISTS idx_hw_notify_pending ON homework_notification_outbox(status,next_attempt_at,created_at);""");cols={r['name'] for r in conn.execute('PRAGMA table_info(homework_notification_outbox)').fetchall()}
 if 'next_attempt_at' not in cols:conn.execute('ALTER TABLE homework_notification_outbox ADD COLUMN next_attempt_at TEXT')
 conn.commit();conn.close()
def enqueue(dedupe_key,recipient_type,event_type,text,user_id=None,action_url=None,action_label=None,payload=None):
 ensure_tables();conn=connect();cur=conn.execute("INSERT OR IGNORE INTO homework_notification_outbox(dedupe_key,recipient_type,user_id,event_type,text,action_url,action_label,payload_json,status,created_at,next_attempt_at) VALUES(?,?,?,?,?,?,?,?,'PENDING',?,?)",(str(dedupe_key),str(recipient_type).upper(),int(user_id) if user_id is not None else None,str(event_type).upper(),str(text),action_url,action_label,json.dumps(payload or {},ensure_ascii=False),now_iso(),now_iso()));conn.commit();created=cur.rowcount>0;conn.close();return created
def enqueue_external_reminder(item):
 title=item.get('title') or 'Домашнее задание';provider=item.get('provider') or 'EXTERNAL';return enqueue(f"ext-reminder:{item['homework_id']}:{item['user_id']}",'STUDENT','EXTERNAL_HOMEWORK_REMINDER',f"💜 Ты открывал домашнее задание «{title}». Уже закончил?",item['user_id'],f"/app/?homework={item['homework_id']}",'Открыть ДЗ',{'homework_id':item['homework_id'],'provider':provider,'buttons':['DONE','WORKING','NEED_MORE_TIME']})
def enqueue_teacher_external_status(homework_id,user_id,status,name,title,external_url):
 labels={'DONE':'закончил(а) ДЗ','WORKING':'ещё решает ДЗ','NEED_MORE_TIME':'нужно больше времени на ДЗ'};label=labels.get(str(status).upper(),'обновил(а) статус ДЗ');return enqueue(f'ext-status:{homework_id}:{user_id}:{status}','TEACHER','EXTERNAL_HOMEWORK_STATUS',f"📚 {name} {label}\n\n{title or 'Домашнее задание'}",user_id,external_url,'Открыть вариант',{'homework_id':int(homework_id),'student_id':int(user_id),'student_status':str(status).upper()})
def enqueue_teacher_auto_result(homework_id,user_id,name,result,teacher_url=None,attempt_number=None):
 attempt=int(attempt_number or result.get('attempt_number') or 1);percent=float(result.get('score_percent',0) or 0);correct=int(result.get('correct_tasks',0) or 0);total=int(result.get('total_tasks',0) or 0);earned=float(result.get('earned_points',0) or 0);points=float(result.get('total_points',0) or 0);return enqueue(f'auto-result:{homework_id}:{user_id}:{attempt}','TEACHER','INTERACTIVE_HOMEWORK_RESULT',f'✅ {name} сдал(а) интерактивное ДЗ\n\nПопытка: {attempt}\nРезультат: {correct}/{total} · {percent:g}%\nБаллы: {earned:g}/{points:g}',user_id,teacher_url or f'/teacher/?homework={homework_id}&student={user_id}&attempt={attempt}','Открыть результат',{'homework_id':int(homework_id),'student_id':int(user_id),'attempt_number':attempt,'result':result})
def claim_pending(limit=100,lease_seconds=LEASE_SECONDS):
 ensure_tables();conn=connect();now=now_iso();lease_cutoff=(datetime.now()-timedelta(seconds=int(lease_seconds))).isoformat(timespec='seconds')
 try:
  conn.execute('BEGIN IMMEDIATE')
  rows=conn.execute("SELECT id FROM homework_notification_outbox WHERE attempts<? AND (status='PENDING' OR (status='CLAIMED' AND claimed_at<?)) AND (next_attempt_at IS NULL OR datetime(next_attempt_at)<=datetime('now')) ORDER BY id LIMIT ?",(MAX_ATTEMPTS,lease_cutoff,int(limit))).fetchall();ids=[int(r['id']) for r in rows]
  if ids:
   marks=','.join('?' for _ in ids);conn.execute(f"UPDATE homework_notification_outbox SET status='CLAIMED',claimed_at=? WHERE id IN ({marks})",(now,*ids));items=conn.execute(f"SELECT * FROM homework_notification_outbox WHERE id IN ({marks}) ORDER BY id",ids).fetchall()
  else:items=[]
  conn.commit();return [dict(r) for r in items]
 except Exception:conn.rollback();raise
 finally:conn.close()
def pending(limit=100):return claim_pending(limit)
def mark_delivered(item_id):
 ensure_tables();conn=connect();conn.execute("UPDATE homework_notification_outbox SET status='DELIVERED',delivered_at=?,claimed_at=NULL,last_error=NULL,next_attempt_at=NULL WHERE id=? AND status='CLAIMED'",(now_iso(),int(item_id)));conn.commit();conn.close()
def mark_failed(item_id,error):
 ensure_tables();conn=connect();row=conn.execute('SELECT attempts FROM homework_notification_outbox WHERE id=?',(int(item_id),)).fetchone();attempts=(int(row['attempts']) if row else 0)+1;delay=min(3600,30*(2**max(0,attempts-1)));next_at=(datetime.now()+timedelta(seconds=delay)).isoformat(timespec='seconds');status='FAILED' if attempts>=MAX_ATTEMPTS else 'PENDING';conn.execute('UPDATE homework_notification_outbox SET status=?,attempts=?,claimed_at=NULL,last_error=?,next_attempt_at=? WHERE id=?',(status,attempts,str(error)[:500],next_at,int(item_id)));conn.commit();conn.close()
