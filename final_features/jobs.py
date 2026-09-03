from __future__ import annotations
from datetime import datetime,date,timedelta
import database
from core import admin_roles,event_center,backup_manager
from . import schema
from .smart import next_actions
from .reconcile import run as reconcile
from .reports import build as build_report,save as save_report


def _admins():
    try:return [int(r['telegram_id']) for r in admin_roles.list_admins() if r['active']]
    except Exception:return []

async def post_lesson_prompt_job(context):
    schema.initialize(); c=database.connect()
    try:
        rows=c.execute("""SELECT l.id,l.user_id,u.name FROM lessons l JOIN users u ON u.id=l.user_id
                         WHERE l.finished_at IS NOT NULL AND l.cancelled_at IS NULL AND COALESCE(l.post_lesson_reviewed,0)=0
                         ORDER BY l.finished_at DESC LIMIT 10""").fetchall()
        now=datetime.now().isoformat(timespec='seconds')
        for r in rows:
            exists=c.execute("SELECT 1 FROM smart_actions WHERE action_type='POST_LESSON_REVIEW' AND source_type='lesson' AND source_id=? AND status='OPEN'",(r['id'],)).fetchone()
            if exists: continue
            c.execute("INSERT OR IGNORE INTO smart_actions(user_id,action_type,priority,title,details,status,source_type,source_id,created_at) VALUES(?,?,?,?,?,'OPEN','lesson',?,?)",(r['user_id'],'POST_LESSON_REVIEW','ACTION',f"Итоги занятия: {r['name']}",f"Занятие #{r['id']} — отметьте темы и уровень.",r['id'],now))
            for aid in _admins()[:3]:
                try:
                    from telegram import InlineKeyboardButton,InlineKeyboardMarkup
                    await context.bot.send_message(aid,f"✅ Занятие с {r['name']} завершено.\nОтметить пройденные темы?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧠 Быстрый опрос',callback_data=f"ff_review_start|{r['id']}|{r['user_id']}")]]))
                except Exception: pass
        c.commit()
    finally:c.close()

async def daily_business_job(context):
    issues=reconcile(); critical=[i for i in issues if i[0] in ('CRITICAL','ATTENTION')]
    if critical:
        for sev,code,details,uid in critical[:20]:
            try:event_center.push(code, f'Сверка: {code}', details, 'CRITICAL' if sev=='CRITICAL' else 'ATTENTION', 'user', uid, f'reconcile:{code}:{uid}')
            except Exception:pass

async def monthly_report_draft_job(context):
    if date.today().day != 1:return
    c=database.connect()
    try: users=c.execute('SELECT id FROM users WHERE active=1').fetchall()
    finally:c.close()
    prev=(date.today().replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
    for u in users:
        try:
            text=build_report(u['id'],prev,'STUDENT'); save_report(u['id'],text,prev,'STUDENT',None)
        except Exception:pass

def register(application):
    jq=application.job_queue
    if not jq:return
    jq.run_repeating(post_lesson_prompt_job,interval=300,first=45,name='ff_post_lesson')
    jq.run_daily(daily_business_job,time=datetime.strptime('03:20','%H:%M').time(),name='ff_reconcile')
    jq.run_daily(monthly_report_draft_job,time=datetime.strptime('09:10','%H:%M').time(),name='ff_monthly_reports')
