from __future__ import annotations
from datetime import datetime
import sqlite3
import database
from core import minute_balance
from . import schema,ledger


def run():
    schema.initialize(); issues=[]; c=database.connect()
    try:
        # Negative or overused packages
        for r in c.execute("SELECT id,user_id,minutes_total,minutes_used FROM lesson_packages WHERE COALESCE(minutes_used,0)<0 OR COALESCE(minutes_used,0)>COALESCE(minutes_total,0)"):
            issues.append(('CRITICAL','PACKAGE_RANGE',f"Пакет #{r['id']}: used={r['minutes_used']} total={r['minutes_total']}",r['user_id']))
        # Completed lessons must have minute reservation/charge unless free/trial.
        for r in c.execute("SELECT id,user_id,reserved_minutes,is_trial,payment_status FROM lessons WHERE finished_at IS NOT NULL AND cancelled_at IS NULL"):
            if not r['is_trial'] and int(r['reserved_minutes'] or 0)<=0 and str(r['payment_status'] or '') not in ('PAID','FREE','TRIAL'):
                issues.append(('ATTENTION','COMPLETED_NO_MINUTES',f"Занятие #{r['id']} завершено без минутного списания",r['user_id']))
        # Cancelled lessons should have no active minute charges.
        for r in c.execute('''SELECT l.id,l.user_id,COALESCE(SUM(CASE WHEN mc.refunded=0 THEN mc.minutes ELSE 0 END),0) active
                              FROM lessons l LEFT JOIN lesson_minute_charges mc ON mc.lesson_id=l.id
                              WHERE l.cancelled_at IS NOT NULL GROUP BY l.id HAVING active>0'''):
            issues.append(('CRITICAL','CANCELLED_CHARGED',f"Отменённое занятие #{r['id']} удерживает {r['active']} мин",r['user_id']))
        # Confirmed payments should have minute metadata.
        for r in c.execute("SELECT id,user_id,minutes_total FROM payments WHERE status IN ('PAID','CONFIRMED') AND payment_type!='BONUS' AND COALESCE(minutes_total,0)<=0"):
            issues.append(('ATTENTION','PAYMENT_NO_MINUTES',f"Оплата #{r['id']} подтверждена без minutes_total",r['user_id']))
        # Calendar: cancelled event id is an issue until cleanup.
        for r in c.execute("SELECT id,user_id,google_event_id FROM lessons WHERE cancelled_at IS NOT NULL AND google_event_id IS NOT NULL"):
            issues.append(('INFO','CANCELLED_CALENDAR',f"Отменённое занятие #{r['id']} ещё имеет Calendar ID",r['user_id']))
        now=datetime.now().isoformat(timespec='seconds'); status='OK' if not [i for i in issues if i[0] in ('CRITICAL','ATTENTION')] else 'ISSUES'
        c.execute('INSERT INTO health_check_runs(check_type,status,details,created_at) VALUES(?,?,?,?)',('BUSINESS_RECONCILIATION',status,f'{len(issues)} issues',now)); c.commit()
    finally:c.close()
    return issues
