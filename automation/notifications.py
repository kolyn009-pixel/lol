from datetime import datetime
import database

DEFAULTS={'remind_24h':1,'remind_2h':1,'remind_30m':0,'remind_10m':0,'schedule_changes':1,'payments':1,'monthly_report':1}


def get(parent_id,student_id):
    conn=database.connect(); row=conn.execute('SELECT * FROM parent_notification_settings WHERE parent_id=? AND student_id=?',(parent_id,student_id)).fetchone(); conn.close()
    return dict(row) if row else {'parent_id':parent_id,'student_id':student_id,**DEFAULTS}


def set_option(parent_id,student_id,key,value):
    if key not in DEFAULTS: raise ValueError('Unknown option')
    current=get(parent_id,student_id); current[key]=1 if value else 0
    conn=database.connect(); conn.execute('''INSERT INTO parent_notification_settings(parent_id,student_id,remind_24h,remind_2h,remind_30m,remind_10m,schedule_changes,payments,monthly_report,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(parent_id,student_id) DO UPDATE SET remind_24h=excluded.remind_24h,remind_2h=excluded.remind_2h,remind_30m=excluded.remind_30m,remind_10m=excluded.remind_10m,schedule_changes=excluded.schedule_changes,payments=excluded.payments,monthly_report=excluded.monthly_report,updated_at=excluded.updated_at''',(
        parent_id,student_id,current['remind_24h'],current['remind_2h'],current['remind_30m'],current['remind_10m'],current['schedule_changes'],current['payments'],current['monthly_report'],datetime.now().isoformat(timespec='seconds')))
    conn.commit(); conn.close(); return current
