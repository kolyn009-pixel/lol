from __future__ import annotations
from datetime import datetime,date,timedelta,timezone
import database
from core import admin_roles,event_center,backup_manager,post_lesson,schedule_sync,payment_sync_runtime,payment_reminder_routing
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


_HOMEWORK_ALERT_START_KEY='homework_streak_alerts_started_at'
_HOMEWORK_ALERT_USER_PREFIX='homework_streak_alerted_homework_'
_HOMEWORK_DONE={'DONE','COMPLETED','SUBMITTED','APPROVED','REVIEWED','CHECKED'}


def _parse_homework_dt(value):
    raw=str(value or '').strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace('Z','+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def _homework_alert_cutoff(c, now):
    row=c.execute(
        "SELECT value FROM bot_settings WHERE key=?",
        (_HOMEWORK_ALERT_START_KEY,),
    ).fetchone()

    if row and row['value']:
        return str(row['value'])

    value=now.replace(microsecond=0).isoformat()

    c.execute(
        """
        INSERT INTO bot_settings(key,value,updated_at)
        VALUES(?,?,?)
        ON CONFLICT(key) DO UPDATE SET
            value=excluded.value,
            updated_at=excluded.updated_at
        """,
        (_HOMEWORK_ALERT_START_KEY,value,value),
    )

    c.commit()
    return value


def _homework_streak_alerts(now=None):
    now=(now or datetime.now()).replace(tzinfo=None)

    c=database.connect()

    try:
        cutoff=_homework_alert_cutoff(c,now)

        rows=c.execute(
            """
            SELECT
                h.id,
                h.user_id,
                h.title,
                h.status,
                h.deadline,
                h.created_at,
                u.name
            FROM homework h
            JOIN users u ON u.id=h.user_id
            WHERE h.created_at>=?
            ORDER BY
                h.user_id,
                h.created_at DESC,
                h.id DESC
            """,
            (cutoff,),
        ).fetchall()

        grouped={}

        for row in rows:
            grouped.setdefault(
                int(row['user_id']),
                [],
            ).append(row)

        result=[]

        for user_id,items in grouped.items():
            streak=0

            for row in items:
                status=str(
                    row['status']
                    or ''
                ).upper()

                if status in _HOMEWORK_DONE:
                    break

                deadline=_parse_homework_dt(
                    row['deadline']
                )

                if (
                    deadline is None
                    or deadline>=now
                ):
                    break

                streak+=1

            if streak<3:
                continue

            latest=items[0]

            alert_key=(
                _HOMEWORK_ALERT_USER_PREFIX
                + str(user_id)
            )

            sent=c.execute(
                "SELECT value FROM bot_settings WHERE key=?",
                (alert_key,),
            ).fetchone()

            if (
                sent
                and str(sent['value'] or '')
                == str(latest['id'])
            ):
                continue

            result.append({
                'user_id':user_id,
                'name':str(
                    latest['name']
                    or f'Ученик #{user_id}'
                ),
                'streak':streak,
                'latest_homework_id':int(
                    latest['id']
                ),
                'latest_title':str(
                    latest['title']
                    or 'Домашнее задание'
                ),
            })

        return result

    finally:
        c.close()


def _mark_homework_streak_alerted(
    user_id,
    homework_id,
):
    c=database.connect()

    try:
        now=datetime.now().isoformat(
            timespec='seconds'
        )

        key=(
            _HOMEWORK_ALERT_USER_PREFIX
            + str(int(user_id))
        )

        c.execute(
            """
            INSERT INTO bot_settings(
                key,
                value,
                updated_at
            )
            VALUES(?,?,?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
            """,
            (
                key,
                str(int(homework_id)),
                now,
            ),
        )

        c.commit()

    finally:
        c.close()


async def homework_streak_job(context):
    """Alert only after three consecutive overdue new homeworks."""

    for item in _homework_streak_alerts():
        delivered=False

        text=(
            "⚠️ Систематически не выполняется ДЗ\n\n"
            f"Ученик: {item['name']}\n"
            f"Просрочено подряд: {item['streak']}\n"
            f"Последнее ДЗ: {item['latest_title']}\n\n"
            "Проверьте карточку ученика и домашние задания."
        )

        for admin_id in _admins()[:3]:
            try:
                await context.bot.send_message(
                    admin_id,
                    text,
                )
                delivered=True
            except Exception:
                pass

        if delivered:
            _mark_homework_streak_alerted(
                item['user_id'],
                item['latest_homework_id'],
            )


async def lesson_integrations_reconcile_job(context):
    """Repair missing Telemost/Google links for upcoming confirmed lessons."""
    now=datetime.now()
    horizon=(now+timedelta(days=21)).isoformat(timespec='seconds')
    c=database.connect()
    try:
        rows=c.execute("""
            SELECT id
            FROM lessons
            WHERE lesson_status='CONFIRMED'
              AND start_time>=?
              AND start_time<=?
              AND COALESCE(payment_status,'')!='AWAITING_PAYMENT'
              AND (COALESCE(meeting_url,'')='' OR COALESCE(google_event_id,'')='')
            ORDER BY start_time,id
            LIMIT 20
        """,(now.isoformat(timespec='seconds'),horizon)).fetchall()
        ids=[int(r['id']) for r in rows]
    finally:
        c.close()
    if not ids:return
    result=await schedule_sync.sync_lessons(context.application,ids)
    if result.get('failed'):
        try:
            event_center.push(
                'LESSON_INTEGRATION_RECONCILE',
                'Не все ссылки занятий синхронизированы',
                f"Проверено {len(ids)}, ошибок {len(result['failed'])}",
                priority='ATTENTION',
                dedupe_key='lesson_integration_reconcile',
            )
        except Exception:pass


async def missing_homework_job(context):
    post_lesson.initialize()
    c=database.connect()
    try:
        rows=c.execute("""
            SELECT l.id,l.user_id,l.finished_at
            FROM lessons l
            WHERE l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
            ORDER BY l.finished_at DESC
            LIMIT 80
        """).fetchall()
        for r in rows:
            lid=int(r['id'])
            if _homework_for_lesson(c,lid):continue
            status=_homework_sync_status(c,lid)
            if status in ('SKIPPED','SENT'):continue
            post_lesson.ensure_sync(lid,int(r['user_id']),None)
    finally:c.close()


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
    # Install once after the Telegram application is initialized. This avoids
    # touching bot.py and gives every payment callback the same post-commit
    # Calendar/Telemost reconciliation behavior.
    payment_sync_runtime.install()
    payment_reminder_routing.install()
    jq=application.job_queue
    if not jq:return
    jq.run_repeating(lesson_integrations_reconcile_job,interval=600,first=120,name='ff_lesson_integrations')
    jq.run_repeating(post_lesson_prompt_job,interval=300,first=45,name='ff_post_lesson')
    jq.run_repeating(missing_homework_job,interval=300,first=90,name='ff_missing_homework')
    jq.run_repeating(homework_streak_job,interval=900,first=180,name='ff_homework_streak')
    jq.run_daily(daily_business_job,time=datetime.strptime('03:20','%H:%M').time(),name='ff_reconcile')
    jq.run_daily(monthly_report_draft_job,time=datetime.strptime('09:10','%H:%M').time(),name='ff_monthly_reports')
