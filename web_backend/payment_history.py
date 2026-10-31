"""Read-only evidence for payment states. No backfill, schema creation or balance writes."""
import json
import database


def table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def rows(c, name, where='', args=()):
    return [dict(r) for r in c.execute('SELECT * FROM '+name+(' WHERE '+where if where else '')+' ORDER BY rowid DESC LIMIT 201', args)] if table(c,name) else []


def trace(query):
    c=database.connect()
    try:
        kind=query.get('kind',['individual'])[0]
        if kind not in ('individual','group'):raise ValueError('invalid_kind')
        pid=int(query.get('payment_id',['0'])[0]);lid=int(query.get('lesson_id',['0'])[0]);uid=int(query.get('user_id',['0'])[0])
        evidence=[];linked=[];status='';group_id=None
        if kind=='group':
            gid=int(query.get('group_id',['0'])[0]);group_id=gid
            if pid:
                p=c.execute('SELECT * FROM group_payments WHERE id=? AND group_id=?',(pid,gid)).fetchone()
                if not p:raise ValueError('payment_not_found')
                p=dict(p);uid=p['user_id'];status=p['status']
            else:
                l=c.execute('SELECT * FROM group_lessons WHERE id=? AND group_id=?',(lid,gid)).fetchone()
                if not l or not c.execute('SELECT 1 FROM group_lesson_participants WHERE lesson_id=? AND user_id=?',(lid,uid)).fetchone():raise ValueError('lesson_not_found')
                linked=[{'id':lid,'start_time':l['start_time']}]
                p=c.execute("SELECT * FROM group_payments WHERE group_id=? AND group_lesson_id=? AND user_id=? AND status='PAID' ORDER BY id DESC LIMIT 1",(gid,lid,uid)).fetchone()
                p=dict(p) if p else None;pid=p['id'] if p else 0;status='Резерв абонемента' if not p else p['status']
            if pid:
                linked=[dict(r) for r in c.execute('SELECT DISTINCT l.id,l.start_time FROM group_lessons l LEFT JOIN group_subscription_ledger a ON a.lesson_id=l.id LEFT JOIN group_subscriptions s ON s.id=a.subscription_id WHERE l.group_id=? AND (l.id=? OR (s.source_payment_id=? AND s.user_id=?)) ORDER BY l.start_time LIMIT 201',(gid,p.get('group_lesson_id') or 0,pid,uid))] or linked
                for a in rows(c,'group_payment_audit','payment_id=? AND group_id=?',(pid,gid)):
                    evidence.append({'label':'Подтверждение оплаты','at':a['created_at'],'actor':a['teacher_id'],'source':'Журнал группы'})
                if p.get('receipt_ref'):evidence.append({'label':'Приложено подтверждение оплаты','at':p.get('created_at'),'actor':None,'source':'Файл или ссылка сохранены; сами по себе не подтверждают перевод'})
            if lid:
                for a in c.execute('SELECT l.*,s.source_payment_id FROM group_subscription_ledger l JOIN group_subscriptions s ON s.id=l.subscription_id WHERE s.group_id=? AND s.user_id=? AND l.lesson_id=? ORDER BY l.id DESC LIMIT 201',(gid,uid,lid)):
                    evidence.append({'label':{'LESSON_RESERVE':'Занятие зарезервировано из абонемента','LESSON_REFUND':'Занятие возвращено на баланс'}.get(a['reason'],a['reason']),'at':a['created_at'],'actor':None,'source':'Абонемент #'+str(a['subscription_id'])+' · платёж #'+str(a['source_payment_id'])})
        else:
            p=None
            if lid:
                l=c.execute('SELECT * FROM lessons WHERE id=?',(lid,)).fetchone()
                if not l:raise ValueError('lesson_not_found')
                l=dict(l);uid=l['user_id'];status=l['payment_status'];pid=l.get('payment_id') or 0
                linked=[{'id':lid,'start_time':l['start_time']}]
                if not pid and l.get('package_id'):
                    package=c.execute('SELECT payment_id FROM lesson_packages WHERE id=? AND user_id=?',(l['package_id'],uid)).fetchone();pid=package['payment_id'] if package else 0
            if pid:
                p=c.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
                if not p:raise ValueError('payment_not_found')
                p=dict(p);uid=p['user_id'];status=status or p['status']
                linked=[dict(r) for r in c.execute('SELECT id,start_time FROM lessons WHERE user_id=? AND (payment_id=? OR package_id IN (SELECT id FROM lesson_packages WHERE payment_id=? AND user_id=?)) ORDER BY start_time LIMIT 201',(uid,pid,pid,uid))] or linked
                for a in rows(c,'receipt_review_dates','payment_id=?',(pid,)):
                    if a.get('reviewed_at'):evidence.append({'label':'Проверка чека','at':a['reviewed_at'],'actor':a.get('teacher_id'),'source':'Дата оплаты: '+str(a.get('paid_on') or 'не указана')})
                for a in rows(c,'receipts','payment_id=?',(pid,)):
                    evidence.append({'label':'Чек: '+str(a.get('status') or 'статус не сохранён'),'at':a.get('created_at'),'actor':None,'source':'Чек #'+str(a['id'])})
                if p.get('source_type') or p.get('source_platform'):
                    evidence.append({'label':'Источник записи платежа','at':p.get('created_at'),'actor':None,'source':' · '.join(str(p[k]) for k in ('source_type','source_platform') if p.get(k))})
            if table(c,'minute_ledger') and (pid or lid):
                for a in rows(c,'minute_ledger','payment_id=? OR lesson_id=?',(pid or -1,lid or -1)):
                    evidence.append({'label':str(a.get('reason') or a['operation']),'at':a['created_at'],'actor':a.get('actor_id'),'source':'Журнал минут · '+str(a['operation'])})
        if not uid:raise ValueError('payment_or_lesson_required')
        user=c.execute('SELECT name FROM users WHERE id=?',(uid,)).fetchone()
        return {'kind':kind,'group_id':group_id,'payment_id':pid or None,'lesson_id':lid or None,'name':user['name'] if user else 'Ученик','status':status,'amount':p.get('total_amount') if p else None,'confirmed_at':p.get('confirmed_at') if p else None,'evidence':evidence[:200],'lessons':linked[:200],'note':'Сохранённые записи показывают историю статуса. Отсутствующие источник или автор не восстанавливаются автоматически.'}
    finally:c.close()


def journal(group_id=None):
    c=database.connect();items=[];gid=int(group_id or 0)
    try:
        if not gid:
            for r in rows(c,'payment_reversals'):
                try:snapshot=json.loads(r['snapshot']);result=json.loads(r['result'])
                except (ValueError,TypeError):snapshot={};result={}
                p=snapshot.get('payment') or {};items.append({'kind':'Отмена подтверждения','payment_id':r['payment_id'],'user_id':p.get('user_id'),'amount':p.get('total_amount'),'at':r['reversed_at'],'actor':r['actor_id'],'reason':r['reason'],'source':r['source'],'lesson_ids':result.get('lesson_ids',[]),'note':'Исправление учёта. Деньги через банк не возвращаются.'})
        if table(c,'group_subscription_ledger'):
            sql="SELECT l.*,s.user_id,s.group_id,s.source_payment_id FROM group_subscription_ledger l JOIN group_subscriptions s ON s.id=l.subscription_id WHERE l.reason='LESSON_REFUND'"+(' AND s.group_id=?' if gid else '')+' ORDER BY l.id DESC LIMIT 201'
            for r in c.execute(sql,(gid,) if gid else ()):
                items.append({'kind':'Возврат занятия на баланс группы','payment_id':r['source_payment_id'],'user_id':r['user_id'],'amount':None,'at':r['created_at'],'actor':None,'reason':r['reason'],'source':'Абонемент #'+str(r['subscription_id']),'lesson_ids':[r['lesson_id']],'note':str(r['delta'])+' зан. · денежный возврат не зафиксирован'})
        if not gid:
            for r in rows(c,'minute_ledger',"operation='LESSON_REFUND'"):
                minutes=int(r.get('paid_minutes_delta') or 0)+int(r.get('bonus_minutes_delta') or 0)
                items.append({'kind':'Возврат минут на баланс','payment_id':r.get('payment_id'),'user_id':r['user_id'],'amount':None,'at':r['created_at'],'actor':r.get('actor_id'),'reason':r.get('reason') or 'Возврат за занятие','source':'Журнал минут','lesson_ids':[r['lesson_id']] if r.get('lesson_id') else [],'note':str(minutes)+' мин · денежный возврат не зафиксирован'})
        for x in items:
            u=c.execute('SELECT name FROM users WHERE id=?',(x['user_id'],)).fetchone();x['name']=u['name'] if u else 'Ученик'
        items.sort(key=lambda x:x['at'] or '',reverse=True)
        return {'items':items[:200],'limited':len(items)>200,'note':'Отмены подтверждений и возвраты занятий на баланс. Банковские возвраты здесь не выполняются.'}
    finally:c.close()
