"""Compact olympiad summaries shared by Telegram and VK. No login tokens in URLs."""
from web_backend import olympiad_store as store


def cabinet(role):
    return 'https://adeliatutor.ru/app/'+('teacher.html' if role=='teacher' else '')+'?olympiads=1'


def summary(role,uid,subject=''):
    data=store.overview(role,uid)
    items=[x for x in data['items'] if not subject or x['subject']==subject]
    current=store.now();entries=[]
    for x in items:
        for e in x['events']:
            if e['status'] not in {'CONFIRMED','TENTATIVE'}:continue
            at=store.event_boundary(e.get('end_at') or e.get('start_at'),e['precision'],bool(e.get('end_at')))
            if not at or at<current:continue
            entries.append((at,x,e))
    entries.sort(key=lambda v:v[0]);lines=['🏆 ОЛИМПИАДЫ · '+data['season']]
    if subject:lines.append({'PHYSICS':'⚛️ Физика','CHEMISTRY':'🧪 Химия'}[subject])
    recommended=[x['title'] for x in items if x['recommendation']]
    if recommended:lines+=['','⭐ Рекомендует преподаватель: '+', '.join(recommended[:4])]
    for _,x,e in entries[:6]:
        label='⚛️' if x['subject']=='PHYSICS' else '🧪'
        lines+=['',label+' '+x['title'],e['title']+' · '+store.describe_date(e)]
        if e['status']=='TENTATIVE':lines.append('Предварительно')
    if not entries:lines+=['','Ближайшие подтверждённые даты пока не добавлены.']
    lines+=['','Время — МСК. Календарь, подготовка и напоминания — кнопкой ниже.']
    return '\n'.join(lines)
