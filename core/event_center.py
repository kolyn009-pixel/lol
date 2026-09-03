from datetime import datetime
import database
from .schema import ensure_schema

ORDER="CASE priority WHEN 'CRITICAL' THEN 0 WHEN 'ACTION' THEN 1 WHEN 'ATTENTION' THEN 2 ELSE 3 END"

def push(event_type,title,body='',priority='INFO',entity_type=None,entity_id=None,dedupe_key=None):
    ensure_schema(); conn=database.connect()
    conn.execute("""INSERT INTO admin_events(event_type,priority,title,body,entity_type,entity_id,dedupe_key,status,created_at)
                    VALUES(?,?,?,?,?,?,?,'OPEN',?) ON CONFLICT(dedupe_key) DO UPDATE SET priority=excluded.priority,title=excluded.title,body=excluded.body,status='OPEN',resolved_at=NULL""",
                 (event_type,priority,title,body,entity_type,str(entity_id) if entity_id is not None else None,dedupe_key,datetime.now().isoformat(timespec='seconds')))
    conn.commit(); conn.close()

def resolve(event_id):
    conn=database.connect(); conn.execute("UPDATE admin_events SET status='RESOLVED',resolved_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),int(event_id))); conn.commit(); conn.close()


def resolve_all_work_events():
    """Resolve non-system notification events without changing business entities."""
    system_types={'BOT_ERROR','STARTUP_BACKUP_ERROR','LEDGER_SYNC_ERROR','BACKUP_ERROR'}
    conn=database.connect()
    rows=conn.execute("SELECT id,event_type FROM admin_events WHERE status='OPEN'").fetchall()
    ids=[int(r['id']) for r in rows if r['event_type'] not in system_types and not str(r['event_type'] or '').endswith('_ERROR')]
    if ids:
        placeholders=','.join('?' for _ in ids)
        conn.execute(
            f"UPDATE admin_events SET status='RESOLVED',resolved_at=? WHERE id IN ({placeholders})",
            (datetime.now().isoformat(timespec='seconds'), *ids),
        )
    conn.commit(); conn.close(); return len(ids)

def open_events(limit=40):
    conn=database.connect(); rows=conn.execute(f"SELECT * FROM admin_events WHERE status='OPEN' ORDER BY {ORDER}, id DESC LIMIT ?",(int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]

def refresh_automatic():
    from core import minute_balance
    conn=database.connect()
    unpaid=conn.execute("SELECT COUNT(*) c FROM lessons WHERE lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT'").fetchone()['c']
    homework=conn.execute("SELECT COUNT(*) c FROM homework WHERE status IN ('SUBMITTED','WAITING_REVIEW')").fetchone()['c'] if _table_has(conn,'homework','status') else 0
    students=conn.execute("SELECT id,name FROM users WHERE active=1").fetchall()
    conn.close()
    for r in students:
        try:
            bal=minute_balance.get_balance(r['id'])['total']
            if bal<=120:
                push('LOW_BALANCE',f"Низкий баланс: {r['name']}",f"Осталось времени: {bal} мин",'ATTENTION','user',r['id'],f"low_balance:{r['id']}")
        except Exception:
            pass
    if unpaid: push('UNPAID','Есть неоплаченные занятия',f'Количество: {unpaid}','ACTION',dedupe_key='unpaid:current')
    if homework: push('HOMEWORK_REVIEW','ДЗ ждут проверки',f'Количество: {homework}','ACTION',dedupe_key='homework:review')

def _table_has(conn,table,col):
    try: return col in {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    except Exception: return False
