from . import schema
import sqlite3
from datetime import datetime

def save(lesson_id,user_id,text,db_path=schema.DB_PATH):
 now=datetime.now().isoformat(timespec='seconds');conn=sqlite3.connect(db_path);c=conn.cursor();c.execute('''INSERT INTO lesson_plans(lesson_id,user_id,plan_text,created_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(lesson_id) DO UPDATE SET plan_text=excluded.plan_text,updated_at=excluded.updated_at''',(lesson_id,user_id,text,now,now));conn.commit();conn.close()
