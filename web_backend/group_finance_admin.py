"""Teacher group finance view. Viewing never allocates or consumes balance."""
from datetime import datetime
import database

def overview(group_id):
    from web_backend import group_finance
    group_finance.ensure_schema()
    gid=int(group_id);c=database.connect()
    try:
        g=c.execute('SELECT id,name,price_per_lesson FROM study_groups WHERE id=? AND active=1',(gid,)).fetchone()
        if not g:raise ValueError('group_not_found')
        members=[dict(r) for r in c.execute("SELECT m.user_id,u.name,m.status,COALESCE(p.price_per_lesson,?) price FROM group_members m JOIN users u ON u.id=m.user_id LEFT JOIN group_member_prices p ON p.group_id=m.group_id AND p.user_id=m.user_id WHERE m.group_id=? ORDER BY u.name",(g['price_per_lesson'],gid))]
        payments=[dict(r) for r in c.execute('SELECT p.*,u.name FROM group_payments p JOIN users u ON u.id=p.user_id WHERE p.group_id=? ORDER BY p.id DESC LIMIT 201',(gid,))];limited=len(payments)>200;payments=payments[:200]
        received=c.execute("SELECT COALESCE(SUM(total_amount),0) FROM group_payments WHERE group_id=? AND status='PAID'",(gid,)).fetchone()[0]
        subscriptions=[dict(r) for r in c.execute('SELECT * FROM group_subscriptions WHERE group_id=? ORDER BY id',(gid,))]
        lessons=[dict(r) for r in c.execute('SELECT id,start_time,end_time,status FROM group_lessons WHERE group_id=? ORDER BY start_time DESC LIMIT 51',(gid,))];limited=limited or len(lessons)>50;lessons=lessons[:50]
        cells=[];now=database.now_iso()
        for l in lessons:
            for part in c.execute('SELECT user_id FROM group_lesson_participants WHERE lesson_id=?',(l['id'],)):
                uid=int(part['user_id']);paid=c.execute("SELECT id FROM group_payments WHERE group_lesson_id=? AND user_id=? AND status='PAID' LIMIT 1",(l['id'],uid)).fetchone()
                reserved=c.execute("""SELECT l.id FROM group_subscription_ledger l JOIN group_subscriptions s ON s.id=l.subscription_id WHERE s.group_id=? AND s.user_id=? AND l.lesson_id=? AND l.reason='LESSON_RESERVE' AND NOT EXISTS(SELECT 1 FROM group_subscription_ledger r WHERE r.subscription_id=l.subscription_id AND r.lesson_id=l.lesson_id AND r.reason='LESSON_REFUND') LIMIT 1""",(gid,uid,l['id'])).fetchone()
                receipt=c.execute("SELECT id FROM group_payments WHERE group_lesson_id=? AND user_id=? AND status='RECEIPT_SENT' LIMIT 1",(l['id'],uid)).fetchone()
                available=any(s['user_id']==uid and s['status']=='ACTIVE' and int(s['lessons_remaining'])>0 and (not s['expires_at'] or s['expires_at']>now) and (not s['paused_until'] or s['paused_until']<=now or (s['paused_from'] and s['paused_from']>now)) for s in subscriptions)
                state='CANCELLED' if l['status']=='CANCELLED' else 'PAID' if paid else 'RESERVED' if reserved else 'REVIEW' if receipt else 'AVAILABLE' if available else 'UNPAID'
                cells.append({'lesson_id':l['id'],'user_id':uid,'status':state})
        now=database.now_iso()
        for m in members:
            m['remaining']=sum(int(s['lessons_remaining']) for s in subscriptions if s['user_id']==m['user_id'] and s['status']=='ACTIVE' and (not s['expires_at'] or s['expires_at']>now) and (not s['paused_until'] or s['paused_until']<=now or (s['paused_from'] and s['paused_from']>now)))
        audit_exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='group_payment_audit'").fetchone()
        audit=[dict(r) for r in c.execute('SELECT payment_id,teacher_id,action,created_at FROM group_payment_audit WHERE group_id=? ORDER BY id DESC LIMIT 200',(gid,))] if audit_exists else []
        return {'group':dict(g),'members':members,'payments':payments,'subscriptions':subscriptions,'lessons':lessons,'cells':cells,'received':int(received),'limited':limited,'audit':audit}
    finally:c.close()

def confirm(group_id,payment_id,teacher_id,expected_amount):
    """Serialise approval and package credit; persist actor in the same transaction."""
    from web_backend import group_finance
    group_finance.ensure_schema();gid=int(group_id);pid=int(payment_id);c=database.connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM group_payments WHERE id=? AND group_id=?',(pid,gid)).fetchone()
        if not p:raise ValueError('group_payment_not_found')
        if int(p['total_amount'])!=int(expected_amount):raise ValueError('payment_amount_changed')
        if p['status']=='PAID':
            sub=c.execute('SELECT id FROM group_subscriptions WHERE source_payment_id=?',(pid,)).fetchone();c.rollback();return {'status':'ok','already_paid':True,'payment_id':pid,'subscription_id':sub['id'] if sub else None}
        if p['status'] not in ('PENDING','RECEIPT_SENT'):raise ValueError('group_payment_not_approvable')
        c.execute('CREATE TABLE IF NOT EXISTS group_payment_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,group_id INTEGER NOT NULL,payment_id INTEGER NOT NULL,teacher_id INTEGER NOT NULL,action TEXT NOT NULL,created_at TEXT NOT NULL)')
        sid=None;now=database.now_iso();c.execute("UPDATE group_payments SET status='PAID',confirmed_at=? WHERE id=?",(now,pid))
        if p['payment_kind']=='PACKAGE':
            if c.execute('SELECT 1 FROM group_subscriptions WHERE source_payment_id=?',(pid,)).fetchone():raise ValueError('payment_subscription_already_exists')
            opt=c.execute('SELECT validity_days FROM group_package_options WHERE id=?',(p['package_option_id'],)).fetchone()
            from datetime import timedelta
            expires=(datetime.fromisoformat(now)+timedelta(days=int(opt['validity_days']))).isoformat(timespec='seconds') if opt and opt['validity_days'] else None
            cur=c.execute("INSERT INTO group_subscriptions(group_id,user_id,source_payment_id,lessons_total,lessons_remaining,status,starts_at,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,'ACTIVE',?,?,?,?)",(gid,p['user_id'],pid,p['lessons_count'],p['lessons_count'],now,expires,now,now));sid=int(cur.lastrowid)
        c.execute("INSERT INTO group_payment_audit(group_id,payment_id,teacher_id,action,created_at) VALUES(?,?,?,'CONFIRM',?)",(gid,pid,int(teacher_id),now));c.commit()
        return {'status':'ok','payment_id':pid,'subscription_id':sid,'approved_by':int(teacher_id)}
    except Exception:c.rollback();raise
    finally:c.close()
