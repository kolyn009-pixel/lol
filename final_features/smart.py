from __future__ import annotations
from datetime import datetime,date,timedelta
import database
from core import minute_balance
from automation.balance_forecast import forecast
from learning import exam_results, homework_stats
from . import schema


def _future_lesson(user_id):
    c=database.connect()
    try:return c.execute("SELECT * FROM lessons WHERE user_id=? AND cancelled_at IS NULL AND finished_at IS NULL AND datetime(start_time)>=datetime('now') ORDER BY datetime(start_time) LIMIT 1",(int(user_id),)).fetchone()
    finally:c.close()

def next_actions(user_id):
    schema.initialize(); items=[]; user=database.get_user(int(user_id))
    try:
        f=forecast(user_id)
        if f.get('remaining',999999)<=180: items.append(('ATTENTION','💳 Низкий баланс',f"Осталось {f['remaining']} мин"))
    except Exception: pass
    nxt=_future_lesson(user_id)
    if not nxt: items.append(('ATTENTION','📅 Нет следующего занятия','Стоит назначить следующее занятие.'))
    hs=homework_stats.stats(user_id)
    overdue=int(hs.get('overdue',0) or 0) if isinstance(hs,dict) else 0
    if overdue: items.append(('ACTION','📝 Просроченное ДЗ',f'{overdue} шт.'))
    c=database.connect()
    try:
        pending=c.execute("SELECT COUNT(*) n FROM teacher_inbox WHERE student_id=? AND status='OPEN'",(int(user_id),)).fetchone()['n']
        if pending: items.append(('ACTION','💬 Есть сообщения',f'{pending} открытых'))
        mocks=c.execute("SELECT COUNT(*) n FROM mock_tests WHERE user_id=? AND status IN ('ASSIGNED','SUBMITTED')",(int(user_id),)).fetchone()['n']
        if mocks: items.append(('INFO','🧪 Пробники',f'{mocks} требуют внимания'))
    finally:c.close()
    return items

def card(user_id):
    u=database.get_user(int(user_id)); actions=next_actions(user_id); nxt=_future_lesson(user_id)
    lines=[f"👤 {u['name'] if u else user_id}",""]
    if actions:
        lines += ['⚡ СЛЕДУЮЩИЕ ДЕЙСТВИЯ']+[f"{'🔴' if p=='ACTION' else '🟠' if p=='ATTENTION' else '🔵'} {t} — {d}" for p,t,d in actions]+['']
    if nxt: lines.append(f"📅 Следующее: {nxt['start_time']} • {nxt['duration_minutes']} мин")
    programs=database.get_student_programs(int(user_id),active_only=True,approved_only=True)
    for p in programs:
        try:
            b=minute_balance.get_balance(user_id,minute_balance.effective_hourly_rate(p['id']))
            lines.append(f"🎟 {p['study_goal']} {p['subject']}: {b['total']} мин")
        except Exception: pass
    return '\n'.join(lines)
