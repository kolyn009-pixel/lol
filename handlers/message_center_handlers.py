from __future__ import annotations

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from core import admin_roles
from crm_plus import service, messenger
from ai_assistant import client as adelia_ai
from ai_assistant import context as ai_context

WAIT_ADMIN_REPLY=9821
WAIT_RECEPTION_TIME=9822
WAIT_AI_INSTRUCTION=9823
WAIT_AI_PREVIEW=9824


def _admin(uid): return admin_roles.is_admin_id(uid)


def _fmt(value):
    try:return datetime.fromisoformat(str(value)).strftime('%d.%m %H:%M')
    except Exception:return str(value or '—')


async def _edit(q,text,kb=None):
    try: await q.edit_message_text(text[:3900],reply_markup=kb)
    except Exception as e:
        if 'Message is not modified' not in str(e): raise


async def show_main(q,context=None):
    c=service.message_counts()
    text=(
        '💬 СООБЩЕНИЯ\n\n'
        f"🔴 Непрочитанные: {c['unread']}\n"
        f"🌙 Ожидают часов приёма: {c['queued']}\n"
        f"💬 Диалогов: {c['dialogs']}"
    )
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔴 Новые ({c['unread']})",callback_data='msg_new'),InlineKeyboardButton('💬 Все диалоги',callback_data='msg_dialogs')],
        [InlineKeyboardButton('⚙️ Настройки сообщений',callback_data='msg_settings')],
        [InlineKeyboardButton('⬅️ Админка',callback_data='admin_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='global_home')],
    ])
    await _edit(q,text,kb)


async def _dialogs(q,only_unread=False):
    rows=service.dialog_students(100)
    if only_unread: rows=[r for r in rows if int(r['unread'] or 0)>0]
    if not rows:
        await _edit(q,'💬 СООБЩЕНИЯ\n\nНовых сообщений нет.' if only_unread else '💬 ДИАЛОГИ\n\nПереписка пока пуста.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Сообщения',callback_data='msg_home')]])); return
    kb=[]
    for r in rows[:30]:
        badge=f" • {int(r['unread'])}" if int(r['unread'] or 0)>0 else ''
        kb.append([InlineKeyboardButton(f"💬 {r['name']}{badge}",callback_data=f"msg_dialog|{r['id']}")])
    kb.append([InlineKeyboardButton('⬅️ Сообщения',callback_data='msg_home')])
    await _edit(q,'🔴 НОВЫЕ СООБЩЕНИЯ' if only_unread else '💬 ВСЕ ДИАЛОГИ',InlineKeyboardMarkup(kb))


async def _dialog(q,uid):
    uid=int(uid); user=database.get_user(uid); service.mark_dialog_read(uid)
    rows=service.message_history(uid,30)
    lines=[f"💬 ДИАЛОГ · {user['name'] if user else uid}",'']
    if rows:
        for r in reversed(rows):
            who='Вы' if r['direction']=='OUT' else (user['name'] if user else 'Ученик')
            status=''
            if r['status']=='QUEUED': status=' · ожидает доставки'
            lines.append(f"{_fmt(r['created_at'])} · {who}{status}\n{r['body']}")
    else: lines.append('История пока пуста.')
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton('↩️ Ответить',callback_data=f'msg_reply|{uid}'),InlineKeyboardButton('💜 Помощь Аделии',callback_data=f'msg_ai|{uid}')],
        [InlineKeyboardButton('✅ Выполнено',callback_data=f'msg_done|{uid}'),InlineKeyboardButton('🟡 В работу',callback_data=f'msg_work|{uid}')],
        [InlineKeyboardButton('👤 Карточка',callback_data=f'student_view|{uid}')],
        [InlineKeyboardButton('📅 Записать',callback_data=f'admin_manual_for|{uid}'),InlineKeyboardButton('🔄 Перенести',callback_data=f'ff_swap|{uid}')],
        [InlineKeyboardButton('📝 ДЗ',callback_data=f'student_homeworks|{uid}')],
        [InlineKeyboardButton('⬅️ Диалоги',callback_data='msg_dialogs'),InlineKeyboardButton('🏠 Главное меню',callback_data='global_home')],
    ])
    await _edit(q,'\n\n'.join(lines)[-3900:],kb)


async def _settings(q):
    enabled,s,e,days=service.reception_label(); urgent=service.get_setting('urgent_enabled','0')=='1'; dnd=service.get_setting('lesson_dnd_enabled','1')=='1'
    text=(
        '⚙️ НАСТРОЙКИ СООБЩЕНИЙ\n\n'
        f"🕘 Часы приёма: {s}–{e}\n"
        f"📅 Дни: {days}\n"
        f"🌙 Отложенная доставка: {'ВКЛ' if enabled else 'ВЫКЛ'}\n"
        f"🚨 Срочные сообщения: {'ВКЛ' if urgent else 'ВЫКЛ'}\n"
        f"🔕 Не беспокоить во время занятий: {'ВКЛ' if dnd else 'ВЫКЛ'}\n\n"
        'Если ученик пишет вне часов приёма, сообщение сохраняется сразу, но уведомление придёт вам только в ближайшие часы приёма. В уведомлении будет указано фактическое время сообщения.'
    )
    day_names=['Пн','Вт','Ср','Чт','Пт','Сб','Вс']; active={int(x) for x in (service.get_setting('reception_days','0,1,2,3,4,5,6') or '').split(',') if x.strip().isdigit()}
    day_buttons=[InlineKeyboardButton(('✅ ' if i in active else '➕ ')+name,callback_data=f'msg_day|{i}') for i,name in enumerate(day_names)]
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton('🕘 Изменить часы',callback_data='msg_hours'),InlineKeyboardButton('🌙 Вкл/выкл',callback_data='msg_reception_toggle')],
        day_buttons[:4],day_buttons[4:],
        [InlineKeyboardButton('🚨 Срочные вкл/выкл',callback_data='msg_urgent_toggle')],
        [InlineKeyboardButton('🔕 Во время занятий вкл/выкл',callback_data='msg_dnd_toggle')],
        [InlineKeyboardButton('⬅️ Сообщения',callback_data='msg_home'),InlineKeyboardButton('🏠 Главное меню',callback_data='global_home')],
    ])
    await _edit(q,text,kb)


async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q:return
    d=q.data or ''
    if d=='admin_student_messages': d='msg_home'
    if not d.startswith('msg_'):return
    if not _admin(q.from_user.id):await q.answer('Нет доступа',show_alert=True);return ConversationHandler.END
    await q.answer()
    if d=='msg_home': await show_main(q,context); return ConversationHandler.END
    if d=='msg_new': await _dialogs(q,True); return ConversationHandler.END
    if d=='msg_dialogs': await _dialogs(q,False); return ConversationHandler.END
    if d.startswith('msg_dialog|'): await _dialog(q,int(d.split('|')[1])); return ConversationHandler.END
    if d.startswith('msg_done|'):
        uid=int(d.split('|')[1]); service.set_setting(f'dialog_state:{uid}','DONE',q.from_user.id); service.mark_dialog_read(uid); await _dialog(q,uid); return ConversationHandler.END
    if d.startswith('msg_work|'):
        uid=int(d.split('|')[1]); service.set_setting(f'dialog_state:{uid}','WORK',q.from_user.id); await _dialog(q,uid); return ConversationHandler.END
    if d.startswith('msg_read|'):
        uid=int(d.split('|')[1]); service.mark_dialog_read(uid); await _dialog(q,uid); return ConversationHandler.END
    if d.startswith('msg_ai|'):
        uid=int(d.split('|')[1]); u=database.get_user(uid)
        if not adelia_ai.is_enabled():
            await q.edit_message_text('💜 Помощь Аделии пока не подключена.\n\nДобавьте OPENROUTER_API_KEY на сервере — остальные функции бота продолжат работать без ИИ.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Диалог',callback_data=f'msg_dialog|{uid}')]])); return ConversationHandler.END
        context.user_data['msg_ai_uid']=uid
        await q.edit_message_text(
            f"💜 АДЕЛИЯ • ЧЕРНОВИК ДЛЯ {u['name'] if u else uid}\n\n"
            "Напишите мне смысл сообщения обычными словами.\n\n"
            "Например:\n• мягко напомни про оплату\n• ответь, что перенос возможен, но нужно выбрать время\n• похвали за сегодняшний урок\n• скажи покороче и без эмодзи\n\nНичего не отправится без Вашего подтверждения."
        )
        return WAIT_AI_INSTRUCTION
    if d.startswith('msg_reply|'):
        uid=int(d.split('|')[1]); context.user_data['msg_reply_uid']=uid; u=database.get_user(uid)
        await q.edit_message_text(f"↩️ ОТВЕТ · {u['name'] if u else uid}\n\nНапишите сообщение следующим сообщением.")
        return WAIT_ADMIN_REPLY
    if d=='msg_settings': await _settings(q); return ConversationHandler.END
    if d=='msg_hours': await q.edit_message_text('🕘 Введите часы приёма в формате 09:00-21:00'); return WAIT_RECEPTION_TIME
    if d=='msg_reception_toggle':
        cur=service.get_setting('reception_enabled','1');service.set_setting('reception_enabled','0' if cur=='1' else '1',q.from_user.id);await _settings(q);return ConversationHandler.END
    if d=='msg_dnd_toggle':
        cur=service.get_setting('lesson_dnd_enabled','1');service.set_setting('lesson_dnd_enabled','0' if cur=='1' else '1',q.from_user.id);await _settings(q);return ConversationHandler.END
    if d=='msg_urgent_toggle':
        cur=service.get_setting('urgent_enabled','0');service.set_setting('urgent_enabled','0' if cur=='1' else '1',q.from_user.id);await _settings(q);return ConversationHandler.END
    if d.startswith('msg_day|'):
        day=int(d.split('|')[1]); active={int(x) for x in (service.get_setting('reception_days','0,1,2,3,4,5,6') or '').split(',') if x.strip().isdigit()}
        if day in active: active.remove(day)
        else: active.add(day)
        service.set_setting('reception_days',','.join(map(str,sorted(active))),q.from_user.id);await _settings(q);return ConversationHandler.END
    return ConversationHandler.END


async def reply_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=context.user_data.pop('msg_reply_uid',None);text=(update.message.text or '').strip()
    if not uid or not text:return ConversationHandler.END
    result=await messenger.send_teacher_message(context,int(uid),text,update.effective_user.id,'STUDENT')
    if result['status']=='QUEUED':
        await update.message.reply_text(f"🌙 Сообщение поставлено в очередь до {result['send_at'].strftime('%d.%m %H:%M')}.")
    else:
        await update.message.reply_text('✅ Сообщение отправлено ученику.' if result['sent'] else '⚠️ Не удалось доставить сообщение.')
    return ConversationHandler.END


async def ai_instruction(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=context.user_data.get('msg_ai_uid'); instruction=(update.message.text or '').strip()
    if not uid or not instruction: return ConversationHandler.END
    u=database.get_user(int(uid)); name=u['name'] if u else str(uid)
    await update.message.reply_text('💜 Готовлю черновик…')
    try:
        draft=await adelia_ai.draft_message(
            instruction=instruction,recipient_name=name,recipient_type='ученик',
            facts=ai_context.student_facts(int(uid)),recent_messages=ai_context.recent_messages(int(uid)),tone='friendly')
    except Exception:
        await update.message.reply_text('⚠️ Сейчас бесплатная модель не ответила. Сам TutorBot работает нормально — можно написать сообщение вручную или попробовать ещё раз позже.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Диалог',callback_data=f'msg_dialog|{uid}')]])); return ConversationHandler.END
    context.user_data['msg_ai_draft']=draft
    context.user_data['msg_ai_instruction']=instruction
    await update.message.reply_text(
        f"💜 АДЕЛИЯ • ЧЕРНОВИК\n\n{draft}\n\nНичего ещё не отправлено.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('📨 Отправить',callback_data='msg_ai_send')],
            [InlineKeyboardButton('✏️ Переделать',callback_data='msg_ai_rewrite'),InlineKeyboardButton('❌ Отмена',callback_data='msg_ai_cancel')],
        ]))
    return WAIT_AI_PREVIEW


async def ai_preview_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); d=q.data or ''; uid=context.user_data.get('msg_ai_uid')
    if not uid: return ConversationHandler.END
    if d=='msg_ai_cancel':
        context.user_data.pop('msg_ai_draft',None);context.user_data.pop('msg_ai_uid',None)
        await _dialog(q,int(uid)); return ConversationHandler.END
    if d=='msg_ai_rewrite':
        await q.edit_message_text('💜 Напишите, как изменить черновик. Например: «короче», «мягче», «официальнее», или полностью опишите новый смысл.')
        return WAIT_AI_INSTRUCTION
    if d=='msg_ai_send':
        draft=context.user_data.get('msg_ai_draft')
        if not draft:
            await q.edit_message_text('Черновик устарел. Подготовьте сообщение заново.'); return ConversationHandler.END
        result=await messenger.send_teacher_message(context,int(uid),draft,q.from_user.id,'STUDENT')
        context.user_data.pop('msg_ai_draft',None);context.user_data.pop('msg_ai_uid',None)
        text='🌙 Сообщение поставлено в очередь до часов приёма.' if result.get('status')=='QUEUED' else ('✅ Я отправила сообщение ученику.' if result.get('sent') else '⚠️ Не удалось доставить сообщение.')
        await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('💬 Открыть диалог',callback_data=f'msg_dialog|{uid}')]])); return ConversationHandler.END
    return WAIT_AI_PREVIEW


async def reception_time(update:Update,context:ContextTypes.DEFAULT_TYPE):
    txt=(update.message.text or '').strip()
    try:
        s,e=[x.strip() for x in txt.split('-',1)];datetime.strptime(s,'%H:%M');datetime.strptime(e,'%H:%M')
    except Exception:
        await update.message.reply_text('❌ Формат: 09:00-21:00');return WAIT_RECEPTION_TIME
    service.set_setting('reception_start',s,update.effective_user.id);service.set_setting('reception_end',e,update.effective_user.id)
    await update.message.reply_text(f'✅ Часы приёма сообщений: {s}–{e}')
    return ConversationHandler.END


def handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(callbacks,pattern=r'^(msg_|admin_student_messages$)')],
        states={
            WAIT_ADMIN_REPLY:[MessageHandler(filters.TEXT & ~filters.COMMAND,reply_text)],
            WAIT_RECEPTION_TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND,reception_time)],
            WAIT_AI_INSTRUCTION:[MessageHandler(filters.TEXT & ~filters.COMMAND,ai_instruction)],
            WAIT_AI_PREVIEW:[CallbackQueryHandler(ai_preview_callback,pattern=r'^msg_ai_(send|rewrite|cancel)$')],
        },fallbacks=[],allow_reentry=True,
    )
