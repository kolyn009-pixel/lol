from __future__ import annotations
from datetime import datetime
import database
from . import schema


def request(student_id, lesson_id=None, desired_date=None, desired_from=None, desired_to=None, min_duration=None):
    schema.initialize(); c=database.connect(); now=datetime.now().isoformat(timespec='seconds')
    try:
        cur=c.execute('INSERT INTO reschedule_exchange_requests(student_id,lesson_id,desired_date,desired_from,desired_to,min_duration_minutes,status,created_at) VALUES(?,?,?,?,?,?,?,?)',(int(student_id),lesson_id,desired_date,desired_from,desired_to,min_duration,'OPEN',now)); c.commit(); return cur.lastrowid
    finally:c.close()

def candidates(req_id):
    schema.initialize(); c=database.connect()
    try:
        r=c.execute('SELECT * FROM reschedule_exchange_requests WHERE id=?',(int(req_id),)).fetchone()
        if not r:return []
        sql="SELECT * FROM reschedule_exchange_requests WHERE status='OPEN' AND id<>? AND student_id<>?"
        params=[int(req_id),r['student_id']]
        if r['desired_date']: sql+=' AND desired_date=?'; params.append(r['desired_date'])
        return c.execute(sql+' ORDER BY created_at LIMIT 20',params).fetchall()
    finally:c.close()
