from datetime import datetime
import database


def add(student_id,event_type,title,details=None,source_type=None,source_id=None,created_at=None):
    conn=database.connect(); conn.execute('''INSERT INTO student_timeline(student_id,event_type,title,details,source_type,source_id,created_at) VALUES(?,?,?,?,?,?,?)''',(student_id,event_type,title,details,source_type,source_id,created_at or datetime.now().isoformat(timespec='seconds'))); conn.commit(); conn.close()


def recent(student_id,limit=50):
    conn=database.connect(); rows=conn.execute('SELECT * FROM student_timeline WHERE student_id=? ORDER BY created_at DESC LIMIT ?',(student_id,limit)).fetchall(); conn.close(); return rows


def rebuild_basic(student_id=None):
    conn=database.connect(); students=[student_id] if student_id else [r['id'] for r in conn.execute('SELECT id FROM users').fetchall()]
    added=0
    for sid in students:
        existing={(r['source_type'],r['source_id']) for r in conn.execute('SELECT source_type,source_id FROM student_timeline WHERE student_id=?',(sid,)).fetchall() if r['source_type'] and r['source_id']}
        for r in conn.execute('SELECT id,start_time,lesson_status,subject FROM lessons WHERE user_id=?',(sid,)).fetchall():
            key=('lesson',r['id'])
            if key not in existing:
                conn.execute('INSERT INTO student_timeline(student_id,event_type,title,details,source_type,source_id,created_at) VALUES(?,?,?,?,?,?,?)',(sid,'LESSON',f"Занятие: {r['subject'] or 'без предмета'}",r['lesson_status'],'lesson',r['id'],r['start_time'])); added+=1
        for r in conn.execute('SELECT id,total_amount,status,created_at FROM payments WHERE user_id=?',(sid,)).fetchall():
            key=('payment',r['id'])
            if key not in existing:
                conn.execute('INSERT INTO student_timeline(student_id,event_type,title,details,source_type,source_id,created_at) VALUES(?,?,?,?,?,?,?)',(sid,'PAYMENT','Оплата',f"{r['total_amount']} ₽ · {r['status']}",'payment',r['id'],r['created_at'] or datetime.now().isoformat(timespec='seconds'))); added+=1
    conn.commit(); conn.close(); return added
