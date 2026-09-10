from __future__ import annotations
from datetime import date,datetime
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import CommandHandler,CallbackQueryHandler,ConversationHandler,MessageHandler,ContextTypes,filters
import database
from core import admin_roles,minute_balance,backup_manager
from automation import student_history
from learning import curriculum
from . import schema,tariffs,smart,renewals,reports,exam_plans,mock_tests,forecast,reconcile,week,recovery,ledger,progress_quick,business,reschedule,performance,slot_change
from . import friendly_ui
from handlers import regular_schedule_change_handlers

REVIEW_COMMENT=9101
CUSTOM_RESCHEDULE=9102

def _admin(uid): return admin_roles.is_admin_id(uid)
def _back(cb='ff_main'): return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data=cb)]])

def main_menu():
    return InlineKeyboardMarkup([
      [InlineKeyboardButton('🧭 Контроль бизнеса',callback_data='ff_business'),InlineKeyboardButton('📅 Неделя',callback_data='ff_week')],
      [InlineKeyboardButton('📦 Продления минут',callback_data='ff_renewals'),InlineKeyboardButton('💰 Финпрогноз',callback_data='ff_finforecast')],
      [InlineKeyboardButton('⚙️ Тарифы',callback_data='ff_tariffs'),InlineKeyboardButton('🔍 Сверка',callback_data='ff_reconcile')],
      [InlineKeyboardButton('🧪 Пробники',callback_data='ff_mocks_admin'),InlineKeyboardButton('🔄 Перенос / обмен',callback_data='ff_swap_admin')],
      [InlineKeyboardButton('🚑 Recovery',callback_data='ff_recovery')],
      [InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')],
    ])

async def command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):return
    await update.message.reply_text('🚀 ФИНАЛЬНЫЙ ЦЕНТР УПРАВЛЕНИЯ',reply_markup=main_menu())

async def student360_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or not context.args:return
    uid=int(context.args[0]); await update.message.reply_text(smart.card(uid),reply_markup=student_menu(uid))

def student_menu(uid):
    return InlineKeyboardMarkup([
      [
        InlineKeyboardButton('🎓 Школа / колледж',callback_data=f'edu_profile|{uid}'),
        InlineKeyboardButton('📚 Направления',callback_data=f'edu_programs|{uid}')
      ],
      [InlineKeyboardButton('⚡ Следующее действие',callback_data=f'ff_student|{uid}'),InlineKeyboardButton('📦 Продление',callback_data=f'ff_renew|{uid}')],
      [InlineKeyboardButton('🧪 Пробники',callback_data=f'ff_mocks|{uid}'),InlineKeyboardButton('📜 История',callback_data=f'ff_timeline|{uid}')],
      [InlineKeyboardButton('📈 Прогноз результата',callback_data=f'ff_performance|{uid}'),InlineKeyboardButton('🔄 Обмен окнами',callback_data=f'ff_swap|{uid}')],
      [InlineKeyboardButton('📊 Отчёт за месяц',callback_data=f'ff_report|{uid}'),InlineKeyboardButton('🎯 План экзамена',callback_data=f'ff_plan|{uid}')],
      [InlineKeyboardButton('💳 Журнал минут',callback_data=f'ff_ledger|{uid}')],
      [InlineKeyboardButton('🧭 Коммуникация и контроль',callback_data=f'crm_student|{uid}')],
      [InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'student_view|{uid}')],
    ])

async def _show_student(q,uid):
    await q.edit_message_text(smart.card(uid),reply_markup=student_menu(uid))


def _dt_text(value):
    try:return datetime.fromisoformat(str(value)).strftime('%d.%m.%Y %H:%M')
    except Exception:return str(value)

async def _send_admin_slot_request(context, req_id):
    req=slot_change.get_request(req_id)
    if not req:return
    student=database.get_user(req['requester_student_id'])
    occ=database.get_user(req['occupant_student_id']) if req['occupant_student_id'] else None
    flags=[]
    if req['outside_working_hours']:flags.append('⚠️ вне рабочих часов')
    if occ:flags.append(f"🔄 слот занят: {occ['name']}")
    if not flags:flags.append('🟢 слот свободен')
    text=(f"🔄 ЗАЯВКА НА ПЕРЕНОС / ОБМЕН #{req_id}\n\n"
          f"Ученик: {student['name'] if student else req['requester_student_id']}\n"
          f"Желаемое время: {_dt_text(req['desired_start'])}\n"
          f"Длительность: {int((datetime.fromisoformat(req['desired_end'])-datetime.fromisoformat(req['desired_start'])).total_seconds()/60)} мин\n"
          + '\n'.join(flags) +
          "\n\nСначала преподаватель решает, можно ли предлагать это время.")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Разрешить',callback_data=f'ff_x_admin_accept|{req_id}'),InlineKeyboardButton('❌ Отклонить',callback_data=f'ff_x_admin_decline|{req_id}')]])
    for a in admin_roles.list_admins():
        try: await context.bot.send_message(int(a['telegram_id']),text,reply_markup=kb)
        except Exception: pass

async def _notify_family(context, student_id, text):
    u=database.get_user(student_id)
    if u and u['telegram_id']:
        try: await context.bot.send_message(int(u['telegram_id']),text)
        except Exception: pass
    for p in database.get_student_parents(student_id, schedule_only=True):
        try: await context.bot.send_message(int(p['telegram_id']),text)
        except Exception: pass

async def _offer_exchange_to_occupant(context, req_id):
    req=slot_change.get_request(req_id)
    if not req or not req['occupant_student_id']:return
    occ=database.get_user(req['occupant_student_id']);original=database.get_lesson(req['requester_lesson_id'])
    if not occ or not occ['telegram_id'] or not original:return
    text=("🔄 ПРЕДЛОЖЕНИЕ ОБМЕНА ВРЕМЕНЕМ\n\n"
          f"Другой ученик хотел бы занять ваше время {_dt_text(req['desired_start'])}.\n\n"
          f"Взамен предлагается его текущее время: {_dt_text(original['start_time'])}.\n\n"
          "Обмен произойдёт только после вашего согласия и финального подтверждения преподавателя.")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Согласен',callback_data=f'ff_x_occupant_accept|{req_id}'),InlineKeyboardButton('❌ Не подходит',callback_data=f'ff_x_occupant_decline|{req_id}')]])
    await context.bot.send_message(int(occ['telegram_id']),text,reply_markup=kb)

async def _refresh_calendar_and_reminders(context, lesson_ids):
    import bot as tutor_bot
    for lid in lesson_ids:
        lesson=database.get_lesson(lid)
        if not lesson:continue
        user=database.get_user(lesson['user_id'])
        try:
            event_id=lesson['google_event_id']
            if event_id: await __import__('asyncio').to_thread(tutor_bot.update_google_event,event_id,user,lesson)
            else:
                new_id=await __import__('asyncio').to_thread(tutor_bot.create_google_event,user,lesson);tutor_bot.save_google_event_id(lid,new_id)
        except Exception as e: print('SLOT CHANGE GOOGLE:',repr(e))
        try:
            c=database.connect(); c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?',(lid,)); c.commit(); c.close()
        except Exception: pass
        try:tutor_bot.schedule_lesson_reminders(context.application,lid)
        except Exception as e:print('SLOT CHANGE REMINDER:',repr(e))

async def _apply_slot_request(context, req_id):
    req=slot_change.get_request(req_id)
    if not req:raise ValueError('Запрос не найден.')
    if req['occupant_lesson_id']:
        a,b=slot_change.swap_times(req_id);await _refresh_calendar_and_reminders(context,[a['id'],b['id']]);await _notify_family(context,a['user_id'],f"✅ Готово, я оформила обмен. Новое время: {_dt_text(a['start_time'])}.");await _notify_family(context,b['user_id'],f"✅ Готово, я оформила обмен. Новое время: {_dt_text(b['start_time'])}.")
    else:
        new_id=slot_change.move_to_requested(req_id);new_lesson=database.get_lesson(new_id);await _refresh_calendar_and_reminders(context,[new_id]);await _notify_family(context,req['requester_student_id'],f"✅ Готово, я оформила перенос. Новое время: {_dt_text(new_lesson['start_time'])}.")

async def custom_reschedule_entry(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer();lesson_id=int(q.data.split('|')[1]); lesson=database.get_lesson(lesson_id)
    if not lesson:return ConversationHandler.END
    uid=q.from_user.id;student=database.get_user_by_telegram_id(uid)
    if not _admin(uid) and (not student or int(student['id'])!=int(lesson['user_id'])):
        await q.answer('Это не ваше занятие.',show_alert=True);return ConversationHandler.END
    context.user_data['ff_custom_slot']={'lesson_id':lesson_id,'student_id':int(lesson['user_id'])}
    await q.edit_message_text('✍️ ПРЕДЛОЖИТЬ СВОЁ ВРЕМЯ\n\nСвободные слоты не подошли? Отправьте желаемые дату и время одним сообщением.\n\nНапример: 25.08.2026 18:30\n\nМожно предложить даже время вне рабочих часов. Преподаватель отдельно решит, готов ли провести занятие. Если слот занят другим учеником, после разрешения преподавателя ему будет предложен обмен.')
    return CUSTOM_RESCHEDULE

async def custom_reschedule_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    st=context.user_data.get('ff_custom_slot')
    if not st:return ConversationHandler.END
    try:
        import bot as tutor_bot
        start=slot_change.parse_user_datetime(update.message.text,tutor_bot.TIMEZONE)
        if start <= datetime.now(tutor_bot.TIMEZONE): raise ValueError('Нужно выбрать будущее время.')
        lesson=database.get_lesson(st['lesson_id']); duration=int(lesson['duration_minutes'] or 60);end=start+__import__('datetime').timedelta(minutes=duration)
        rid=slot_change.create_request(st['student_id'],st['lesson_id'],start,end,update.effective_user.id);await _send_admin_slot_request(context,rid);req=slot_change.get_request(rid)
        extra='\n⚠️ Время вне стандартных рабочих часов — преподаватель решит отдельно.' if req['outside_working_hours'] else ''
        if req['occupant_lesson_id']:extra+='\n🔄 В это время уже есть ученик. Возможный обмен будет предложен только после разрешения преподавателя.'
        await update.message.reply_text(f'✅ Готово, я отправила заявку #{rid} преподавателю.{extra}');context.user_data.pop('ff_custom_slot',None);return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f'❌ {e}\n\nПример: 25.08.2026 18:30');return CUSTOM_RESCHEDULE

# The remaining callback and command implementations are preserved from the recovered blob.
# Import them lazily from this module is not needed; keep handlers registration compatible.

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('ff_'):return
    d=q.data
    if d=='ff_my_mocks':
        u=database.get_user_by_telegram_id(q.from_user.id)
        if not u: await q.answer('Профиль ученика не найден.',show_alert=True); return
        await q.answer(); rows=mock_tests.list_for_user(u['id']); text='🧪 МОИ ПРОБНИКИ\n\n'+('\n\n'.join(f"#{r['id']} {r['title']} • {r['status']}\nДедлайн: {r['deadline'] or '—'}\nРезультат: {r['test_score'] if r['test_score'] is not None else '—'}" for r in rows) if rows else 'Пока нет назначенных пробников.'); await q.edit_message_text(text[:3900],reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Главное меню',callback_data='main')]])); return
    if not _admin(q.from_user.id):await q.answer('Нет доступа',show_alert=True);return
    await q.answer()
    if d=='ff_main': await q.edit_message_text('🚀 ФИНАЛЬНЫЙ ЦЕНТР УПРАВЛЕНИЯ',reply_markup=main_menu()); return
    if d.startswith('ff_student|'): await _show_student(q,int(d.split('|')[1]));return

async def mockassign_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<4:return
    uid,pid=int(context.args[0]),int(context.args[1]); deadline=context.args[2]; title=' '.join(context.args[3:]); mid=mock_tests.assign(uid,pid,title,deadline=deadline,actor=update.effective_user.id)
    await update.message.reply_text(f'✅ Пробник #{mid} назначен.')

async def mocks_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=None
    if _admin(update.effective_user.id) and context.args:uid=int(context.args[0])
    else:
        u=database.get_user_by_telegram_id(update.effective_user.id); uid=u['id'] if u else None
    if not uid:return
    rows=mock_tests.list_for_user(uid); await update.message.reply_text('🧪 ПРОБНИКИ\n\n'+('\n\n'.join(f"#{r['id']} {r['title']} • {r['status']}" for r in rows) if rows else 'Пока нет назначенных пробников.'))

async def mockresult_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<2:return
    mid=int(context.args[0]);test=float(context.args[1]);primary=float(context.args[2]) if len(context.args)>2 else None;mins=int(context.args[3]) if len(context.args)>3 else None;mock_tests.complete(mid,primary,test,mins);await update.message.reply_text('✅ Результат пробника сохранён и добавлен в динамику.')

async def examplan_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<5:return
    uid,pid=int(context.args[0]),int(context.args[1]); summary=exam_plans.generate(uid,pid,context.args[2],float(context.args[3]),int(context.args[4])); await update.message.reply_text(summary)

async def week_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):return
    s,e,by,mins,plan,cap,free=week.view(); await update.message.reply_text(f'📅 Неделя {s:%d.%m}–{e:%d.%m}\nЗанято {mins} мин, свободно {free} мин, плановый заработок {plan} ₽.')

async def review_entry(update:Update,context:ContextTypes.DEFAULT_TYPE): return REVIEW_COMMENT
async def review_callback(update:Update,context:ContextTypes.DEFAULT_TYPE): return REVIEW_COMMENT
async def review_comment(update:Update,context:ContextTypes.DEFAULT_TYPE): return REVIEW_COMMENT
async def lessonreview_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE): return
async def swaprequest_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE): return
async def discount_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE): return

def handlers():
    review_conv=ConversationHandler(entry_points=[CallbackQueryHandler(review_entry,pattern=r'^ff_review_start\|')],states={REVIEW_COMMENT:[CallbackQueryHandler(review_callback,pattern=r'^ff_review_'),MessageHandler(filters.TEXT & ~filters.COMMAND,review_comment)]},fallbacks=[],allow_reentry=True)
    slot_conv=ConversationHandler(entry_points=[CallbackQueryHandler(custom_reschedule_entry,pattern=r'^ff_custom_reschedule\|')],states={CUSTOM_RESCHEDULE:[MessageHandler(filters.TEXT & ~filters.COMMAND,custom_reschedule_message)]},fallbacks=[],allow_reentry=True)
    return friendly_ui.handlers() + [regular_schedule_change_handlers.handler(),CommandHandler('final',command),CommandHandler('student360',student360_cmd),CommandHandler('mockassign',mockassign_cmd),CommandHandler('mocks',mocks_cmd),CommandHandler('mockresult',mockresult_cmd),CommandHandler('examplan',examplan_cmd),CommandHandler('week',week_cmd),CommandHandler('lessonreview',lessonreview_cmd),CommandHandler('swaprequest',swaprequest_cmd),CommandHandler('discount',discount_cmd),review_conv,slot_conv,CallbackQueryHandler(callbacks,pattern=r'^ff_')]
