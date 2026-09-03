from __future__ import annotations
from datetime import date,datetime,timedelta
import database
from core import minute_balance


def finance(month=None):
    d=date.today() if month is None else datetime.strptime(month+'-01','%Y-%m-%d').date(); start=d.replace(day=1); end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
    c=database.connect()
    try:
        earned=c.execute("SELECT COALESCE(SUM(price),0) s FROM lessons WHERE finished_at>=? AND finished_at<? AND cancelled_at IS NULL",(start.isoformat(),end.isoformat())).fetchone()['s'] or 0
        received=c.execute("SELECT COALESCE(SUM(total_amount),0) s FROM payments WHERE status IN ('PAID','CONFIRMED') AND confirmed_at>=? AND confirmed_at<?",(start.isoformat(),end.isoformat())).fetchone()['s'] or 0
        future=c.execute("SELECT COALESCE(SUM(price),0) s,COALESCE(SUM(duration_minutes),0) m FROM lessons WHERE cancelled_at IS NULL AND finished_at IS NULL AND start_time>=? AND start_time<?",(datetime.now().isoformat(timespec='seconds'),end.isoformat())).fetchone()
        students=c.execute("SELECT COUNT(*) n FROM users WHERE active=1").fetchone()['n']
        return {'received':int(received),'earned':int(earned),'future_earned':int(future['s'] or 0),'future_minutes':int(future['m'] or 0),'projected_earned':int(earned)+int(future['s'] or 0),'prepaid':minute_balance.prepaid_value_rubles(),'active_students':int(students or 0)}
    finally:c.close()
