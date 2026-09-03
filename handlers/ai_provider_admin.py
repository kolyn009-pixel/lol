from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters
from ai_assistant import providers
from core import admin_roles
import database

WAIT_KEY,WAIT_MODEL,WAIT_BASE,WAIT_EDIT_MODEL=1401,1402,1403,1404

def _admin(uid): return admin_roles.is_admin_id(uid)

async def _edit(q,text,kb=None):
    try: await q.edit_message_text(text[:3900],reply_markup=kb)
    except Exception as e:
        if 'Message is not modified' not in str(e): raise

def _menu():
    rows=[]; cfg=providers.load_config(); active=cfg.get('active','openrouter_env')
    for p in providers.provider_list():
        icon='✅' if p['id']==active else ('🟢' if p.get('enabled',True) else '⚫')
        rows.append([InlineKeyboardButton(f"{icon} {p.get('title',p['id'])} • {p.get('model','')[:26]}",callback_data=f"aip_view|{p['id']}")])
    rows += [[InlineKeyboardButton('➕ Добавить AI-провайдер',callback_data='aip_add')],
             [InlineKeyboardButton('📊 Использование сегодня',callback_data='aip_usage')],
             [InlineKeyboardButton('⬅️ Аделия',callback_data='ux_ai_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]
    return InlineKeyboardMarkup(rows)

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('aip_'): return
    if not _admin(q.from_user.id): await q.answer('Нет доступа',show_alert=True); return
    await q.answer(); d=q.data
    if d=='aip_home':
        await _edit(q,'🤖 AI-ПРОВАЙДЕРЫ\n\n💜 Можно подключать провайдеры прямо отсюда. OpenRouter остаётся рабочим по умолчанию.\n\nЕсли основной провайдер недоступен, Аделия пробует следующий включённый.',_menu()); return
    if d=='aip_add':
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('OpenRouter',callback_data='aip_type|openrouter')],[InlineKeyboardButton('Gemini',callback_data='aip_type|gemini')],[InlineKeyboardButton('DeepSeek',callback_data='aip_type|deepseek')],[InlineKeyboardButton('Другой OpenAI-совместимый',callback_data='aip_type|custom')],[InlineKeyboardButton('⬅️ Назад',callback_data='aip_home')]])
        await _edit(q,'➕ ДОБАВИТЬ AI-ПРОВАЙДЕР\n\nВыберите тип. После подключения провайдер не станет основным сам — сначала его можно проверить.',kb); return
    if d.startswith('aip_type|'):
        typ=d.split('|',1)[1]; context.user_data['aip_type']=typ; context.user_data.pop('aip_model',None); context.user_data.pop('aip_base',None)
        if typ=='custom':
            await _edit(q,'🌐 ДРУГОЙ ПРОВАЙДЕР\n\nПришлите base URL OpenAI-совместимого API.\nНапример: https://example.com/v1',InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data='aip_home')]])); return WAIT_BASE
        await _edit(q,'🔐 API-КЛЮЧ\n\nПришлите API key одним сообщением. Я постараюсь удалить это сообщение сразу после чтения, сохраню ключ только в защищённом серверном файле с правами root и больше полностью его не покажу.\n\n⚠️ Ключи присылайте только в личный чат с ботом.',InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data='aip_home')]])); return WAIT_KEY
    if d.startswith('aip_view|'):
        pid=d.split('|',1)[1]; p=providers.get_provider(pid); cfg=providers.load_config()
        if not p: await _edit(q,'Провайдер не найден.',_menu()); return
        active=cfg.get('active')==pid; mask=providers.mask_key(str(p.get('api_key') or ''))
        kb=[[InlineKeyboardButton('🧪 Проверить',callback_data=f'aip_test|{pid}')]]
        if not active: kb.append([InlineKeyboardButton('✅ Сделать основным',callback_data=f'aip_active|{pid}')])
        if pid!='openrouter_env':
            kb.append([InlineKeyboardButton('✏️ Изменить модель',callback_data=f'aip_model|{pid}')])
            kb.append([InlineKeyboardButton(('⏸ Выключить' if p.get('enabled',True) else '▶️ Включить'),callback_data=f'aip_toggle|{pid}'),InlineKeyboardButton('🗑 Удалить',callback_data=f'aip_delete|{pid}')])
        kb.append([InlineKeyboardButton('⬅️ Провайдеры',callback_data='aip_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')])
        await _edit(q,f"🤖 {p.get('title')}\n\nСтатус: {'основной' if active else ('включён' if p.get('enabled',True) else 'выключен')}\nМодель: {p.get('model')}\nКлюч: {mask}\n\n💜 Ключ целиком здесь никогда не отображается.",InlineKeyboardMarkup(kb)); return
    if d.startswith('aip_model|'):
        pid=d.split('|',1)[1]; context.user_data['aip_edit_pid']=pid; p=providers.get_provider(pid)
        await _edit(q,f"✏️ МОДЕЛЬ • {p.get('title') if p else pid}\n\nСейчас: {(p or {}).get('model','—')}\n\nПришлите новое имя модели одним сообщением.",InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data=f'aip_view|{pid}')]])); return WAIT_EDIT_MODEL
    if d.startswith('aip_active|'):
        pid=d.split('|',1)[1]; providers.set_active(pid); await _edit(q,'💜 Готово. Этот провайдер теперь основной. Если он не ответит, Аделия автоматически попробует следующий.',_menu()); return
    if d.startswith('aip_toggle|'):
        pid=d.split('|',1)[1]; providers.toggle_provider(pid); await _edit(q,'💜 Статус провайдера изменён.',_menu()); return
    if d.startswith('aip_delete|'):
        pid=d.split('|',1)[1]; providers.delete_provider(pid); await _edit(q,'💜 Провайдер удалён.',_menu()); return
    if d.startswith('aip_test|'):
        pid=d.split('|',1)[1]; await _edit(q,'💜 Проверяю подключение…')
        try:
            import asyncio; answer=await asyncio.to_thread(providers.test_provider,pid)
            await _edit(q,f'✅ Подключение работает.\n\nОтвет провайдера: {answer}',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К провайдеру',callback_data=f'aip_view|{pid}')]]))
        except Exception as e:
            await _edit(q,f'❌ Не удалось подключиться.\n\n{str(e)[:900]}',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К провайдеру',callback_data=f'aip_view|{pid}')]]))
        return
    if d=='aip_usage':
        from datetime import datetime; day=datetime.now().strftime('%Y-%m-%d'); lines=['📊 AI • СЕГОДНЯ','']
        for p in providers.provider_list():
            ok=int(database.get_setting(f"ai_usage:{day}:{p['id']}:ok",'0') or 0); er=int(database.get_setting(f"ai_usage:{day}:{p['id']}:error",'0') or 0)
            lines.append(f"{p.get('title')}: {ok} запросов"+(f" · ошибок {er}" if er else ''))
        lines += ['','💜 Расписание, уведомления, сводки, задачи и CRM не расходуют AI-запросы.']
        await _edit(q,'\n'.join(lines),InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Провайдеры',callback_data='aip_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return

async def base_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    value=(update.message.text or '').strip()
    if not value.startswith(('http://','https://')):
        await update.message.reply_text('💜 Нужен полный URL, начинающийся с https://'); return WAIT_BASE
    context.user_data['aip_base']=value.rstrip('/')
    await update.message.reply_text('Теперь пришлите название модели, которое ожидает этот API.'); return WAIT_MODEL

async def model_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    context.user_data['aip_model']=(update.message.text or '').strip()
    await update.message.reply_text('🔐 Теперь пришлите API key одним сообщением.'); return WAIT_KEY

async def edit_model_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    pid=context.user_data.pop('aip_edit_pid',None); model=(update.message.text or '').strip()
    if not pid or not model:
        return ConversationHandler.END
    providers.update_model(pid,model)
    await update.message.reply_text(f'💜 Готово. Модель сохранена: {model}',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧪 Проверить',callback_data=f'aip_test|{pid}')],[InlineKeyboardButton('⬅️ К провайдеру',callback_data=f'aip_view|{pid}')]])); return ConversationHandler.END

async def key_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    key=(update.message.text or '').strip(); typ=context.user_data.get('aip_type')
    try: await update.message.delete()
    except Exception: pass
    if len(key)<8:
        await context.bot.send_message(update.effective_chat.id,'💜 Ключ выглядит слишком коротким. Попробуйте ещё раз.'); return WAIT_KEY
    pid=providers.save_provider(typ,key,model=context.user_data.get('aip_model',''),base_url=context.user_data.get('aip_base',''))
    context.user_data.pop('aip_type',None); context.user_data.pop('aip_model',None); context.user_data.pop('aip_base',None)
    await context.bot.send_message(update.effective_chat.id,f'💜 Провайдер сохранён. Ключ: {providers.mask_key(key)}\n\nСначала проверьте подключение, затем при желании сделайте его основным.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧪 Проверить',callback_data=f'aip_test|{pid}')],[InlineKeyboardButton('🤖 AI-провайдеры',callback_data='aip_home')]])); return ConversationHandler.END

def handlers():
    conv=ConversationHandler(entry_points=[CallbackQueryHandler(callbacks,pattern=r'^aip_type\|'),CallbackQueryHandler(callbacks,pattern=r'^aip_model\|')],states={WAIT_BASE:[MessageHandler(filters.TEXT & ~filters.COMMAND,base_text)],WAIT_MODEL:[MessageHandler(filters.TEXT & ~filters.COMMAND,model_text)],WAIT_KEY:[MessageHandler(filters.TEXT & ~filters.COMMAND,key_text)],WAIT_EDIT_MODEL:[MessageHandler(filters.TEXT & ~filters.COMMAND,edit_model_text)]},fallbacks=[],allow_reentry=True)
    return [conv,CallbackQueryHandler(callbacks,pattern=r'^aip_')]
