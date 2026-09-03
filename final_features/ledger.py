from __future__ import annotations
from datetime import datetime
import database
from . import schema


def now(): return datetime.now().isoformat(timespec='seconds')

def append(user_id, operation, *, program_id=None, lesson_id=None, payment_id=None, package_id=None,
           paid_delta=0, bonus_delta=0, money=0, hourly_rate=None, reason=None, actor_id=None,
           idempotency_key=None, conn=None):
    schema.initialize(); own = conn is None
    c = conn or database.connect()
    try:
        c.execute('''INSERT OR IGNORE INTO minute_ledger(user_id,program_id,lesson_id,payment_id,package_id,operation,
                   paid_minutes_delta,bonus_minutes_delta,money_rubles,hourly_rate,reason,actor_id,idempotency_key,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (int(user_id),program_id,lesson_id,payment_id,package_id,operation,int(paid_delta),int(bonus_delta),
                   int(money or 0),hourly_rate,reason,actor_id,idempotency_key,now()))
        if own: c.commit()
    finally:
        if own: c.close()


def history(user_id, limit=100):
    schema.initialize(); c=database.connect()
    try: return c.execute('SELECT * FROM minute_ledger WHERE user_id=? ORDER BY id DESC LIMIT ?', (int(user_id),int(limit))).fetchall()
    finally: c.close()


def derived_balance(user_id):
    c=database.connect()
    try:
        r=c.execute('''SELECT COALESCE(SUM(paid_minutes_delta),0) paid,COALESCE(SUM(bonus_minutes_delta),0) bonus
                     FROM minute_ledger WHERE user_id=?''',(int(user_id),)).fetchone()
        return {'paid':int(r['paid'] or 0),'bonus':int(r['bonus'] or 0),'total':int(r['paid'] or 0)+int(r['bonus'] or 0)}
    finally:c.close()

def backfill_current():
    """Create one immutable opening entry per existing package.

    This deliberately snapshots the *remaining* minutes at migration time instead of
    inventing historical minute movements that predate the minute ledger.
    """
    schema.initialize(); c=database.connect()
    try:
        rows=c.execute("""SELECT id,user_id,program_id,source_type,hourly_rate,minutes_total,minutes_used,payment_id
                          FROM lesson_packages WHERE COALESCE(minutes_total,0)>0""").fetchall()
        for p in rows:
            remaining=max(int(p['minutes_total'] or 0)-int(p['minutes_used'] or 0),0)
            if remaining<=0: continue
            key=f"opening:package:{p['id']}"
            paid=0 if p['source_type']=='BONUS' else remaining
            bonus=remaining if p['source_type']=='BONUS' else 0
            append(p['user_id'],'OPENING_BALANCE',program_id=p['program_id'],payment_id=p['payment_id'],package_id=p['id'],paid_delta=paid,bonus_delta=bonus,hourly_rate=p['hourly_rate'],reason='Остаток на момент миграции минутного журнала',idempotency_key=key,conn=c)
        c.commit()
    finally:c.close()
