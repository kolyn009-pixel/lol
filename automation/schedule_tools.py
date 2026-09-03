from datetime import datetime
import database


def add_pause(student_id,date_from,date_to,reason=None,created_by=None):
    conn=database.connect(); cur=conn.cursor(); cur.execute('INSERT INTO student_pauses(student_id,date_from,date_to,reason,active,created_by,created_at) VALUES(?,?,?,?,1,?,?)',(student_id,date_from,date_to,reason,created_by,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid


def is_paused(student_id,date_text):
    conn=database.connect(); row=conn.execute('SELECT 1 FROM student_pauses WHERE student_id=? AND active=1 AND date_from<=? AND date_to>=? LIMIT 1',(student_id,date_text,date_text)).fetchone(); conn.close(); return bool(row)


def add_teacher_absence(date_from,date_to,reason=None,mode='SICK',created_by=None):
    conn=database.connect(); cur=conn.cursor(); cur.execute('INSERT INTO teacher_absences(date_from,date_to,reason,mode,active,created_by,created_at) VALUES(?,?,?,?,1,?,?)',(date_from,date_to,reason,mode,created_by,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid


def affected_lessons(date_from,date_to):
    conn=database.connect(); rows=conn.execute("SELECT l.*,u.name,u.telegram_id FROM lessons l JOIN users u ON u.id=l.user_id WHERE substr(l.start_time,1,10) BETWEEN ? AND ? AND l.lesson_status IN ('CONFIRMED','PENDING') ORDER BY datetime(l.start_time)",(date_from,date_to)).fetchall(); conn.close(); return rows


def create_group(name,subject=None,study_goal=None):
    conn=database.connect(); cur=conn.cursor(); cur.execute('INSERT INTO lesson_groups(name,subject,study_goal,active,created_at) VALUES(?,?,?,1,?)',(name,subject,study_goal,datetime.now().isoformat(timespec='seconds'))); conn.commit(); gid=cur.lastrowid; conn.close(); return gid


def add_group_member(group_id,student_id,individual_price=None):
    conn=database.connect(); conn.execute('INSERT INTO lesson_group_members(group_id,student_id,individual_price,active) VALUES(?,?,?,1) ON CONFLICT(group_id,student_id) DO UPDATE SET individual_price=excluded.individual_price,active=1',(group_id,student_id,individual_price)); conn.commit(); conn.close()
