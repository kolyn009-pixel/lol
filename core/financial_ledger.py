from datetime import datetime
import database
from .schema import ensure_schema


def append(user_id, amount=0, lessons_delta=0, nominal=0, entry_type="ADJUSTMENT", source_type=None, source_id=None, description=None, actor_id=None, external_key=None, created_at=None):
    ensure_schema()
    conn=database.connect()
    try:
        conn.execute("""INSERT INTO financial_ledger(user_id,amount,lessons_delta,nominal,entry_type,source_type,source_id,external_key,description,actor_telegram_id,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id,int(amount or 0),int(lessons_delta or 0),int(nominal or 0),entry_type,source_type,str(source_id) if source_id is not None else None,external_key,description,actor_id,created_at or datetime.now().isoformat(timespec="seconds")))
        conn.commit(); return True
    except Exception as exc:
        if "UNIQUE constraint failed: financial_ledger.external_key" in str(exc): return False
        raise
    finally: conn.close()


def backfill_existing():
    ensure_schema(); conn=database.connect()
    payments=conn.execute("SELECT id,user_id,total_amount,price_per_lesson,lessons_count,confirmed_at,created_at FROM payments WHERE status IN ('PAID','CONFIRMED')").fetchall()
    lessons=conn.execute("SELECT id,user_id,price,start_time,finished_at FROM lessons WHERE lesson_status='COMPLETED'").fetchall()
    conn.close()
    for p in payments:
        append(p['user_id'], amount=p['total_amount'], nominal=p['price_per_lesson'], lessons_delta=p['lessons_count'], entry_type='PAYMENT_RECEIVED', source_type='payment', source_id=p['id'], external_key=f"payment:{p['id']}:received", description='Подтвержденная оплата', created_at=p['confirmed_at'] or p['created_at'])
    for l in lessons:
        append(l['user_id'], amount=l['price'], nominal=l['price'], lessons_delta=-1, entry_type='LESSON_EARNED', source_type='lesson', source_id=l['id'], external_key=f"lesson:{l['id']}:earned", description='Проведенное занятие', created_at=l['finished_at'] or l['start_time'])


def recent(limit=50):
    conn=database.connect(); rows=conn.execute("SELECT * FROM financial_ledger ORDER BY id DESC LIMIT ?",(int(limit),)).fetchall(); conn.close(); return [dict(r) for r in rows]
