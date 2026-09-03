from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden
from core import admin_roles
from core import user_timezone
import database
from . import service, messenger

log=logging.getLogger(__name__)

def _on(key, default='1'):
    return str(database.get_setting(key,default)).lower() not in ('0','false','off','no')

def _tz():
    name=database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'
    try:return ZoneInfo(name)
    except Exception:return ZoneInfo('Europe/Samara')

def _admins():
    try:return [int(a['telegram_id']) for a in admin_roles.list_admins() if a['active']]
    except Exception:return []

def _queue_markup(morning=False):
    label='🌅 Подготовить день' if morning else '▶️ Разобрать всё по очереди'
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label,callback_data='ux_review_start')],
        [InlineKeyboardButton('💬 Сообщения',callback_data='admin_student_messages'),InlineKeyboardButton('💳 Оплаты',callback_data='mh_debts')],
        [InlineKeyboardButton('⚠️ Требуют внимания',callback_data='mh_attention'),InlineKeyboardButton('📅 Сегодня',callback_data='crm_today')],
        [InlineKeyboardButton('🏠 Главная',callback_data='global_home')],
    ])

async def morning_brief_job(context):
    d=service.today_dashboard()
    lines=['💜 АДЕЛИЯ • ДОБРОЕ УТРО','', 'Я уже посмотрела, что у нас сегодня. Вот главное 💜','',
           f"📅 Занятий сегодня: {len(d['lessons'])}",f"💬 Сообщений ждут ответа: {int(d['open_messages'] or 0)}",
           f"💳 Неоплаченных занятий: {int(d['unpaid'] or 0)}" if _on('notify_payment','1') else '💳 Оплаты: уведомления выключены',f"⚠️ Требуют внимания: {len(d['attention'])}"]
    try:
        from core import admin_inbox
        lines.append(f"📥 Во входящих: {admin_inbox.counts()['total']}")
    except Exception:pass
    if not d['lessons'] and not d['attention'] and not d['open_messages'] and not d['unpaid']:
        lines += ['','🟢 Всё спокойно. Можно начинать день без хвостов.']
    for aid in _admins():
        try:
            await context.bot.send_message(aid,'\n'.join(lines),reply_markup=_queue_markup(True)); database.set_setting('morning_brief_last_ok',datetime.now(_tz()).isoformat(timespec='minutes')); database.log_automation_delivery('morning_brief','OK','ADMIN',aid)
        except Exception as e:
            database.log_automation_delivery('morning_brief','ERROR','ADMIN',aid,repr(e)); log.exception('ADELIA MORNING BRIEF SEND ERROR admin=%s',aid)

async def evening_brief_job(context):
    c=database.connect(); local_now=datetime.now(_tz()); today=local_now.date().isoformat(); tomorrow_day=(local_now.date()+timedelta(days=1)).isoformat()
    try:
        done=c.execute("SELECT COUNT(*) FROM lessons WHERE date(COALESCE(finished_at,start_time))=? AND lesson_status IN ('COMPLETED','FINISHED')",(today,)).fetchone()[0]
        cancelled=c.execute("SELECT COUNT(*) FROM lessons WHERE date(COALESCE(cancelled_at,start_time))=? AND lesson_status='CANCELLED'",(today,)).fetchone()[0]
        unpaid=c.execute("SELECT COUNT(*),COALESCE(SUM(price),0) FROM lessons WHERE lesson_status='CONFIRMED' AND payment_status='AWAITING_PAYMENT'").fetchone()
        tomorrow=c.execute("SELECT COUNT(*) FROM lessons WHERE date(start_time)=? AND lesson_status!='CANCELLED'",(tomorrow_day,)).fetchone()[0]
    except Exception:
        log.exception('ADELIA EVENING BRIEF DB ERROR');done=cancelled=tomorrow=0;unpaid=(0,0)
    finally:c.close()
    d=service.today_dashboard()
    lines=['💜 АДЕЛИЯ • ИТОГ ДНЯ','', 'День почти закрыт. Я собрала остаток, чтобы ничего не потерялось 💜','',
           f'✅ Проведено занятий: {int(done or 0)}',f'❌ Отменено: {int(cancelled or 0)}',
           f"💬 Сообщений ждут ответа: {int(d['open_messages'] or 0)}",
           (f"💳 Неоплаченных занятий: {int(unpaid[0] or 0)} · {int(unpaid[1] or 0):,} ₽".replace(',',' ') if _on('notify_payment','1') else '💳 Оплаты: уведомления выключены'),
           f"⚠️ Требуют внимания: {len(d['attention'])}",f'📅 Занятий завтра: {int(tomorrow or 0)}']
    for aid in _admins():
        try:
            await context.bot.send_message(aid,'\n'.join(lines),reply_markup=_queue_markup(False));database.set_setting('evening_brief_last_ok',datetime.now(_tz()).isoformat(timespec='minutes')); database.log_automation_delivery('evening_brief','OK','ADMIN',aid)
        except Exception as e:
            database.log_automation_delivery('evening_brief','ERROR','ADMIN',aid,repr(e)); log.exception('ADELIA EVENING BRIEF SEND ERROR admin=%s',aid)


async def student_day_brief_job(context, force=False):
    """Send one local-morning summary per student on days with lessons.

    Each student uses their own MСК-relative timezone. Users who have not yet
    configured a region temporarily inherit the teacher/TutorBot timezone.
    """
    c = database.connect()
    try:
        rows = c.execute("""
            SELECT l.*, u.name, u.telegram_id, u.board_url
            FROM lessons l
            JOIN users u ON u.id = l.user_id
            WHERE date(l.start_time) BETWEEN date('now','-1 day') AND date('now','+2 day')
              AND l.lesson_status IN ('PENDING','CONFIRMED','IN_PROGRESS')
              AND u.active = 1
              AND u.telegram_id IS NOT NULL
            ORDER BY u.id, l.start_time
        """).fetchall()
    except Exception:
        log.exception('ADELIA STUDENT DAY BRIEF DB ERROR')
        rows = []
    finally:
        c.close()

    grouped = {}
    for row in rows:
        grouped.setdefault(int(row['user_id']), []).append(row)

    target = database.get_setting('student_day_brief_time','08:00') or '08:00'
    teacher_zone = database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'

    for uid, candidate_lessons in grouped.items():
        first = candidate_lessons[0]
        tid = int(first['telegram_id'])
        tz = user_timezone.user_tz(tid, teacher_zone)
        local_now = datetime.now(tz)
        if not force and local_now.strftime('%H:%M') != target:
            continue
        day = local_now.date().isoformat()
        lessons = []
        for lesson in candidate_lessons:
            local_start = user_timezone.convert_for_user(lesson['start_time'], tid, teacher_zone)
            if local_start and local_start.date().isoformat() == day:
                lessons.append((lesson, local_start))
        if not lessons:
            continue
        sent_key = f'student_day_brief_last_day_{uid}'
        if not force and (database.get_setting(sent_key, '') or '') == day:
            continue

        lines = [
            '💜 АДЕЛИЯ • СЕГОДНЯ ЗАНЯТИЕ',
            '',
            f"Доброе утро, {first['name']}!",
            'Сегодня у тебя ' + ('занятие.' if len(lessons) == 1 else f'занятий: {len(lessons)}.'),
            f"🌍 Время: {user_timezone.user_label(tid, teacher_zone)}",
            '',
        ]
        for lesson, local_start in lessons:
            subject = (lesson['subject'] or lesson['study_goal'] or 'занятие').strip()
            lines.append(f"🕐 {local_start.strftime('%H:%M')} · {subject} · {int(lesson['duration_minutes'] or 0)} мин")
        lines += ['', 'Я всё держу под рукой — если планы изменятся, актуальная информация будет в TutorBot 💜']
        buttons = [[InlineKeyboardButton('📅 Мои занятия', callback_data='lessons')]]
        if first['board_url']:
            buttons.append([InlineKeyboardButton('🖥 Доска', url=first['board_url'])])
        buttons.append([InlineKeyboardButton('🌍 Сменить часовой пояс', callback_data='tz_menu')])
        buttons.append([InlineKeyboardButton('🏠 Главная', callback_data='global_home')])
        try:
            await context.bot.send_message(tid, '\n'.join(lines), reply_markup=InlineKeyboardMarkup(buttons))
            if not force:
                database.set_setting(sent_key, day)
            database.log_automation_delivery('student_day_brief','OK','STUDENT',uid)
        except Exception as e:
            database.log_automation_delivery('student_day_brief','ERROR','STUDENT',uid,repr(e)); log.exception('ADELIA STUDENT DAY BRIEF SEND ERROR user=%s', uid)


async def timezone_migration_job(context, remind=False):
    """One-time region setup invitation for existing registered accounts."""
    if not _on('timezone_migration_enabled','1'):
        return
    try:
        from handlers import timezone_handlers
        recipients = {}
        for user in database.get_all_users(active_only=True):
            if user['telegram_id']:
                recipients[int(user['telegram_id'])] = ('STUDENT', user['name'])
        for parent in database.get_all_parents(active_only=True):
            if parent['telegram_id']:
                recipients[int(parent['telegram_id'])] = ('PARENT', parent['name'])
        for admin_id in _admins():
            recipients[int(admin_id)] = ('ADMIN', 'Преподаватель')

        sent = 0
        for tid, (role, name) in recipients.items():
            if remind:
                if database.timezone_configured(tid):
                    continue
            elif not database.timezone_notification_pending(tid):
                continue
            text = (
                '💜 АДЕЛИЯ • НАСТРОЙКА ВРЕМЕНИ\n\n'
                'В TutorBot появилась персональная настройка времени 🌍\n\n'
                'Теперь расписание, свободные окна, занятия и локальные ежедневные уведомления '
                'я могу показывать именно по вашему времени.\n\n'
                'Выберите регион. Если нужного варианта нет — нажмите «Другой часовой пояс» и напишите разницу с Москвой.'
            )
            try:
                await context.bot.send_message(tid, text, reply_markup=timezone_handlers.timezone_markup(tid, include_back=False))
                database.mark_timezone_notified(tid)
                database.log_automation_delivery('timezone_setup_notice','OK',role,tid)
                sent += 1
                await asyncio.sleep(0.08)
            except Forbidden as exc:
                # Деактивируем только ученика и только когда Telegram
                # явно подтвердил блокировку бота пользователем.
                if (
                    role == 'STUDENT'
                    and 'blocked by the user' in str(exc).lower()
                ):
                    user = database.get_user_by_telegram_id(tid)

                    if user is not None:
                        database.set_user_active(
                            user['id'],
                            False,
                        )

                database.log_automation_delivery(
                    'timezone_setup_notice',
                    'SKIPPED',
                    role,
                    tid,
                    'BOT_BLOCKED',
                )
                log.info(
                    'TIMEZONE MIGRATION SKIP BLOCKED tid=%s role=%s',
                    tid,
                    role,
                )
            except Exception as exc:
                database.log_automation_delivery(
                    'timezone_setup_notice',
                    'ERROR',
                    role,
                    tid,
                    repr(exc),
                )
                log.exception(
                    'TIMEZONE MIGRATION NOTICE ERROR tid=%s',
                    tid,
                )
            if sent >= 100:
                break
    except Exception:
        log.exception('TIMEZONE MIGRATION JOB ERROR')

async def brief_dispatcher(context):
    now=datetime.now(_tz()); hhmm=now.strftime('%H:%M'); day=now.strftime('%Y-%m-%d')
    for kind,func,default in [('morning',morning_brief_job,'08:30'),('evening',evening_brief_job,'21:00')]:
        if not _on(f'{kind}_brief_enabled','1'):continue
        target=database.get_setting(f'{kind}_brief_time',default) or default
        if hhmm != target:continue
        sent=database.get_setting(f'{kind}_brief_last_day','') or ''
        if sent==day:continue
        await func(context);database.set_setting(f'{kind}_brief_last_day',day)

    # Each student receives the morning summary at the configured clock time
    # in their own selected region/timezone.
    if _on('student_day_brief_enabled','1'):
        await student_day_brief_job(context)

def register(application):
    jq=application.job_queue
    if not jq:return
    # Minute dispatcher makes time changes effective immediately and uses an explicit configurable timezone.
    jq.run_repeating(brief_dispatcher,interval=60,first=5,name='crm_brief_dispatcher')
    jq.run_repeating(timezone_migration_job,interval=300,first=20,name='timezone_migration_notifier')
    jq.run_repeating(messenger.delivery_job,interval=60,first=15,name='crm_messenger_delivery')
