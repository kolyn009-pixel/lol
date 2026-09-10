from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden

import database
from core import admin_roles
from automation import schedule_tools
from handlers import runtime_patch_v2, review_v2, pricing_ux_patch
from vk_adapter import telegram_link, lesson_link_bridge


def _admins():
    try:return [int(r["telegram_id"]) for r in admin_roles.list_admins() if r["active"]]
    except Exception:return []

def _timezone():
    name=database.get_setting("bot_timezone","Europe/Samara") or "Europe/Samara"
    try:return ZoneInfo(name)
    except Exception:return ZoneInfo("Europe/Samara")

def _has_vk_channel(user_id):
    try:
        c=database.connect()
        try:return bool(c.execute("SELECT 1 FROM channel_identities WHERE user_id=? AND channel='VK' AND enabled=1 LIMIT 1",(int(user_id),)).fetchone())
        finally:c.close()
    except Exception:return False

def _weekly_text():
    c=database.connect()
    try:
        done=c.execute("SELECT COUNT(*) FROM lessons WHERE finished_at IS NOT NULL AND datetime(finished_at)>=datetime('now','-7 days')").fetchone()[0]
        cancelled=c.execute("SELECT COUNT(*) FROM lessons WHERE cancelled_at IS NOT NULL AND datetime(cancelled_at)>=datetime('now','-7 days')").fetchone()[0]
        active=c.execute("SELECT COUNT(*) FROM users WHERE active=1").fetchone()[0];msgs=0
        try:msgs=c.execute("SELECT COUNT(*) FROM crm_student_messages WHERE direction='IN' AND datetime(created_at)>=datetime('now','-7 days')").fetchone()[0]
        except Exception:pass
    finally:c.close()
    unpaid=pricing_ux_patch.weekly_payment_snapshot()
    return ("💜 АДЕЛИЯ • НЕДЕЛЯ\n\nЯ собрала короткий итог за последние 7 дней.\n\n"+f"✅ Проведено занятий: {done}\n❌ Отменено: {cancelled}\n💬 Входящих сообщений: {msgs}\n💳 Ближайших занятий ждут оплаты: {int(unpaid['count'])} · {int(unpaid['amount']):,} ₽\n👥 Активных учеников: {active}\n\nСумма ожидания оплаты считается по актуальным индивидуальным ставкам и только по ближайшему занятию каждого ученика.\n\nЕсли хотите разобраться подробнее — откройте «Разобрать всё».").replace(","," ")

def _active_students():
    c=database.connect()
    try:return c.execute("SELECT id,name,grade,telegram_id,telegram_username,COALESCE(trial_used,0) AS trial_used FROM users WHERE active=1 AND telegram_id IS NOT NULL ORDER BY grade,name COLLATE NOCASE").fetchall()
    finally:c.close()

async def weekly_booking_reminders(context):
    enabled=str(database.get_setting("weekly_booking_reminder_enabled","1")).lower()
    if enabled in ("0","false","off","no"):return
    today=datetime.now(_timezone()).date().isoformat();sent=paused_count=future_count=errors=0;blocked=[]
    for student in _active_students():
        uid=int(student["id"]);tid=int(student["telegram_id"])
        try:
            if schedule_tools.is_paused(uid,today):paused_count+=1;continue
            if database.get_upcoming_lessons(uid):future_count+=1;continue
            trial_available=not bool(int(student["trial_used"] or 0))
            if trial_available:text=f"💜 {student['name']}, привет!\n\nЯ посмотрела расписание и пока не вижу следующего занятия.\n\nУ тебя ещё доступно пробное занятие — можно выбрать удобную дату и познакомиться с форматом 👇";label="🎁 Записаться на пробное"
            else:text=f"💜 {student['name']}, привет!\n\nЯ посмотрела твоё расписание и пока не вижу следующего занятия.\n\nЧтобы не выпадать из подготовки, можешь заранее выбрать удобную дату и время 👇";label="📅 Записаться"
            await context.bot.send_message(chat_id=tid,text=text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(label,callback_data="booking")],[InlineKeyboardButton("🏠 Главная",callback_data="global_home")]]));database.log_automation_delivery("weekly_booking_reminder","OK","STUDENT",uid);sent+=1
        except Forbidden as exc:
            if "blocked by the user" in str(exc).lower():
                has_vk=_has_vk_channel(uid)
                if not has_vk:database.set_user_active(uid,False)
                username=str(student["telegram_username"] or "").strip().lstrip("@");suffix=" • VK остаётся активным" if has_vk else " • ученик выключен";blocked.append(f"• {student['name'] or 'Без имени'}"+(f" — @{username}" if username else " — ник не указан")+suffix);database.log_automation_delivery("weekly_booking_reminder","SKIPPED","STUDENT",uid,"BOT_BLOCKED_VK_ACTIVE" if has_vk else "BOT_BLOCKED_NO_OTHER_CHANNEL")
            else:errors+=1;database.log_automation_delivery("weekly_booking_reminder","ERROR","STUDENT",uid,repr(exc))
        except Exception as exc:errors+=1;database.log_automation_delivery("weekly_booking_reminder","ERROR","STUDENT",uid,repr(exc))
    database.set_setting("weekly_booking_reminder_last_stats",f"sent={sent};future={future_count};pause={paused_count};blocked={len(blocked)};errors={errors}")
    if blocked:
        text="🚫 АДЕЛИЯ • БЛОКИРОВКИ\n\n"+f"Новых блокировок Telegram обнаружено: {len(blocked)}\n\n"+"\n".join(blocked)+"\n\nЕсли у ученика подключён VK, карточка остаётся активной и работа продолжается через VK."
        for aid in _admins():
            try:await context.bot.send_message(aid,text)
            except Exception:pass

async def weekly_job(context):
    if str(database.get_setting("notify_weekly","1")).lower() in ("0","false","off","no"):return
    text=_weekly_text()
    for aid in _admins():
        try:await context.bot.send_message(aid,text);database.log_automation_delivery("weekly_summary","OK","ADMIN",aid)
        except Exception as exc:database.log_automation_delivery("weekly_summary","ERROR","ADMIN",aid,repr(exc))

async def weekly_dispatcher(context):
    if str(database.get_setting("notify_weekly","1")).lower() in ("0","false","off","no"):return
    now=datetime.now(_timezone())
    if now.weekday()!=0:return
    target=database.get_setting("weekly_summary_time","09:00") or "09:00"
    if now.strftime("%H:%M")!=target:return
    day=now.date().isoformat()
    if (database.get_setting("weekly_summary_last_day","") or "")==day:return
    await weekly_job(context);await weekly_booking_reminders(context);database.set_setting("weekly_summary_last_day",day)

async def homework_watchdog_job(context):
    """Evaluate individual/group deadlines and queue durable notifications."""
    try:
        import asyncio
        from web_backend import homework_watchdog
        queued=await asyncio.to_thread(homework_watchdog.tick)
        database.set_setting("homework_watchdog_last_stats",f"queued={queued}")
        database.set_setting("homework_watchdog_last_error","")
    except Exception as exc:
        database.set_setting("homework_watchdog_last_error",repr(exc)[:500])
        print("HOMEWORK WATCHDOG JOB:",repr(exc),flush=True)

def register(application):
    runtime_patch_v2.install(application);review_v2.install(application);pricing_ux_patch.install(application);lesson_link_bridge.install();jq=application.job_queue
    if not jq:return
    jq.run_repeating(weekly_dispatcher,interval=60,first=20,name="adelia_weekly_dispatcher")
    jq.run_repeating(runtime_patch_v2.regular_series_sync_job,interval=6*60*60,first=45,name="adelia_regular_full_sync")
    jq.run_repeating(homework_watchdog_job,interval=5*60,first=75,name="adelia_homework_watchdog")
