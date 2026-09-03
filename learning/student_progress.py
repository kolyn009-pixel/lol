from . import schema
import sqlite3
from datetime import datetime

def set_goal(user_id,subject,target_text,target_score=None,target_date=None,study_goal=None,db_path=schema.DB_PATH):
 schema.initialize(db_path);now=datetime.now().isoformat(timespec='seconds');conn=sqlite3.connect(db_path);c=conn.cursor();c.execute("UPDATE student_goals SET status='ARCHIVED',updated_at=? WHERE user_id=? AND subject=? AND status='ACTIVE'",(now,user_id,subject));c.execute('INSERT INTO student_goals(user_id,subject,study_goal,target_text,target_score,target_date,status,created_at,updated_at) VALUES(?,?,?,?,?,?,\'ACTIVE\',?,?)',(user_id,subject,study_goal,target_text,target_score,target_date,now,now));conn.commit();conn.close()

def get_goal(user_id,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row;c=conn.cursor();c.execute("SELECT * FROM student_goals WHERE user_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(user_id,));r=c.fetchone();conn.close();return r
