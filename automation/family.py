import database
from .balance_forecast import forecast


def dashboard(parent_id):
    students=database.get_parent_students(parent_id)
    result=[]
    for s in students:
        try: fc=forecast(s['id'])
        except Exception: fc={'remaining':0,'through':None}
        conn=database.connect(); nxt=conn.execute("SELECT * FROM lessons WHERE user_id=? AND lesson_status IN ('CONFIRMED','PENDING') AND datetime(start_time)>=datetime('now','localtime') ORDER BY datetime(start_time) LIMIT 1",(s['id'],)).fetchone(); conn.close()
        result.append({'student':dict(s),'forecast':fc,'next_lesson':dict(nxt) if nxt else None})
    return result
