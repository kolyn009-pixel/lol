from __future__ import annotations
import database
from automation.operations import attention_items
from .reconcile import run as reconcile
from .forecast import finance


def dashboard():
    c=database.connect()
    try:
        students=c.execute('SELECT COUNT(*) n FROM users WHERE active=1').fetchone()['n']
        seven=c.execute("SELECT COUNT(*) n,COALESCE(SUM(duration_minutes),0) mins FROM lessons WHERE cancelled_at IS NULL AND datetime(start_time)>=datetime('now') AND datetime(start_time)<datetime('now','+7 days')").fetchone()
        pending_pay=c.execute("SELECT COUNT(*) n FROM payments WHERE status IN ('WAITING','RECEIVED')").fetchone()['n']
    finally:c.close()
    issues=reconcile(); fin=finance(); return {'students':students,'lessons7':seven['n'],'minutes7':seven['mins'],'pending_payments':pending_pay,'issues':issues,'attention':attention_items(),'finance':fin}
