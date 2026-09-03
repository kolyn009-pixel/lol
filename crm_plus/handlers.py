from __future__ import annotations
from datetime import datetime,timedelta
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import CallbackQueryHandler,ConversationHandler,MessageHandler,ContextTypes,filters
import database
from core import admin_roles
from automation import messaging, student_history
from . import schema,service,messenger

WAIT_TEXT=9701
WAIT_NOTE=9702
WAIT_AGREEMENT=9703
WAIT_PAUSE_DATE=9704
WAIT_SEARCH=9705
WAIT_QUIET=9706
WAIT_BROADCAST=9707
WAIT_BROADCAST_CONFIRM=9708

def _admin(uid): return admin_roles.is_admin_id(uid)

def _student(uid):return database.get_user(int(uid))

def _card_kb(uid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💬 Написать ученику',callback_data=f'crm_write|{uid}'),InlineKeyboardButton('📜 Переписка',callback_data=f'crm_history|{uid}')],
        [InlineKeyboardButton('📌 Закреплённая заметка',callback_data=f'crm_note|{uid}'),InlineKeyboardButton('🧷 Договорённости',callback_data=f'crm_agreements|{uid}')],
        [InlineKeyboardButton('⚠️ Следующее действие',callback_data=f'crm_attention|{uid}'),InlineKeyboardButton('💳 Предложить оплату',callback_data=f'crm_bill|{uid}')],
        [InlineKeyboardButton('📅 Следующее занятие',callback_data=f'admin_manual_for|{uid}'),InlineKeyboardButton('🏖 Пауза',callback_data=f'crm_pause|{uid}')],
        [InlineKeyboardButton('📊 Отчёт родителю',callback_data=f'crm_report|{uid}'),InlineKeyboardButton('📝 Итог урока',callback_data=f'crm_review_latest|{uid}')],
        [InlineKeyboardButton('📜 История ученика',callback_data=f'mh_history|{uid}')],
        [InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'student_view|{uid}')],
    ])

async def _edit(q,text,kb=None):
    try:await q.edit_message_text(text[:3900],reply_markup=kb)
    except Exception as e:
        if 'Message is not modified' not in str(e):raise

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('crm_'):return
    if not _admin(q.from_user.id):await q.answer('Нет доступа',show_alert=True);return
    await q.answer(); d=q.data; schema.initialize()
    if d=='crm_today':
        x=service.today_dashboard(); lines=['🌅 ЧТО ВАЖНО СЕГОДНЯ','']
        if x['lessons']:
            lines+=['📅 Занятия:']+[f"• {str(r['start_time'])[11:16]} — {r['name']} ({int(r['duration_minutes'] or 60)} мин)" for r in x['lessons']]
        lines+=['',f"💬 Сообщений ждут ответа: {x['open_messages']}",f"💳 Неоплаченных: {x['unpaid']}",f"⚠️ Требуют внимания: {len(x['attention'])}"]
        kb=[[InlineKeyboardButton(name,callback_data=f'crm_attention|{sid}')] for sid,name,_ in x['attention'][:12]]+[[InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')]]
        await _edit(q,'\n'.join(lines),InlineKeyboardMarkup(kb));return
    if d=='crm_search':
        context.user_data['crm_mode']='search'; await q.edit_message_text('🔎 Введите имя, Telegram, телефон или часть заметки ученика:'); return WAIT_SEARCH
    if d=='crm_broadcast':
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton('👥 Всем ученикам',callback_data='crm_bseg|ALL')],
            [InlineKeyboardButton('🎓 ЕГЭ',callback_data='crm_bseg|EGE'),InlineKeyboardButton('🎯 ОГЭ',callback_data='crm_bseg|OGE')],
            [InlineKeyboardButton('⚛️ Физика',callback_data='crm_bseg|PHYSICS'),InlineKeyboardButton('🧪 Химия',callback_data='crm_bseg|CHEMISTRY')],
            [InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')],
        ])
        await _edit(q,'📣 АДРЕСНАЯ РАССЫЛКА\n\nВыберите группу:',kb);return
    if d.startswith('crm_bseg|'):
        seg=d.split('|',1)[1];context.user_data['crm_bseg']=seg;context.user_data['crm_mode']='broadcast';await q.edit_message_text('✍️ Напишите сообщение для выбранной группы:');return WAIT_BROADCAST
    if d=='crm_quiet':
        enabled=service.get_setting('quiet_enabled','1'); s=service.get_setting('quiet_start','22:00');e=service.get_setting('quiet_end','09:00')
        await _edit(q,f"🔕 ТИХИЕ ЧАСЫ\n\nСейчас: {'включены' if enabled=='1' else 'выключены'}\n{s} — {e}\n\nОтправьте новое окно в формате 22:00-09:00 или нажмите переключатель.",InlineKeyboardMarkup([[InlineKeyboardButton('🔁 Вкл/выкл',callback_data='crm_quiet_toggle')],[InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')]])); context.user_data['crm_mode']='quiet'; return WAIT_QUIET
    if d=='crm_quiet_toggle':
        service.set_setting('quiet_enabled','0' if service.get_setting('quiet_enabled','1')=='1' else '1',q.from_user.id); await q.answer('Готово',show_alert=True);return
    if d.startswith('crm_student|'):
        uid=int(d.split('|')[1]); u=_student(uid); note=service.get_pinned_note(uid); rs=service.attention_reasons(uid); ag=service.agreements(uid,3)
        text=f"🧭 УМНАЯ КАРТОЧКА\n\n👤 {u['name'] if u else uid}\n"
        if note:text+=f"\n📌 {note}\n"
        if rs:text+='\n⚠️ '+ '\n⚠️ '.join(rs)+'\n'
        if ag:text+='\n🧷 Договорённости:\n'+'\n'.join('• '+r['text'] for r in ag)
        await _edit(q,text,_card_kb(uid));return
    if d.startswith('crm_write|'):
        uid=int(d.split('|')[1]);context.user_data['crm_student_id']=uid;context.user_data['crm_target']='STUDENT';context.user_data['crm_mode']='write'
        await _edit(q,'💬 Кому отправить сообщение?',InlineKeyboardMarkup([[InlineKeyboardButton('👤 Ученику',callback_data=f'crm_target_student|{uid}'),InlineKeyboardButton('👨‍👩‍👧 Родителям',callback_data=f'crm_target_parents|{uid}')],[InlineKeyboardButton('👥 Всем',callback_data=f'crm_target_all|{uid}')],[InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')]]));return WAIT_TEXT
    if d.startswith('crm_target_'):
        parts=d.split('|');uid=int(parts[1]);target='STUDENT' if 'student' in parts[0] else ('PARENTS' if 'parents' in parts[0] else 'ALL');context.user_data.update(crm_student_id=uid,crm_target=target,crm_mode='write');await q.edit_message_text('✍️ Напишите сообщение.\n\nЕсли сейчас тихие часы, бот предложит отправить утром или срочно.');return WAIT_TEXT
    if d.startswith('crm_history|'):
        uid=int(d.split('|')[1]); rows=service.message_history(uid,30); text='📜 ПЕРЕПИСКА ЧЕРЕЗ БОТА\n\n'+('\n\n'.join(f"{r['created_at'][5:16]} • {'➡️' if r['direction']=='OUT' else '⬅️'} {r['target']}\n{r['body']}" for r in rows) if rows else 'История пока пуста.'); await _edit(q,text,_card_kb(uid));return
    if d.startswith('crm_note|'):
        uid=int(d.split('|')[1]);context.user_data.update(crm_student_id=uid,crm_mode='note'); cur=service.get_pinned_note(uid) or '—'; await q.edit_message_text(f'📌 Текущая заметка:\n{cur}\n\nОтправьте новый текст:');return WAIT_NOTE
    if d.startswith('crm_agreements|'):
        uid=int(d.split('|')[1]);rows=service.agreements(uid);text='🧷 ДОГОВОРЁННОСТИ\n\n'+('\n'.join(f"• {r['text']}"+(f" (до {r['valid_until']})" if r['valid_until'] else '') for r in rows) if rows else 'Нет активных договорённостей.');kb=InlineKeyboardMarkup([[InlineKeyboardButton('➕ Добавить',callback_data=f'crm_agreement_add|{uid}')],[InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')]]);await _edit(q,text,kb);return
    if d.startswith('crm_agreement_add|'):
        uid=int(d.split('|')[1]);context.user_data.update(crm_student_id=uid,crm_mode='agreement');await q.edit_message_text('🧷 Напишите договорённость.\nМожно добавить срок после символа |\n\nПример: Заниматься по 120 минут | 2026-12-31');return WAIT_AGREEMENT
    if d.startswith('crm_attention|'):
        uid=int(d.split('|')[1]);u=_student(uid);rs=service.attention_reasons(uid);text=f"⚠️ СЛЕДУЮЩЕЕ ДЕЙСТВИЕ\n\n{u['name'] if u else uid}\n\n"+('\n'.join('• '+x for x in rs) if rs else '✅ Ничего срочного.');await _edit(q,text,_card_kb(uid));return
    if d.startswith('crm_pause|'):
        uid=int(d.split('|')[1]);context.user_data.update(crm_student_id=uid,crm_mode='pause');await q.edit_message_text('🏖 До какой даты поставить ученика на паузу?\nВведите ДД.ММ.ГГГГ');return WAIT_PAUSE_DATE
    if d.startswith('crm_review_latest|'):
        uid=int(d.split('|')[1]);c=database.connect();r=c.execute("SELECT id FROM lessons WHERE user_id=? AND finished_at IS NOT NULL AND cancelled_at IS NULL ORDER BY datetime(finished_at) DESC LIMIT 1",(uid,)).fetchone();c.close()
        if not r:await q.answer('Нет завершённых занятий.',show_alert=True);return
        await _edit(q,'📝 Быстрый итог последнего занятия',InlineKeyboardMarkup([[InlineKeyboardButton('🧠 Отметить темы и уровень',callback_data=f"ff_review_start|{r['id']}|{uid}")],[InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')]]));return
    if d.startswith('crm_report|'):
        uid=int(d.split('|')[1]);text=service.quick_month_report(uid);kb=InlineKeyboardMarkup([[InlineKeyboardButton('📨 Отправить родителям',callback_data=f'crm_report_send|{uid}')],[InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')]]);context.user_data['crm_report_text']=text;await _edit(q,text,kb);return
    if d.startswith('crm_report_send|'):
        uid=int(d.split('|')[1]);text=context.user_data.get('crm_report_text') or service.quick_month_report(uid);ok=0
        for tid in service.parent_ids(uid):
            try:await context.bot.send_message(tid,text);ok+=1
            except Exception:pass
        await q.answer(f'Отправлено родителям: {ok}',show_alert=True);return
    if d=='crm_broadcast_send':
        payload=context.user_data.pop('crm_broadcast_payload',None)
        if not payload:await q.answer('Рассылка устарела.',show_alert=True);return
        text,tids,seg=payload;quiet,send_at=service.quiet_state();ok=0
        if quiet:
            for tid in tids:messaging.schedule(q.from_user.id,text,send_at.isoformat(timespec='seconds'),'TELEGRAM',int(tid))
            await q.edit_message_text(f'🔕 Тихие часы. В очередь поставлено: {len(tids)}. Отправка с {send_at:%d.%m %H:%M}.');return
        for tid in tids:
            try:await context.bot.send_message(int(tid),text);ok+=1
            except Exception:pass
        await q.edit_message_text(f'✅ Рассылка завершена: {ok}/{len(tids)}');return
    if d=='crm_broadcast_cancel':
        context.user_data.pop('crm_broadcast_payload',None);await q.edit_message_text('Рассылка отменена.');return
    if d.startswith('crm_bill|'):
        uid=int(d.split('|')[1]);progs=database.get_student_programs(uid,active_only=True,approved_only=True);kb=[[InlineKeyboardButton(service.program_label(p),callback_data=f"crm_bill_prog|{uid}|{p['id']}")] for p in progs]+[[InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')]];await _edit(q,'💳 Выберите направление для предложения оплаты:',InlineKeyboardMarkup(kb));return
    if d.startswith('crm_bill_methods|'):
        _,_,oid,uid=d.split('|');oid=int(oid);uid=int(uid)
        c=database.connect();r=c.execute('SELECT * FROM billing_offers WHERE id=?',(oid,)).fetchone();c.close()
        if not r:
            await q.answer('Предложение не найдено.',show_alert=True);return
        methods=service.active_payment_methods()
        text=(f"💳 ПРЕДЛОЖЕНИЕ ОПЛАТЫ\n\n{r['minutes']} минут\nСкидка: {r['discount_percent']}%\nИтого: {r['amount']} ₽\n\n"
              "Выберите, какие реквизиты отправить ученику:")
        kb=[[InlineKeyboardButton(('⭐ ' if m['is_default'] else '💳 ')+m['title'],callback_data=f"crm_bill_method|{oid}|{uid}|{m['id']}")] for m in methods]
        if not methods: kb.append([InlineKeyboardButton('➕ Добавить способ оплаты',callback_data='admin_payment_methods')])
        kb.append([InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'crm_student|{uid}')])
        await _edit(q,text,InlineKeyboardMarkup(kb));return
    if d.startswith('crm_bill_prog|'):
        _,_,uid,pid=d.split('|');uid=int(uid);qte=service.billing_quote(uid,int(pid),10); oid=service.save_billing_offer(uid,int(pid),qte,q.from_user.id)
        methods=service.active_payment_methods()
        text=(f"💳 ПРЕДЛОЖЕНИЕ ОПЛАТЫ\n\n{qte['equivalent_lessons']} занятий • {qte['minutes']} мин\n"
              f"Скидка: {qte.get('discount_percent',0)}%\nИтого: {qte['total']} ₽\n\n"
              "Я подготовила сумму. Теперь выберите, какие реквизиты отправить ученику:")
        kb=[[InlineKeyboardButton(('⭐ ' if m['is_default'] else '💳 ')+m['title'],callback_data=f"crm_bill_method|{oid}|{uid}|{m['id']}")] for m in methods]
        if not methods:
            text += "\n\nСейчас нет активных способов оплаты. Сначала добавьте реквизиты в админке."
            kb.append([InlineKeyboardButton('➕ Добавить способ оплаты',callback_data='admin_payment_methods')])
        kb.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'crm_student|{uid}')])
        await _edit(q,text,InlineKeyboardMarkup(kb));return
    if d.startswith('crm_bill_method|'):
        _,_,oid,uid,mid=d.split('|');oid=int(oid);uid=int(uid);mid=int(mid)
        method=service.choose_billing_payment_method(oid,mid)
        if not method:
            await q.answer('Этот способ оплаты сейчас недоступен.',show_alert=True);return
        c=database.connect();r=c.execute('SELECT * FROM billing_offers WHERE id=?',(oid,)).fetchone();c.close()
        preview=(f"💳 ПРЕДЛОЖЕНИЕ ОПЛАТЫ\n\n{r['minutes']} минут\nСкидка: {r['discount_percent']}%\nИтого: {r['amount']} ₽\n\n"
                 f"Выбран способ: {method['title']}\n\n{service.payment_method_message(method)}")
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton('📨 Отправить ученику',callback_data=f'crm_bill_send|{oid}|{uid}')],
            [InlineKeyboardButton('🔄 Выбрать другие реквизиты',callback_data=f'crm_bill_methods|{oid}|{uid}')],
            [InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'crm_student|{uid}')],
        ])
        await _edit(q,preview,kb);return
    if d.startswith('crm_bill_send|'):
        _,_,oid,uid=d.split('|');uid=int(uid);u=_student(uid);c=database.connect();r=c.execute('SELECT * FROM billing_offers WHERE id=?',(int(oid),)).fetchone();c.close()
        method=service.billing_payment_method(r) if r else None
        if not r or not method:
            await q.answer('Не удалось найти предложение или реквизиты.',show_alert=True);return
        text=(f"💳 Предложение пополнить баланс\n\n{r['minutes']} минут\nСкидка: {r['discount_percent']}%\nИтого: {r['amount']} ₽\n\n"
              f"{service.payment_method_message(method)}")
        ok=0
        if u and u['telegram_id']:
            try:await context.bot.send_message(int(u['telegram_id']),text);ok+=1
            except Exception:pass
        for tid in service.parent_ids(uid):
            try:await context.bot.send_message(tid,text);ok+=1
            except Exception:pass
        c=database.connect();c.execute("UPDATE billing_offers SET status='SENT',sent_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),int(oid)));c.commit();c.close();await q.answer(f'Готово 💜 Я отправила предложение: {ok}.',show_alert=True);return

async def text_state(update:Update,context:ContextTypes.DEFAULT_TYPE):
    mode=context.user_data.get('crm_mode'); txt=update.message.text.strip();uid=context.user_data.get('crm_student_id')
    if mode=='write':
        target=context.user_data.get('crm_target','STUDENT')
        result=await messenger.send_teacher_message(context,int(uid),txt,update.effective_user.id,target)
        student_history.add(uid,'MESSAGE','Сообщение преподавателя',txt,'crm_message',None)
        if result['status']=='QUEUED':
            await update.message.reply_text(f"🔕 Сообщение поставлено в очередь до {result['send_at'].strftime('%d.%m %H:%M')}.")
        else:
            await update.message.reply_text(f"✅ Отправлено: {result['sent']}")
        return ConversationHandler.END
    if mode=='note':service.set_pinned_note(uid,txt,update.effective_user.id);await update.message.reply_text('✅ Закреплённая заметка сохранена.');return ConversationHandler.END
    if mode=='agreement':
        parts=[x.strip() for x in txt.split('|',1)];valid=parts[1] if len(parts)>1 and parts[1] else None;service.add_agreement(uid,parts[0],valid,update.effective_user.id);student_history.add(uid,'AGREEMENT','Договорённость',parts[0]);await update.message.reply_text('✅ Договорённость сохранена.');return ConversationHandler.END
    if mode=='pause':
        try:d=datetime.strptime(txt,'%d.%m.%Y').date().isoformat();rid=service.pause_student(uid,d,'Пауза ученика',update.effective_user.id);await update.message.reply_text(f'✅ Пауза создана до {txt}.');return ConversationHandler.END
        except Exception as e:await update.message.reply_text(f'❌ {e}\nВведите дату ДД.ММ.ГГГГ');return WAIT_PAUSE_DATE
    if mode=='search':
        c=database.connect();like=f"%{txt}%";rows=c.execute("SELECT DISTINCT u.id,u.name,u.telegram_username,u.phone FROM users u LEFT JOIN student_pinned_notes n ON n.student_id=u.id WHERE u.name LIKE ? OR COALESCE(u.telegram_username,'') LIKE ? OR COALESCE(u.phone,'') LIKE ? OR COALESCE(n.note,'') LIKE ? ORDER BY u.name LIMIT 20",(like,like,like,like)).fetchall();c.close();kb=[[InlineKeyboardButton(r['name'],callback_data=f"crm_student|{r['id']}")] for r in rows]+[[InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')]];await update.message.reply_text('🔎 Результаты:' if rows else 'Ничего не найдено.',reply_markup=InlineKeyboardMarkup(kb));return ConversationHandler.END
    if mode=='quiet':
        try:s,e=[x.strip() for x in txt.split('-',1)];datetime.strptime(s,'%H:%M');datetime.strptime(e,'%H:%M');service.set_setting('quiet_start',s,update.effective_user.id);service.set_setting('quiet_end',e,update.effective_user.id);await update.message.reply_text(f'✅ Тихие часы: {s}–{e}');return ConversationHandler.END
        except Exception:await update.message.reply_text('❌ Формат: 22:00-09:00');return WAIT_QUIET
    if mode=='broadcast':
        seg=context.user_data.get('crm_bseg','ALL');c=database.connect()
        if seg=='ALL':rows=c.execute('SELECT telegram_id FROM users WHERE active=1 AND telegram_id IS NOT NULL').fetchall()
        elif seg in ('EGE','OGE'):rows=c.execute('SELECT DISTINCT u.telegram_id FROM users u JOIN student_programs p ON p.user_id=u.id WHERE u.active=1 AND u.telegram_id IS NOT NULL AND p.active=1 AND p.study_goal=?',(seg,)).fetchall()
        else:rows=c.execute('SELECT DISTINCT u.telegram_id FROM users u JOIN student_programs p ON p.user_id=u.id WHERE u.active=1 AND u.telegram_id IS NOT NULL AND p.active=1 AND p.subject=?',(seg,)).fetchall()
        c.close();tids=[int(r['telegram_id']) for r in rows if r['telegram_id']];context.user_data['crm_broadcast_payload']=(txt,tids,seg)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ Отправить ({len(tids)})',callback_data='crm_broadcast_send')],[InlineKeyboardButton('❌ Отмена',callback_data='crm_broadcast_cancel')]])
        await update.message.reply_text(f'⚠️ Подтвердите рассылку для {len(tids)} получателей:\n\n{txt[:2500]}',reply_markup=kb);return WAIT_BROADCAST_CONFIRM
    return ConversationHandler.END

def handler():
    return ConversationHandler(entry_points=[CallbackQueryHandler(callbacks,pattern=r'^crm_')],states={WAIT_TEXT:[CallbackQueryHandler(callbacks,pattern=r'^crm_'),MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_NOTE:[MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_AGREEMENT:[MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_PAUSE_DATE:[MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_SEARCH:[MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_QUIET:[CallbackQueryHandler(callbacks,pattern=r'^crm_'),MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_BROADCAST:[MessageHandler(filters.TEXT & ~filters.COMMAND,text_state)],WAIT_BROADCAST_CONFIRM:[CallbackQueryHandler(callbacks,pattern=r'^crm_broadcast_')]},fallbacks=[],allow_reentry=True)
