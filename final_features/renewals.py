from __future__ import annotations
from datetime import datetime,timedelta
import database
from core import minute_balance
from .tariffs import package_quote


def recommendation(user_id, program_id):
    base=minute_balance.get_program_duration(program_id); rate=minute_balance.effective_hourly_rate(program_id); bal=minute_balance.get_balance(user_id,rate)['total']
    c=database.connect()
    try:
        rows=c.execute("SELECT duration_minutes FROM lessons WHERE user_id=? AND program_id=? AND cancelled_at IS NULL AND finished_at IS NULL AND datetime(start_time)>=datetime('now') ORDER BY datetime(start_time) LIMIT 20",(int(user_id),int(program_id))).fetchall()
    finally:c.close()
    reserved=sum(int(r['duration_minutes'] or base) for r in rows)
    net=max(0,bal-reserved)
    # Recommend enough for roughly 4 weeks at the observed future cadence, minimum 5 standard lessons.
    observed=max(5,min(20,len(rows) if rows else 10)); quote=package_quote(program_id,observed)
    return {'balance':bal,'reserved':reserved,'available_after_bookings':net,'quote':quote}
