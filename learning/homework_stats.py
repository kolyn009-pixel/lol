from . import schema
import sqlite3

def stats(user_id,db_path=schema.DB_PATH):
 conn=sqlite3.connect(db_path);conn.row_factory=sqlite3.Row;c=conn.cursor();c.execute('''SELECT COUNT(*) total,SUM(CASE WHEN status IN ('DONE','APPROVED','REVIEWED') THEN 1 ELSE 0 END) done,SUM(CASE WHEN status IN ('ASSIGNED','REVISION') AND deadline IS NOT NULL AND datetime(deadline)<datetime('now') THEN 1 ELSE 0 END) overdue,SUM(CASE WHEN status='REVISION' THEN 1 ELSE 0 END) revision FROM homework WHERE user_id=?''',(user_id,));r=c.fetchone();conn.close();return dict(r) if r else {}
