import secrets
from datetime import datetime
import database


def get_or_create(student_id,reward_lessons=1):
    conn=database.connect(); row=conn.execute("SELECT * FROM referrals WHERE referrer_student_id=? AND status='ACTIVE' ORDER BY id DESC LIMIT 1",(student_id,)).fetchone()
    if row: conn.close(); return row
    code='REF-'+secrets.token_hex(3).upper(); cur=conn.cursor(); cur.execute("INSERT INTO referrals(referrer_student_id,code,status,reward_lessons,created_at) VALUES(?,?,'ACTIVE',?,?)",(student_id,code,reward_lessons,datetime.now().isoformat(timespec='seconds'))); conn.commit(); row=conn.execute('SELECT * FROM referrals WHERE id=?',(cur.lastrowid,)).fetchone(); conn.close(); return row


def claim(code,student_id):
    conn=database.connect(); row=conn.execute("SELECT * FROM referrals WHERE code=? AND status='ACTIVE'",(code.strip().upper(),)).fetchone()
    if not row: conn.close(); return False,'Код не найден'
    if row['referrer_student_id']==student_id: conn.close(); return False,'Нельзя использовать свой код'
    if row['invited_student_id']: conn.close(); return False,'Код уже использован'
    conn.execute("UPDATE referrals SET invited_student_id=?,status='CLAIMED' WHERE id=?",(student_id,row['id'])); conn.commit(); conn.close(); return True,row
