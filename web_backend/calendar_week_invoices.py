"""Read-only calendar-week invoice view. Invoice creation stays canonical."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import database


def bounds(now, zone):
    local = now.astimezone(ZoneInfo(zone)) if now.tzinfo else now
    start = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.weekday())
    return start.replace(tzinfo=None), (start + timedelta(days=7)).replace(tzinfo=None)


def candidates(limit=100, now=None):
    from web_backend.teacher_invoices import _lesson_price, _payment_summary
    from web_backend.invoice_pricing import individual_lesson_quote
    zone = str(database.get_setting('bot_timezone', 'Europe/Samara') or 'Europe/Samara')
    try:
        tz = ZoneInfo(zone)
    except (ValueError, KeyError):
        zone, tz = 'Europe/Samara', ZoneInfo('Europe/Samara')
    current = now or datetime.now(tz)
    start, end = bounds(current, zone)
    local_now = current.astimezone(tz).replace(tzinfo=None) if current.tzinfo else current
    conn = database.connect()
    try:
        rows = conn.execute('''SELECT l.*,u.name student_name FROM lessons l
            JOIN users u ON u.id=l.user_id
            WHERE l.start_time>=? AND l.start_time<? ORDER BY l.start_time,l.id''',
            (start.isoformat(timespec='seconds'), end.isoformat(timespec='seconds'))).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        item = dict(row)
        payment = database.get_payment_for_lesson(int(row['id']))
        paid = str(item.get('payment_status') or 'UNPAID').upper()
        status = str(item.get('lesson_status') or '').upper()
        trial = bool(item.get('is_trial'))
        starts = datetime.fromisoformat(str(row['start_time']))
        if starts.tzinfo:
            starts = starts.astimezone(tz).replace(tzinfo=None)
        eligible = (not trial and starts >= local_now and
                    status not in {'CANCELLED','LATE_CANCELLED','REJECTED','COMPLETED','SICKNESS','NO_SHOW'} and
                    paid not in {'PAID','FREE','RESERVED_BALANCE','TRANSFERRED','COVERED','WAIVED'} and payment is None)
        price = _lesson_price(row)
        source = 'LESSON_SNAPSHOT'
        if eligible:
            quote = individual_lesson_quote(row)
            if quote:
                price, source = int(quote['amount']), quote['source']
        out.append({'lesson_id':int(row['id']), 'user_id':int(row['user_id']),
                    'student_name':row['student_name'], 'start_time':row['start_time'],
                    'end_time':item.get('end_time'), 'duration_minutes':item.get('duration_minutes'),
                    'subject':row['subject'], 'lesson_status':status,
                    'lesson_payment_status':paid, 'is_trial':trial,
                    'price':price, 'price_source':source, 'payment':_payment_summary(payment),
                    'can_issue':bool(eligible and price > 0)})
    return {'items':out, 'count':len(out), 'calendar_week':True,
            'period':{'start':start.isoformat(timespec='seconds'),
                      'end':end.isoformat(timespec='seconds'),
                      'last_day':(end-timedelta(days=1)).date().isoformat(), 'timezone':zone}}
