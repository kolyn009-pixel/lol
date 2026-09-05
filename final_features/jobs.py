from __future__ import annotations
from datetime import datetime,date,timedelta,timezone
import database
from core import admin_roles,event_center,backup_manager,post_lesson
from core.lesson_time import actual_datetime
from . import schema
from .smart import next_actions
from .reconcile import run as reconcile
from .reports import build as build_report,save as save_report


def _admins():
    try:return [int(r['telegram_id']) for r in admin_roles.list_admins() if r['active']]
    except Exception:return []


def _homework_for_lesson(c, lesson_id):
    try:
        return c.execute("SELECT id FROM homeworks WHERE lesson_id=? ORDER BY id DESC LIMIT 1",(int(lesson_id),)).fetchone()
    except Exception:
        return None


def _homework_draft_for_lesson(c, lesson_id):
    try:
        return c.execute("SELECT id,admin_telegram_id,status FROM homework_drafts WHERE lesson_id=? AND status='DRAFT' ORDER BY updated_at DESC LIMIT 1",(int(lesson_id),)).fetchone()
    except Exception:
        return None


def _homework_sync_status(c, lesson_id):
    try:
        row=c.execute("SELECT homework_status FROM post_lesson_review_sync WHERE lesson_id=?",(int(lesson_id),)).fetchone()
        return str(row['homework_status'] or '').upper() if row else ''
    except Exception:
        return ''


async def _send_missing_homework_prompt(context, row, stage, draft=None):
    lesson_id=int(row['id']);uid=int(row['user_id']);name=row['name']
    is_followup=(stage=='followup')
    if draft:
        text=(
            f"📝 {'НАПОМИНАНИЕ: ' if is_followup else ''}ДЗ ЕЩЁ НЕ ОТПРАВЛЕНО\n\n"
            f"👤 {name}\n"
            f"Занятие #{lesson_id} завершено, а черновик ДЗ всё ещё не отправлен ученику."
        )
        tg_cb=f"hw2_step1|{int(draft['id'])}"
        tg_label="▶️ Продолжить ДЗ"
    else:
        text=(
            f"📝 {'НАПОМИНАНИЕ: ' if is_followup else ''}ПОСЛЕ ЗАНЯТИЯ НЕТ ДЗ\n\n"
            f"👤 {name}\n"
            f"Занятие #{lesson_id} завершено, но домашнее задание ещё не задано."
        )
        tg_cb=f"admin_homework_create|{lesson_id}"
        tg_label="📝 Задать ДЗ"
    text += "\n\nЕсли ДЗ не нужно, отметьте «Без ДЗ» в итогах занятия."

    try:
        from telegram import InlineKeyboardButton,InlineKeyboardMarkup
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton(tg_label,callback_data=tg_cb)],
            [InlineKeyboardButton('🧠 Итоги занятия',callback_data=f"ff_review_start|{lesson_id}|{uid}")],
            [InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')],
        ])
        for aid in _admins()[:3]:
            try:await context.bot.send_message(aid,text,reply_markup=kb)
            except Exception:pass
    except Exception:pass

    try:
        from vk_adapter import app as vk_app,teacher_service
        for peer in teacher_service.teacher_alert_peers():
            try:
                vk_app.send(int(peer),text,True,"teacher_lesson",{"lesson_id":lesson_id,"user_id":uid})
            except Exception:pass
    except Exception:pass


async def missing_homework_job(context):
    """Remind the teacher in both channels when a finished lesson still has no HW.

    First prompt: roughly 10 minutes after the lesson is closed.
    Follow-up: roughly 60 minutes after closing if nothing was sent yet.
    Explicit SKIPPED suppresses reminders.
    """
    post_lesson.initialize()
    c=database.connect()
    try:
        rows=c.execute("""
            SELECT l.id,l.user_id,l.finished_at,u.name
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
            ORDER BY l.finished_at DESC
            LIMIT 40
        """).fetchall()
        now=datetime.now(timezone.utc)
        for r in rows:
            lid=int(r['id'])
            if _homework_for_lesson(c,lid):
                continue
            status=_homework_sync_status(c,lid)
            if status in ('SKIPPED','SENT'):
                continue
            try:
                finished=actual_datetime(r['finished_at']).astimezone(timezone.utc)
                age=(now-finished).total_seconds()
            except Exception:
                continue
            draft=_homework_draft_for_lesson(c,lid)
            stages=[]
            if age>=10*60:stages.append('first')
            if age>=60*60:stages.append('followup')
            for stage in stages:
                key=f"missing_homework:{lid}:{stage}"
                if not post_lesson.claim(key):
                    continue
                await _send_missing_homework_prompt(context,r,stage,draft=draft)
    finally:
        c.close()


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
    jq.run_repeating(missing_homework_job,interval=300,first=90,name='ff_missing_homework')
    jq.run_daily(daily_business_job,time=datetime.strptime('03:20','%H:%M').time(),name='ff_reconcile')
    jq.run_daily(monthly_report_draft_job,time=datetime.strptime('09:10','%H:%M').time(),name='ff_monthly_reports')
