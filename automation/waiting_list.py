from datetime import datetime
import database


def add(student_id, subject=None, study_goal=None, preferred_date=None, preferred_from=None, preferred_to=None, note=None):
    conn=database.connect(); cur=conn.cursor()
    cur.execute('''INSERT INTO waiting_list(student_id,subject,study_goal,preferred_date,preferred_from,preferred_to,note,status,created_at)
                   VALUES(?,?,?,?,?,?,?,'ACTIVE',?)''',(student_id,subject,study_goal,preferred_date,preferred_from,preferred_to,note,datetime.now().isoformat(timespec='seconds')))
    conn.commit(); rid=cur.lastrowid; conn.close(); return rid


def active(student_id=None):
    conn=database.connect();
    if student_id:
        rows=conn.execute("SELECT * FROM waiting_list WHERE status='ACTIVE' AND student_id=? ORDER BY created_at",(student_id,)).fetchall()
    else:
        rows=conn.execute("SELECT w.*,u.name,u.telegram_id FROM waiting_list w JOIN users u ON u.id=w.student_id WHERE w.status='ACTIVE' ORDER BY w.preferred_date,w.created_at").fetchall()
    conn.close(); return rows


def close(wait_id):
    conn=database.connect(); conn.execute("UPDATE waiting_list SET status='CLOSED' WHERE id=?",(wait_id,)); conn.commit(); conn.close()


def candidates(date_text, time_text=None, subject=None):
    conn=database.connect()
    sql="""SELECT w.*,u.name,u.telegram_id FROM waiting_list w JOIN users u ON u.id=w.student_id
           WHERE w.status='ACTIVE' AND (w.preferred_date IS NULL OR w.preferred_date='' OR w.preferred_date=?)"""
    params=[date_text]
    if subject:
        sql += " AND (w.subject IS NULL OR w.subject='' OR w.subject=?)"; params.append(subject)
    rows=conn.execute(sql,params).fetchall(); conn.close()
    if not time_text: return rows
    out=[]
    for r in rows:
        lo=r['preferred_from']; hi=r['preferred_to']
        if (not lo or time_text>=lo) and (not hi or time_text<=hi): out.append(r)
    return out
