"""Non-mutating forecasts and family week drafts, never payment creation."""
from datetime import datetime,timedelta
import database

def _period(day=None):
    from core.lesson_time import lesson_timezone
    tz=lesson_timezone();d=datetime.fromisoformat(str(day)) if day else datetime.now(tz).replace(tzinfo=None)
    d=d.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=d.weekday())
    return d,d+timedelta(days=7),tz

def _key(value,tz):
    d=datetime.fromisoformat(str(value));return d.astimezone(tz).replace(tzinfo=None) if d.tzinfo else d

def forecast(group_id,day=None):
    start,end,tz=_period(day);gid=int(group_id);c=database.connect()
    try:
        rows=c.execute('''SELECT l.*,p.user_id,p.attendance_status,COALESCE(m.price_per_lesson,l.price_per_student) unit_price FROM group_lessons l JOIN group_lesson_participants p ON p.lesson_id=l.id LEFT JOIN group_member_prices m ON m.group_id=l.group_id AND m.user_id=p.user_id WHERE l.group_id=? AND l.start_time>=? AND l.start_time<? ORDER BY l.start_time''',(gid,(start-timedelta(days=2)).isoformat(),(end+timedelta(days=2)).isoformat())).fetchall()
        rows=[dict(r) for r in rows if start<=_key(r['start_time'],tz)<end and r['status']!='CANCELLED' and r['attendance_status'] not in ('PAUSED','CANCELLED')]
        scheduled=sum(int(r['unit_price']) for r in rows if r['status'] in ('SCHEDULED','IN_PROGRESS'));completed=sum(int(r['unit_price']) for r in rows if r['status']=='COMPLETED')
        received=sum(int(r['total_amount']) for r in c.execute("SELECT total_amount,confirmed_at FROM group_payments WHERE group_id=? AND status='PAID' AND confirmed_at IS NOT NULL",(gid,)) if start<=_key(r['confirmed_at'],tz)<end)
        return {'start':start.date().isoformat(),'end':(end-timedelta(days=1)).date().isoformat(),'timezone':str(tz),'scheduled_estimate':scheduled,'completed_estimate':completed,'received':received,'participant_visits':len(rows),'note':'Оценка по созданным занятиям и участникам. Изменения состава и персональных цен изменяют прогноз. Абонементные поступления не равны доходу за проведённые занятия.'}
    finally:c.close()

def families(group_id):
    c=database.connect()
    try:
        exists=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='parent_student_links'").fetchone()
        if not exists:return []
        return [dict(r) for r in c.execute('''SELECT DISTINCT p.id,p.name FROM parent_accounts p JOIN parent_student_links l ON l.parent_id=p.id JOIN group_members m ON m.user_id=l.student_id WHERE m.group_id=? AND p.active=1 ORDER BY p.name''',(int(group_id),))]
    finally:c.close()

def family_week(group_id,parent_id,day=None):
    gid=int(group_id);pid=int(parent_id)
    if pid not in {r['id'] for r in families(gid)}:raise ValueError('family_not_in_group')
    from web_backend import calendar_week_invoices
    start,end,tz=_period(day);c=database.connect()
    try:
        children={int(r['id']):r['name'] for r in c.execute('SELECT u.id,u.name FROM users u JOIN parent_student_links l ON l.student_id=u.id WHERE l.parent_id=?',(pid,))}
        parent=c.execute('SELECT name FROM parent_accounts WHERE id=?',(pid,)).fetchone()['name']
        singles=calendar_week_invoices.candidates(now=start.replace(tzinfo=tz));items=[]
        for x in singles['items']:
            if int(x['user_id']) not in children:continue
            status=x['lesson_payment_status'];paid=status in ('PAID','FREE','RESERVED_BALANCE','TRANSFERRED','COVERED','WAIVED');cancelled=x['lesson_status'] in ('CANCELLED','REJECTED','SICKNESS','LATE_CANCELLED')
            pending=bool(x.get('payment')) and not paid
            # Pending bills/receipts are listed but never turned into another invoice.
            due=0 if paid or cancelled or x.get('is_trial') else None if pending else int(x['price'])
            items.append({'kind':'INDIVIDUAL','lesson_id':x['lesson_id'],'student':children[int(x['user_id'])],'start_time':x['start_time'],'title':x['subject'],'amount':int(x['price']),'to_pay':due,'status':'Отменено' if cancelled else 'Оплачено / предоплачено' if paid else 'Уже есть платёж / счёт — проверить' if pending else 'Предварительно к оплате'})
        if children:
            marks=','.join('?' for _ in children)
            rows=c.execute(f'''SELECT l.*,p.user_id,p.attendance_status,g.name group_name,COALESCE(m.price_per_lesson,l.price_per_student) unit_price FROM group_lesson_participants p JOIN group_lessons l ON l.id=p.lesson_id JOIN study_groups g ON g.id=l.group_id LEFT JOIN group_member_prices m ON m.group_id=l.group_id AND m.user_id=p.user_id WHERE p.user_id IN ({marks}) AND l.start_time>=? AND l.start_time<?''',(*children,(start-timedelta(days=2)).isoformat(),(end+timedelta(days=2)).isoformat())).fetchall()
            from web_backend.group_finance import financial_status_for_lesson
            for r in rows:
                if not start<=_key(r['start_time'],tz)<end:continue
                f=financial_status_for_lesson(r['id'],r['user_id']);available=bool(f.get('covered') and f.get('status')!='PAID' and not f.get('reserved'));cancelled=r['status']=='CANCELLED' or r['attendance_status'] in ('PAUSED','CANCELLED');due=0 if cancelled or (f.get('covered') and not available) else None if available else int(r['unit_price'])
                pending=c.execute("SELECT 1 FROM group_payments WHERE user_id=? AND group_lesson_id=? AND status IN ('PENDING','RECEIPT_SENT')",(r['user_id'],r['id'])).fetchone()
                if pending and due:due=None
                items.append({'kind':'GROUP','lesson_id':r['id'],'student':children[int(r['user_id'])],'start_time':r['start_time'],'title':r['group_name'],'amount':int(r['unit_price']),'to_pay':due,'status':'Отменено / пауза' if cancelled else 'Есть баланс — распределение проверить' if available else 'Оплачено / зарезервировано' if f.get('covered') else 'Уже есть счёт / чек — проверить' if pending else 'Предварительно к оплате'})
        items.sort(key=lambda x:(_key(x['start_time'],tz),x['kind'],x['lesson_id']))
        return {'parent':parent,'start':start.date().isoformat(),'end':(end-timedelta(days=1)).date().isoformat(),'items':items,'draft_total':sum(x['to_pay'] or 0 for x in items),'needs_review':sum(x['to_pay'] is None for x in items),'draft':True,'note':'Черновик недельного расчёта, а не созданный счёт. До отправки проверь состав занятий, оплаты, абонементы и плательщика. Ничего не начислено и не отправлено.'}
    finally:c.close()
