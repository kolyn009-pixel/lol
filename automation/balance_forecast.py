import database
from core import minute_balance


def _package_rows(student_id):
    minute_balance.ensure_schema()
    c=database.connect()
    rows=c.execute('''SELECT hourly_rate,
                             SUM(MAX(COALESCE(minutes_total,0)-COALESCE(minutes_used,0),0)) remaining_minutes
                      FROM lesson_packages
                      WHERE user_id=? AND status='ACTIVE' AND source_type!='BONUS'
                      GROUP BY hourly_rate ORDER BY hourly_rate''',(student_id,)).fetchall()
    c.close(); return rows


def forecast(student_id):
    by_rate=minute_balance.get_balance_by_rate(student_id)
    total_minutes=sum(int(x['total'] or 0) for x in by_rate.values())
    conn=database.connect()
    future=conn.execute('''SELECT start_time,duration_minutes FROM lessons WHERE user_id=? AND lesson_status IN ('CONFIRMED','PENDING')
                           AND datetime(start_time) >= datetime('now','localtime') ORDER BY datetime(start_time)''',(student_id,)).fetchall()
    conn.close()
    remaining=total_minutes
    through=None
    for row in future:
        need=int(row['duration_minutes'] or 0)
        if remaining < need: break
        remaining -= need
        through=str(row['start_time'])[:10]
    return {
        'remaining': total_minutes,  # legacy key, now minutes
        'remaining_minutes': total_minutes,
        'through': through,
        'upcoming_count': len(future),
        'nominals':[{'hourly_rate':rate,**item} for rate,item in by_rate.items()],
    }
