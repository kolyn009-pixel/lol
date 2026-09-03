from . import schema
import sqlite3
from datetime import datetime,date

def add(user_id,subject,test_score,primary_score=None,exam_type='EGE',exam_date=None,notes=None,db_path=schema.DB_PATH):
 schema.initialize(db_path);conn=sqlite3.connect(db_path);c=conn.cursor();c.execute('INSERT INTO exam_results(user_id,subject,exam_type,exam_date,primary_score,test_score,notes,created_at) VALUES(?,?,?,?,?,?,?,?)',(user_id,subject,exam_type,exam_date or date.today().isoformat(),primary_score,test_score,notes,datetime.now().isoformat(timespec='seconds')));conn.commit();conn.close()

def history(user_id,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row;c=conn.cursor();c.execute('SELECT * FROM exam_results WHERE user_id=? ORDER BY exam_date',(user_id,));r=c.fetchall();conn.close();return r
