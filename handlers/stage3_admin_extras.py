from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes
import database
from core import admin_roles, audit_log
from automation import admin_tools, monthly_reports, notifications

async def tag_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if len(context.args)<2 or not context.args[0].isdigit():
        await update.message.reply_text('Использование: /tag STUDENT_ID тег'); return
    sid=int(context.args[0]); tag=' '.join(context.args[1:]); admin_tools.add_tag(sid,tag)
    audit_log.log('ADD_TAG',update.effective_user.id,'student',sid,{'tag':tag})
    await update.message.reply_text('✅ Тег добавлен.')

async def template_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    raw=' '.join(context.args)
    if '|' not in raw:
        await update.message.reply_text('Использование: /template Название | текст'); return
    name,text=[x.strip() for x in raw.split('|',1)]
    admin_tools.save_template(name,text,update.effective_user.id)
    await update.message.reply_text('✅ Шаблон сохранён.')

async def templates_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    rows=admin_tools.templates()
    text='📝 ШАБЛОНЫ\n\n'+('\n\n'.join(f"• {r['name']}\n{r['text']}" for r in rows) if rows else 'Пока нет шаблонов.')
    await update.message.reply_text(text[:3900])

async def period_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if len(context.args)<3:
        await update.message.reply_text('Использование: /period Название YYYY-MM-DD YYYY-MM-DD'); return
    name=' '.join(context.args[:-2]); rid=admin_tools.add_period(name,context.args[-2],context.args[-1])
    await update.message.reply_text(f'✅ Учебный период #{rid} создан.')

async def monthlyreport_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text('Использование: /monthlyreport STUDENT_ID [YYYY-MM]'); return
    sid=int(context.args[0]); month=context.args[1] if len(context.args)>1 else None
    text=monthly_reports.build(sid,month); m,_,_=monthly_reports.bounds(month)
    rid=monthly_reports.save_draft(sid,text,m,update.effective_user.id)
    context.user_data[f'monthly_report_{rid}']=text
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Отправить родителям',callback_data=f's3x_monthly_send|{rid}|{sid}')],[InlineKeyboardButton('❌ Оставить черновиком',callback_data='s3x_cancel')]])
    await update.message.reply_text(text,parse_mode='HTML',reply_markup=kb)

async def broadcastto_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    raw=' '.join(context.args)
    if '|' not in raw:
        await update.message.reply_text('Использование: /broadcastto all|grade:10|subject:PHYSICS | текст'); return
    selector,text=[x.strip() for x in raw.split('|',1)]
    conn=database.connect(); ids=[]
    if selector=='all':
        ids=[r['telegram_id'] for r in conn.execute('SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL').fetchall()]
    elif selector.startswith('grade:'):
        grade=selector.split(':',1)[1]
        ids=[r['telegram_id'] for r in conn.execute('SELECT telegram_id FROM users WHERE grade=? AND telegram_id IS NOT NULL',(grade,)).fetchall()]
    elif selector.startswith('subject:'):
        subject=selector.split(':',1)[1]
        ids=[r['telegram_id'] for r in conn.execute('''SELECT DISTINCT u.telegram_id FROM users u JOIN student_programs sp ON sp.user_id=u.id WHERE sp.subject=? AND sp.active=1 AND u.telegram_id IS NOT NULL''',(subject,)).fetchall()]
    conn.close(); ids=list(dict.fromkeys(ids))
    context.user_data['s3x_broadcast']=(selector,text,ids)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ Отправить ({len(ids)})',callback_data='s3x_broadcast_confirm')],[InlineKeyboardButton('❌ Отмена',callback_data='s3x_cancel')]])
    await update.message.reply_text(f'Сегмент: {selector}\nПолучателей: {len(ids)}\n\n{text[:2500]}',reply_markup=kb)

async def callbacks(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); data=q.data
    if not admin_roles.is_admin_id(q.from_user.id): return
    if data=='s3x_cancel': await q.edit_message_text('Оставлено без отправки.'); return
    if data=='s3x_broadcast_confirm':
        payload=context.user_data.pop('s3x_broadcast',None)
        if not payload: await q.edit_message_text('Черновик уже недоступен.'); return
        selector,text,ids=payload; ok=0
        for tid in ids:
            try: await context.bot.send_message(tid,text); ok+=1
            except Exception: pass
        audit_log.log('SEGMENT_BROADCAST',q.from_user.id,details={'selector':selector,'sent':ok,'total':len(ids)})
        await q.edit_message_text(f'✅ Отправлено: {ok}/{len(ids)}'); return
    if data.startswith('s3x_monthly_send|'):
        _,rid,sid=data.split('|'); rid=int(rid); sid=int(sid)
        text=context.user_data.pop(f'monthly_report_{rid}',None) or monthly_reports.build(sid)
        sent=0
        for parent in database.get_student_parents(sid):
            try:
                prefs=notifications.get(parent['id'],sid)
                if not prefs.get('monthly_report',1): continue
                if not parent['telegram_id']: continue
                await context.bot.send_message(parent['telegram_id'],text,parse_mode='HTML'); sent+=1
            except Exception: pass
        conn=database.connect(); conn.execute("UPDATE monthly_reports_log SET status='SENT',sent_at=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),rid)); conn.commit(); conn.close()
        await q.edit_message_text(f'✅ Отчёт отправлен родителям: {sent}.')

def handlers():
    return [CommandHandler('tag',tag_cmd),CommandHandler('template',template_cmd),CommandHandler('templates',templates_cmd),CommandHandler('period',period_cmd),CommandHandler('monthlyreport',monthlyreport_cmd),CommandHandler('broadcastto',broadcastto_cmd),CallbackQueryHandler(callbacks,pattern=r'^s3x_')]
