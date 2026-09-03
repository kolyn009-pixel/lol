from datetime import datetime
import os
import database
from .schema import ensure_schema


def run_checks():
    ensure_schema(); checks=[]; conn=database.connect()
    integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
    checks.append(('SQLite integrity','CRITICAL',integrity=='ok',integrity))
    bad_packages=conn.execute("SELECT COUNT(*) c FROM lesson_packages WHERE lessons_used<0 OR lessons_used>lessons_total").fetchone()['c']
    checks.append(('Баланс пакетов','CRITICAL',bad_packages==0,f'аномалий: {bad_packages}'))
    dup=conn.execute("""SELECT COUNT(*) c FROM (SELECT start_time,COUNT(*) n FROM lessons WHERE lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS') GROUP BY start_time HAVING n>1)""").fetchone()['c']
    checks.append(('Конфликты начала занятий','ATTENTION',dup==0,f'совпадений: {dup}'))
    cancelled_calendar=conn.execute("SELECT COUNT(*) c FROM lessons WHERE lesson_status IN ('CANCELLED','REJECTED','LATE_CANCELLED','SICKNESS') AND COALESCE(google_event_id,'')<>''").fetchone()['c']
    checks.append(('Отмененные события Calendar','ATTENTION',cancelled_calendar==0,f'локально с event_id: {cancelled_calendar}'))
    active_without_event=conn.execute("SELECT COUNT(*) c FROM lessons WHERE lesson_status='CONFIRMED' AND start_time>? AND (google_event_id IS NULL OR google_event_id='')",(datetime.now().isoformat(timespec='seconds'),)).fetchone()['c']
    checks.append(('Будущие занятия без Calendar ID','ATTENTION',active_without_event==0,f'количество: {active_without_event}'))
    fk=conn.execute('PRAGMA foreign_key_check').fetchall(); checks.append(('Foreign keys','CRITICAL',not fk,f'ошибок: {len(fk)}'))
    conn.close()
    for name,severity,ok,details in checks:
        c=database.connect(); c.execute('INSERT INTO system_diagnostics(check_name,severity,ok,details,created_at) VALUES(?,?,?,?,?)',(name,severity,1 if ok else 0,details,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close()
    return checks
