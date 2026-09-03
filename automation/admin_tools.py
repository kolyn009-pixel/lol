from datetime import datetime
import database


def add_tag(student_id, tag):
    tag=tag.strip().lower()
    conn=database.connect(); conn.execute('INSERT OR IGNORE INTO student_tags(student_id,tag,created_at) VALUES(?,?,?)',(student_id,tag,datetime.now().isoformat(timespec='seconds'))); conn.commit(); conn.close()


def tags(student_id):
    conn=database.connect(); rows=conn.execute('SELECT tag FROM student_tags WHERE student_id=? ORDER BY tag',(student_id,)).fetchall(); conn.close(); return [r['tag'] for r in rows]


def save_template(name,text,actor=None):
    conn=database.connect(); conn.execute('''INSERT INTO message_templates(name,text,created_by,updated_at) VALUES(?,?,?,?) ON CONFLICT(name) DO UPDATE SET text=excluded.text,created_by=excluded.created_by,updated_at=excluded.updated_at''',(name.strip(),text,actor,datetime.now().isoformat(timespec='seconds'))); conn.commit(); conn.close()


def templates():
    conn=database.connect(); rows=conn.execute('SELECT * FROM message_templates ORDER BY name').fetchall(); conn.close(); return rows


def add_period(name,date_from,date_to):
    conn=database.connect(); cur=conn.cursor(); cur.execute('INSERT INTO academic_periods(name,date_from,date_to,created_at) VALUES(?,?,?,?)',(name,date_from,date_to,datetime.now().isoformat(timespec='seconds'))); conn.commit(); rid=cur.lastrowid; conn.close(); return rid
