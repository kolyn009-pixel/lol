"""Additive calendar read model: no lesson/payment mutation and no synthetic dates."""
from __future__ import annotations
import database


def enrich_schedule(start, end, items, limit):
    c=database.connect()
    try:
        exists=lambda name: bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())
        individual=[dict(x,kind='INDIVIDUAL') for x in items]
        ids=[int(x['id']) for x in individual]
        moved=set()
        if ids:
            columns={r['name'] for r in c.execute('PRAGMA table_info(lessons)')}
            fields=[name for name in ('rescheduled_from_lesson_id','is_trial') if name in columns]
            if fields:
                marks=','.join('?' for _ in ids)
                by_id={int(r['id']):dict(r) for r in c.execute('SELECT id,'+','.join(fields)+' FROM lessons WHERE id IN ('+marks+')',ids)}
                for item in individual:
                    item.update(by_id.get(int(item['id']),{}));item['rescheduled']=bool(item.get('rescheduled_from_lesson_id'))
            if exists('slot_change_requests'):
                columns={r['name'] for r in c.execute('PRAGMA table_info(slot_change_requests)')}
                if 'apply_requester_before_start' in columns:
                    from core.lesson_time import schedule_datetime
                    by_id={int(x['id']):x for x in individual}
                    for r in c.execute("SELECT * FROM slot_change_requests WHERE status IN ('APPLIED','APPLYING') AND apply_requester_before_start IS NOT NULL"):
                        for side,other in (('requester','occupant'),('occupant','requester')):
                            lid=r[side+'_lesson_id']
                            if lid is None or int(lid) not in by_id:continue
                            before=r['apply_'+side+'_before_start']
                            target=(r['desired_start'] if side=='requester' else r['occupant_proposed_start']) if r['exchange_mode']=='SHIFT' else r['apply_'+other+'_before_start']
                            if before and target and schedule_datetime(target)==schedule_datetime(by_id[int(lid)]['start_time']) and schedule_datetime(before)!=schedule_datetime(target):
                                moved.add(int(lid))
        groups=[]
        if exists('group_lessons') and exists('study_groups'):
            groups=[dict(r) for r in c.execute('''SELECT 'group-'||l.id AS id,l.id AS group_lesson_id,l.group_id,
              'GROUP' AS kind,g.name,g.subject,g.study_goal,l.start_time,l.end_time,
              l.status AS lesson_status,l.price_per_student AS price
              FROM group_lessons l JOIN study_groups g ON g.id=l.group_id
              WHERE l.start_time>=? AND l.start_time<? ORDER BY l.start_time,l.id LIMIT ?''',(start,end,int(limit)))]
        limited=len(individual)>=int(limit) or len(groups)>=int(limit)
    finally:
        c.close()
    for item in individual:
        if int(item['id']) in moved:item['rescheduled']=True
    # Keep the original items shape for older callers of the CRM endpoint.
    return {'start':start,'end':end,'items':items,'calendar_items':individual+groups,'calendar_limit_reached':limited}
