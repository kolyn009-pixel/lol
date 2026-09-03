from __future__ import annotations
from datetime import date,datetime,timedelta
import database
from learning import exam_results, homework_stats, curriculum
from core import minute_balance
from . import schema


def bounds(month=None):
    d=date.today() if month is None else datetime.strptime(month+'-01','%Y-%m-%d').date(); start=d.replace(day=1); end=(start.replace(day=28)+timedelta(days=4)).replace(day=1); return start,end

def build(user_id, month=None, audience='STUDENT'):
    start,end=bounds(month); c=database.connect()
    try:
        l=c.execute("SELECT COUNT(*) n,COALESCE(SUM(actual_duration_minutes),0) mins FROM lessons WHERE user_id=? AND finished_at>=? AND finished_at<? AND cancelled_at IS NULL",(int(user_id),start.isoformat(),end.isoformat())).fetchone()
        u=database.get_user(int(user_id)); hs=homework_stats.stats(user_id); exams=exam_results.history(user_id)
        latest=exams[-1] if exams else None
        lines=[f"📊 Итоги {start.strftime('%m.%Y')} — {u['name'] if u else user_id}","",f"🎓 Проведено занятий: {int(l['n'] or 0)}",f"⏱ Фактически: {int(l['mins'] or 0)} мин"]
        if isinstance(hs,dict): lines.append(f"📝 ДЗ: выполнено {int(hs.get('done') or 0)}, просрочено {int(hs.get('overdue') or 0)}")
        if latest: lines.append(f"🧪 Последний пробник: {latest['test_score']} баллов")
        programs=database.get_student_programs(int(user_id),active_only=True,approved_only=True)
        total=bonus=0
        for p in programs:
            try:
                b=minute_balance.get_balance(user_id,minute_balance.effective_hourly_rate(p['id'])); total+=b['paid']; bonus+=b['bonus']
            except Exception: pass
        lines += [f"🎟 Оплаченный баланс: {total} мин",f"🎁 Бонусная копилка: {bonus} мин"]
        if audience=='PARENT': lines.append("\nℹ️ Учебные комментарии преподаватель может добавить перед отправкой.")
        return '\n'.join(lines)
    finally:c.close()

def save(user_id,text,month=None,audience='STUDENT',actor=None):
    schema.initialize(); start,end=bounds(month); c=database.connect()
    try:
        cur=c.execute('INSERT INTO progress_report_drafts(user_id,period_from,period_to,audience,report_text,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(int(user_id),start.isoformat(),end.isoformat(),audience,text,'DRAFT',actor,datetime.now().isoformat(timespec='seconds'))); c.commit(); return cur.lastrowid
    finally:c.close()
