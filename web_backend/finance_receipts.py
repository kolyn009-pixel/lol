"""Receipt review facade over TutorBot's existing receipts/payments flow.

Browser responses deliberately exclude Telegram identifiers/file IDs. Mutations
remain delegated to TutorBot's canonical payment functions.
"""
from __future__ import annotations
from database import connect,approve_payment,reject_payment


def _limit(v,default=100):
    try:v=int(v)
    except Exception:v=default
    return max(1,min(v,500))


def list_receipts(status='WAITING',limit=100):
    status=str(status or 'WAITING').upper()
    if status not in {'WAITING','APPROVED','REJECTED','ALL'}:raise ValueError('invalid_receipt_status')
    where=[];params=[]
    if status!='ALL':where.append('r.status=?');params.append(status)
    sql="""
      SELECT r.id receipt_id,r.payment_id,r.user_id,r.source_platform,r.file_type,
        r.status receipt_status,r.created_at receipt_created_at,
        p.status payment_status,p.total_amount,p.lessons_count,p.price_per_lesson,
        p.study_goal,p.subject,p.promo_code,p.promo_discount_amount,
        p.created_at payment_created_at,p.confirmed_at,u.name
      FROM receipts r
      JOIN payments p ON p.id=r.payment_id AND p.user_id=r.user_id
      JOIN users u ON u.id=r.user_id
    """
    if where:sql+=' WHERE '+' AND '.join(where)
    sql+=' ORDER BY r.id DESC LIMIT ?';params.append(_limit(limit));conn=connect();rows=conn.execute(sql,params).fetchall();conn.close();return [dict(r) for r in rows]


def summary():
    conn=connect();rows=conn.execute('SELECT status,COUNT(*) c FROM receipts GROUP BY status').fetchall();waiting_amount=conn.execute("SELECT COALESCE(SUM(p.total_amount),0) s FROM receipts r JOIN payments p ON p.id=r.payment_id AND p.user_id=r.user_id WHERE r.status='WAITING' AND p.status IN ('WAITING','PENDING')").fetchone();conn.close();counts={str(r['status']).upper():int(r['c'] or 0) for r in rows};return {'waiting':counts.get('WAITING',0),'approved':counts.get('APPROVED',0),'rejected':counts.get('REJECTED',0),'waiting_amount':int(waiting_amount['s'] or 0)}


def review(payment_id,action):
    pid=int(payment_id);action=str(action or '').upper();conn=connect();row=conn.execute('SELECT id,status FROM payments WHERE id=?',(pid,)).fetchone();receipt=conn.execute('SELECT id,status FROM receipts WHERE payment_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone();conn.close()
    if not row:raise ValueError('payment_not_found')
    if not receipt:raise ValueError('receipt_not_found')
    if action=='APPROVE':
        if str(row['status']).upper()=='PAID':return {'status':'ok','payment_id':pid,'already_processed':True,'result':'PAID'}
        package_id=approve_payment(pid);return {'status':'ok','payment_id':pid,'package_id':package_id,'result':'PAID'}
    if action=='REJECT':
        if str(row['status']).upper()=='REJECTED':return {'status':'ok','payment_id':pid,'already_processed':True,'result':'REJECTED'}
        reject_payment(pid);return {'status':'ok','payment_id':pid,'result':'REJECTED'}
    raise ValueError('invalid_review_action')
