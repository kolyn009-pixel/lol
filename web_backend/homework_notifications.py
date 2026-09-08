"""Durable homework notification outbox shared by WEB/TG/VK."""
import json
from database import connect,now_iso

def ensure_tables():
 conn=connect();conn.executescript("""CREATE TABLE IF NOT EXISTS homework_notification_outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe_key TEXT NOT NULL UNIQUE,recipient_type TEXT NOT NULL,user_id INTEGER,event_type TEXT NOT NULL,text TEXT NOT NULL,action_url TEXT,action_label TEXT,payload_json TEXT,status TEXT NOT NULL DEFAULT 'PENDING',attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,claimed_at TEXT,delivered_at TEXT,last_error TEXT);CREATE INDEX IF NOT EXISTS idx_hw_notify_pending ON homework_notification_outbox(status,created_at);""");conn.commit();conn.close()
def enqueue(dedupe_key,recipient_type,event_type,text,user_id=None,action_url=None,action_label=None,payload=None):
 ensure_tables();conn=connect();cur=conn.execute("INSERT OR IGNORE INTO homework_notification_outbox(dedupe_key,recipient_type,user_id,event_type,text,action_url,action_label,payload_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,'PENDING',?)",(str(dedupe_key),str(recipient_type).upper(),int(user_id) if user_id is not None else None,str(event_type).upper(),str(text),action_url,action_label,json.dumps(payload or {},ensure_ascii=False),now_iso()));conn.commit();created=cur.rowcount>0;conn.close();return created
def enqueue_external_reminder(item):
 title=item.get('title') or 'Домашнее задание';provider=item.get('provider') or 'EXTERNAL';return enqueue(f"ext-reminder:{item['homework_id']}:{item['user_id']}",'STUDENT','EXTERNAL_HOMEWORK_REMINDER',f"💜 Ты открывал домашнее задание «{title}». Уже закончил?",item['user_id'],f"/app/?homework={item['homework_id']}",'Открыть ДЗ',{'homework_id':item['homework_id'],'provider':provider,'buttons':['DONE','WORKING','NEED_MORE_TIME']})
def enqueue_teacher_external_status(homework_id,user_id,status,name,title,external_url):
 labels={'DONE':'закончил(а) ДЗ','WORKING':'ещё решает ДЗ','NEED_MORE_TIME':'нужно больше времени на ДЗ'};label=labels.get(str(status).upper(),'обновил(а) статус ДЗ');return enqueue(f'ext-status:{homework_id}:{user_id}:{status}','TEACHER','EXTERNAL_HOMEWORK_STATUS',f"📚 {name} {label}\n\n{title or 'Домашнее задание'}",user_id,external_url,'Открыть вариант',{'homework_id':int(homework_id),'student_id':int(user_id),'student_status':str(status).upper()})
def enqueue_teacher_auto_result(homework_id,user_id,name,result,teacher_url=None,attempt_number=None):
 attempt=int(attempt_number or result.get('attempt_number') or 1);percent=float(result.get('score_percent',0) or 0);correct=int(result.get('correct_tasks',0) or 0);total=int(result.get('total_tasks',0) or 0);earned=float(result.get('earned_points',0) or 0);points=float(result.get('total_points',0) or 0);return enqueue(f'auto-result:{homework_id}:{user_id}:{attempt}','TEACHER','INTERACTIVE_HOMEWORK_RESULT',f'✅ {name} сдал(а) интерактивное ДЗ\n\nПопытка: {attempt}\nРезультат: {correct}/{total} · {percent:g}%\nБаллы: {earned:g}/{points:g}',user_id,teacher_url or f'/teacher/?homework={homework_id}&student={user_id}&attempt={attempt}','Открыть результат',{'homework_id':int(homework_id),'student_id':int(user_id),'attempt_number':attempt,'result':result})
def pending(limit=100):
 ensure_tables();conn=connect();rows=conn.execute("SELECT * FROM homework_notification_outbox WHERE status='PENDING' ORDER BY id LIMIT ?",(int(limit),)).fetchall();conn.close();return [dict(r) for r in rows]
def mark_delivered(item_id):
 ensure_tables();conn=connect();conn.execute("UPDATE homework_notification_outbox SET status='DELIVERED',delivered_at=?,last_error=NULL WHERE id=?",(now_iso(),int(item_id)));conn.commit();conn.close()
def mark_failed(item_id,error):
 ensure_tables();conn=connect();conn.execute('UPDATE homework_notification_outbox SET attempts=attempts+1,last_error=? WHERE id=?',(str(error)[:500],int(item_id)));conn.commit();conn.close()
