from . import schema
import sqlite3
from datetime import datetime

def add(user_id,subject,mode='QUICK',study_goal=None,score=None,target_score=None,summary=None,db_path=schema.DB_PATH):
 schema.initialize(db_path);conn=sqlite3.connect(db_path);c=conn.cursor();c.execute('INSERT INTO learning_diagnostics(user_id,mode,subject,study_goal,score,target_score,summary,created_at) VALUES(?,?,?,?,?,?,?,?)',(user_id,mode,subject,study_goal,score,target_score,summary,datetime.now().isoformat(timespec='seconds')));i=c.lastrowid;conn.commit();conn.close();return i
