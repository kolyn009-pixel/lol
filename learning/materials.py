from . import schema
import sqlite3
from datetime import datetime

def add(title,subject,material_type='LINK',url=None,telegram_file_id=None,study_goal=None,grade=None,section=None,topic=None,description=None,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);c=conn.cursor();c.execute('INSERT INTO learning_materials(title,subject,study_goal,grade,section,topic,material_type,telegram_file_id,url,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(title,subject,study_goal,grade,section,topic,material_type,telegram_file_id,url,description,datetime.now().isoformat(timespec='seconds')));i=c.lastrowid;conn.commit();conn.close();return i
