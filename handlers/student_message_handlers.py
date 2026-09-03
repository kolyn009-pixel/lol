from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from automation import messaging
from core import event_center
from crm_plus import service as crm_service
from crm_plus import messenger as crm_messenger

WAIT_MESSAGE=940


def _student(update):
    return database.get_user_by_telegram_id(update.effective_user.id)


def _chat_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('✍️ Написать',callback_data='student_message_start'),
         InlineKeyboardButton('📜 История',callback_data='student_chat')],
        [InlineKeyboardButton('⬅️ Главное меню',callback_data='global_home')],
    ])


async def show_chat(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    user=database.get_user_by_telegram_id(q.from_user.id)
    if not user:
        await q.edit_message_text('Сначала нажми /start и зарегистрируйся — тогда я смогу открыть диалог 💜'); return ConversationHandler.END
    rows=crm_service.message_history(user['id'],20)
    lines=['💬 ПРЕПОДАВАТЕЛЬ','']
    if rows:
        for r in reversed(rows):
            who='👨‍🏫' if r['direction']=='OUT' else '👤'
            try: when=datetime.fromisoformat(str(r['created_at'])).strftime('%d.%m %H:%M')
            except Exception: when=str(r['created_at'])[5:16]
            status=''
            if r['status']=='QUEUED': status=' · ожидает доставки'
            lines.append(f"{who} {when}{status}\n{r['body']}")
    else:
        lines.append('Здесь пока нет сообщений. Когда появится переписка, я сохраню её здесь 💜')
    await q.edit_message_text('\n\n'.join(lines)[-3900:],reply_markup=_chat_markup())
    return ConversationHandler.END


async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    user=database.get_user_by_telegram_id(q.from_user.id)
    if not user:
        await q.edit_message_text('Сначала нажми /start и зарегистрируйся — тогда я смогу открыть диалог 💜'); return ConversationHandler.END
    context.user_data['student_message_uid']=user['id']
    kb=[[InlineKeyboardButton('❌ Отмена',callback_data='student_message_cancel')]]
    if crm_service.get_setting('urgent_enabled','0')=='1':
        kb.insert(0,[InlineKeyboardButton('🚨 Отправить как срочное',callback_data='student_message_urgent')])
    await q.edit_message_text(
        '💬 СООБЩЕНИЕ ПРЕПОДАВАТЕЛЮ\n\nНапишите сообщение следующим сообщением.\n'
        'Если вы пишете вне часов приёма, сообщение сохранится сразу и будет доставлено преподавателю в ближайшее время приёма.',
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return WAIT_MESSAGE



async def urgent_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    user=database.get_user_by_telegram_id(q.from_user.id)
    if not user or crm_service.get_setting('urgent_enabled','0')!='1':
        await q.answer('Срочные сообщения отключены.',show_alert=True); return ConversationHandler.END
    context.user_data['student_message_uid']=user['id'];context.user_data['student_message_urgent']=True
    await q.edit_message_text('🚨 Срочное сообщение\n\nИспользуй этот режим только для действительно срочного вопроса. Напиши сообщение — я сразу передам его преподавателю.')
    return WAIT_MESSAGE

async def reply_start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    user=database.get_user_by_telegram_id(q.from_user.id)
    if not user:
        await q.edit_message_text('Сначала нажми /start и зарегистрируйся — тогда я смогу открыть диалог 💜'); return ConversationHandler.END
    context.user_data['student_message_uid']=user['id']
    await q.edit_message_text('↩️ Ответ преподавателю\n\nНапиши ответ следующим сообщением — я передам его 💜',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data='student_message_cancel')]]))
    return WAIT_MESSAGE


async def collect(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user=_student(update); text=(update.message.text or '').strip()
    if not user or not text:
        await update.message.reply_text('Напиши сообщение текстом, пожалуйста 💜'); return WAIT_MESSAGE

    urgent=bool(context.user_data.pop('student_message_urgent',False))
    accepting,deliver_at=crm_service.inbound_delivery_state()
    if urgent and crm_service.get_setting('urgent_during_lesson','0')=='1': accepting=True
    status='OPEN' if accepting else 'QUEUED'
    iid=messaging.create_inbox(text,update.effective_user.id,student_id=user['id'],subject='Срочное сообщение от ученика' if urgent else 'Сообщение от ученика',status=status)
    mid=crm_service.log_message(user['id'],'IN',text,None,'TEACHER','DELIVERED' if accepting else 'QUEUED',None if accepting else deliver_at.isoformat(timespec='seconds'),inbox_id=iid)

    if accepting:
        event_center.push('TEACHER_INBOX',f"Сообщение от {user['name']}",text[:500],priority='ACTION',entity_type='teacher_inbox',entity_id=iid,dedupe_key=f'inbox:{iid}')
        await crm_messenger.notify_admins(context,user['id'],text,crm_service.now().isoformat(timespec='seconds'),iid,delayed=False)
        await update.message.reply_text('✅ Готово, я отправила сообщение преподавателю. 💜',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('💬 Открыть диалог',callback_data='student_chat')]]))
    else:
        sent_at=crm_service.now().strftime('%d.%m.%Y %H:%M')
        await update.message.reply_text(
            f"🌙 Я сохранила сообщение.\n\nСейчас преподаватель не принимает сообщения.\n"
            f"Оно будет доставлено в ближайшие часы приёма.\n\nНаписано вами: {sent_at}\n"
            f"Плановая доставка: {deliver_at.strftime('%d.%m.%Y %H:%M')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('💬 Открыть диалог',callback_data='student_chat')]])
        )
    return ConversationHandler.END


async def more_menu(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text('⚙️ Ещё возможности\n\nЗдесь я собрала дополнительные функции. Выбери нужную 👇',reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton('🧪 Пробники',callback_data='ff_my_mocks'),InlineKeyboardButton('📊 Статистика',callback_data='my_stats')],
        [InlineKeyboardButton('📚 Формулы',callback_data='formulas'),InlineKeyboardButton('💳 Оплата',callback_data='payments')],
        [InlineKeyboardButton('🎟 Абонемент',callback_data='payment_subscription'),InlineKeyboardButton('👤 Профиль',callback_data='profile')],
        [InlineKeyboardButton('👨‍🏫 Контакты',callback_data='teacher_contact')],
        [InlineKeyboardButton('⬅️ Главное меню',callback_data='global_home')],
    ]))


async def show_board(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    user=database.get_user_by_telegram_id(q.from_user.id)
    if not user:
        await q.edit_message_text('Сначала нажми /start и зарегистрируйся — тогда я смогу открыть доску 💜'); return ConversationHandler.END
    url=(user['board_url'] if 'board_url' in user.keys() else None)
    if not url:
        await q.edit_message_text('💜 Ссылка на доску пока не добавлена. Когда преподаватель её сохранит, она появится здесь.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return ConversationHandler.END
    await q.edit_message_text('🖥 ДОСКА\n\n💜 Всё готово — можно открывать рабочую доску.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🖥 Открыть доску',url=url)],[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return ConversationHandler.END


async def cancel(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); await q.edit_message_text('Хорошо, отправку сообщения отменила 💜',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('💬 Диалог',callback_data='student_chat')],[InlineKeyboardButton('⬅️ Главное меню',callback_data='global_home')]])); return ConversationHandler.END


def handler():
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start,pattern=r'^student_message_start$'),
            CallbackQueryHandler(reply_start,pattern=r'^student_reply\|'),
            CallbackQueryHandler(urgent_start,pattern=r'^student_message_urgent$'),
        ],
        states={WAIT_MESSAGE:[MessageHandler(filters.TEXT & ~filters.COMMAND,collect),CallbackQueryHandler(cancel,pattern=r'^student_message_cancel$')]},
        fallbacks=[],allow_reentry=True,
    )


def extra_handlers():
    return [
        CallbackQueryHandler(show_chat,pattern=r'^student_chat$'),
        CallbackQueryHandler(more_menu,pattern=r'^student_more_menu$'),
        CallbackQueryHandler(show_board,pattern=r'^student_board$'),
    ]
