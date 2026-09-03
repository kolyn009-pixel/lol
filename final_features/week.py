from __future__ import annotations
from datetime import date,timedelta,datetime
import database


def _hm(s):
    h,m=map(int,str(s).split(':')[:2]); return h*60+m

def view(anchor=None):
    d=anchor or date.today(); start=d-timedelta(days=d.weekday()); end=start+timedelta(days=7); c=database.connect()
    try:
        rows=c.execute("SELECT l.*,u.name FROM lessons l JOIN users u ON u.id=l.user_id WHERE date(l.start_time)>=? AND date(l.start_time)<? AND l.cancelled_at IS NULL ORDER BY datetime(l.start_time)",(start.isoformat(),end.isoformat())).fetchall()
        by={i:[] for i in range(7)}; total_min=plan=0
        for r in rows:
            dt=datetime.fromisoformat(r['start_time']); by[dt.weekday()].append(r); total_min+=int(r['duration_minutes'] or 0); plan+=int(r['price'] or 0)
        capacity=0
        for offset in range(7):
            day=start+timedelta(days=offset)
            for r in database.get_effective_working_hours(day):
                capacity += max(0,_hm(r['end_time'])-_hm(r['start_time']))
        free=max(0,capacity-total_min)
        return start,end,by,total_min,plan,capacity,free
    finally:c.close()
