from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from final_features import regular_schedule_change

WEEKDAY = 9601
TIME = 9602
DURATION = 9603
NOTE = 9604

WEEKDAYS = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']


def _student(update: Update):
    return database.get_user_by_telegram_id(update.effective_user.id)


def _kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Отмена', callback_data='regular_change_cancel')]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    student = _student(update)
    if not student:
        await q.edit_message_text('Профиль ученика не найден.')
        return ConversationHandler.END
    schedules = regular_schedule_change.schedules_for_student(int(student['id']))
    if not schedules:
        await q.edit_message_text('У тебя нет активного постоянного расписания.')
        return ConversationHandler.END
    rows=[]
    for s in schedules:
        rows.append([InlineKeyboardButton(
            f"{WEEKDAYS[int(s['weekday'])]} · {s['start_time']} · {int(s['duration_minutes'])} мин",
            callback_data=f"regular_change_pick|{int(s['id'])}"
        )])
    rows.append([InlineKeyboardButton('⬅️ Назад', callback_data='main')])
    await q.edit_message_text(
        '📅 ИЗМЕНИТЬ ПОСТОЯННОЕ РАСПИСАНИЕ\n\n'
        'Это изменит будущие занятия всей регулярной серии.\n'
        'Если нужно перенести только один урок — используй перенос в карточке конкретного занятия.\n\n'
        'Выбери серию:',
        reply_markup=InlineKeyboardMarkup(rows)
    )
    return WEEKDAY


async def pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    student=_student(update)
    sid=int(q.data.split('|')[1])
    schedules={int(x['id']):x for x in regular_schedule_change.schedules_for_student(int(student['id']))}
    if sid not in schedules:
        await q.answer('Это расписание недоступно.',show_alert=True)
        return ConversationHandler.END
    context.user_data['regular_change']={'schedule_id':sid}
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton(WEEKDAYS[i],callback_data=f'regular_change_weekday|{i}')] for i in range(7)
    ]+[[InlineKeyboardButton('⬅️ Отмена',callback_data='regular_change_cancel')]])
    await q.edit_message_text('Выбери новый постоянный день недели:',reply_markup=kb)
    return WEEKDAY


async def weekday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    st=context.user_data.get('regular_change')
    if not st:return ConversationHandler.END
    st['weekday']=int(q.data.split('|')[1])
    await q.edit_message_text(
        f"Новый день: {WEEKDAYS[st['weekday']]}\n\nОтправь новое время сообщением в формате ЧЧ:ММ, например 16:30.",
        reply_markup=_kb_back()
    )
    return TIME


async def time_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st=context.user_data.get('regular_change')
    if not st:return ConversationHandler.END
    value=(update.message.text or '').strip()
    try:
        hh,mm=map(int,value.split(':')[:2])
        if not (0<=hh<=23 and 0<=mm<=59 and mm in (0,30)):raise ValueError
    except Exception:
        await update.message.reply_text('Укажи время с шагом 30 минут, например 16:00 или 16:30.')
        return TIME
    st['start_time']=f'{hh:02d}:{mm:02d}'
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton(f'{d} мин',callback_data=f'regular_change_duration|{d}') for d in (60,90)],
        [InlineKeyboardButton('30 мин',callback_data='regular_change_duration|30'),InlineKeyboardButton('120 мин',callback_data='regular_change_duration|120')],
        [InlineKeyboardButton('⬅️ Отмена',callback_data='regular_change_cancel')]
    ])
    await update.message.reply_text('Выбери длительность постоянного занятия:',reply_markup=kb)
    return DURATION


async def duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    st=context.user_data.get('regular_change')
    if not st:return ConversationHandler.END
    st['duration']=int(q.data.split('|')[1])
    await q.edit_message_text(
        'Можно добавить короткий комментарий преподавателю — почему нужно изменить постоянное расписание.\n\n'
        'Если комментарий не нужен, отправь «-».',
        reply_markup=_kb_back()
    )
    return NOTE


async def note_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st=context.user_data.get('regular_change');student=_student(update)
    if not st or not student:return ConversationHandler.END
    note=(update.message.text or '').strip()
    if note=='-':note=''
    try:
        r=regular_schedule_change.create_request(
            int(student['id']),int(st['schedule_id']),int(st['weekday']),st['start_time'],int(st['duration']),source='TELEGRAM',note=note
        )
        conflicts=len((r.get('analysis') or {}).get('conflicts') or [])
        text=(f"✅ Заявка #{r['request_id']} отправлена преподавателю.\n\n"
              f"Новый график: {WEEKDAYS[int(st['weekday'])]} · {st['start_time']} · {st['duration']} мин.\n"
              "До подтверждения преподавателя текущее расписание не изменится.")
        if conflicts:
            text += f"\n\nНайдено конфликтов: {conflicts}. Система сначала предложит преподавателю безопасный вариант; чужие занятия автоматически не двигаются."
        await update.message.reply_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏠 Главное меню',callback_data='main')]]))
    except Exception as e:
        await update.message.reply_text(f'❌ Не удалось создать заявку: {e}')
    context.user_data.pop('regular_change',None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();context.user_data.pop('regular_change',None)
    await q.edit_message_text('Изменение постоянного расписания отменено.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏠 Главное меню',callback_data='main')]]))
    return ConversationHandler.END


def handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start,pattern=r'^regular_change_start$')],
        states={
            WEEKDAY:[CallbackQueryHandler(pick,pattern=r'^regular_change_pick\|'),CallbackQueryHandler(weekday,pattern=r'^regular_change_weekday\|')],
            TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND,time_message)],
            DURATION:[CallbackQueryHandler(duration,pattern=r'^regular_change_duration\|')],
            NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,note_message)],
        },
        fallbacks=[CallbackQueryHandler(cancel,pattern=r'^regular_change_cancel$')],
        allow_reentry=True,
    )
