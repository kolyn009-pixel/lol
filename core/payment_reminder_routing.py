from __future__ import annotations

import database
from core import user_timezone

_INSTALLED = False


def parent_telegram_ids(student_id, user=None):
    result=[];seen=set()
    try:
        for parent in database.get_student_parents(int(student_id)):
            tid=parent['telegram_id'] if 'telegram_id' in parent.keys() else None
            if tid is not None and int(tid) not in seen: seen.add(int(tid));result.append(int(tid))
    except Exception: pass
    if not result:
        if user is None:
            try:user=database.get_user(int(student_id))
            except Exception:user=None
        try:legacy=user['parent_telegram_id'] if user is not None and 'parent_telegram_id' in user.keys() else None
        except Exception:legacy=None
        if legacy and int(legacy) not in seen:result.append(int(legacy))
    return result


def has_parent_recipient(student_id,user=None):return bool(parent_telegram_ids(student_id,user=user))


def _name(lesson):
    try:
        u=database.get_user(int(lesson['user_id']));return str(u['name'] or 'Ученик') if u else 'Ученик'
    except Exception:return 'Ученик'


async def _notify_teacher(context,lesson_id,lesson):
    text=f"💳 До занятия 2 часа — оплата не подтверждена\n\n👤 {_name(lesson)}\nОткройте «Сегодня» в Аделии и выберите: ждать оплату или отменить занятие."
    try:
        from core import admin_roles
        for tid in admin_roles.get_admin_telegram_ids(): await context.bot.send_message(chat_id=int(tid),text=text)
    except Exception:pass
    try:
        from vk_adapter import schema as s,app
        for peer in s.get_admin_external_ids('VK'):app.send(int(peer),text,linked=True,mode='teacher')
    except Exception:pass


def install():
    """Route parent payment reminders and gate the legacy T-2h auto-cancel."""
    global _INSTALLED
    if _INSTALLED:return
    import __main__ as runtime
    original=getattr(runtime,'payment_reminder_job',None)
    original_deadline=getattr(runtime,'payment_deadline_job',None)
    if original is None or getattr(original,'_adelia_parent_payment_routing',False):return

    async def payment_reminder_job(context):
        data=getattr(context.job,'data',None) or {};lesson_id=data.get('lesson_id');reminder_type=data.get('reminder_type')
        if not lesson_id:return await original(context)
        lesson=database.get_lesson(int(lesson_id))
        if lesson is None:return await original(context)
        user=database.get_user(int(lesson['user_id']))
        if user is None:return await original(context)
        recipients=parent_telegram_ids(int(user['id']),user=user)
        if not recipients:return await original(context)
        if str(database.get_setting('notify_payment','1')).lower() in ('0','false','off','no'):return
        if database.reminder_was_sent(int(lesson_id),str(reminder_type)):return
        if str(lesson['lesson_status'] or '')!='CONFIRMED' or str(lesson['payment_status'] or '')!='AWAITING_PAYMENT':return
        names={'PAYMENT_24H':'До занятия осталось меньше суток.','PAYMENT_8H':'До занятия осталось около 8 часов.'}
        try:amount=runtime.payments.money(lesson['price'])
        except Exception:amount=f"{int(lesson['price'] or 0):,} ₽".replace(',',' ')
        from telegram import InlineKeyboardButton,InlineKeyboardMarkup
        delivered=0
        for parent_tid in recipients:
            try:when=user_timezone.format_day_time_for_user(lesson['start_time'],int(parent_tid),runtime.TIMEZONE_NAME,with_zone=True)
            except Exception:when=runtime.format_datetime(lesson['start_time'])
            text=(f"💳 Небольшое напоминание об оплате 💜\n\n👤 Ученик: {user['name']}\n📅 {when}\n💰 {amount}\n\n{names.get(str(reminder_type),'')}\n\nПожалуйста, подтвердите оплату не позднее чем за 2 часа до занятия. Иначе слот потребует решения преподавателя.")
            try:
                await context.bot.send_message(chat_id=int(parent_tid),text=text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('👤 Открыть кабинет ученика',callback_data=f"parent_child|{int(user['id'])}")]]));delivered+=1
            except Exception as exc:print('PARENT PAYMENT REMINDER ERROR:',user['id'],parent_tid,repr(exc),flush=True)
        if delivered:database.mark_reminder_sent(int(lesson_id),str(reminder_type))

    payment_reminder_job._adelia_parent_payment_routing=True;payment_reminder_job._adelia_original=original;runtime.payment_reminder_job=payment_reminder_job

    if original_deadline is not None and not getattr(original_deadline,'_adelia_teacher_payment_decision',False):
        async def payment_deadline_job(context):
            data=getattr(context.job,'data',None) or {};lesson_id=data.get('lesson_id')
            if not lesson_id:return await original_deadline(context)
            lesson=database.get_lesson(int(lesson_id))
            if lesson is None or str(lesson['lesson_status'] or '').upper()!='CONFIRMED' or str(lesson['payment_status'] or '').upper()!='AWAITING_PAYMENT':return await original_deadline(context)
            from core import payment_wait_control
            state=payment_wait_control.get(int(lesson_id))
            if state and state.get('teacher_wait_confirmed_at'):return
            if not state or not state.get('risk_notified_at'):
                payment_wait_control.mark_risk(int(lesson_id))
                try:
                    from web_backend import push_events
                    push_events.teachers('💳 До занятия 2 часа — оплаты нет',f"{_name(lesson)}: оплата не подтверждена. Решите, ждать оплату или отменить занятие.",'/teacher/',f'payment-risk-{int(lesson_id)}',{'type':'payment_risk','lesson_id':int(lesson_id)})
                except Exception as exc:print('TEACHER PAYMENT RISK PUSH ERROR:',int(lesson_id),repr(exc),flush=True)
                await _notify_teacher(context,int(lesson_id),lesson)
            # No immediate legacy cancellation: teacher must decide first.
            # Payment remains AWAITING_PAYMENT, so lesson start stays blocked.
            return
        payment_deadline_job._adelia_teacher_payment_decision=True;payment_deadline_job._adelia_original=original_deadline;runtime.payment_deadline_job=payment_deadline_job
    _INSTALLED=True
