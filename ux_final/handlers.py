from __future__ import annotations
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import CallbackQueryHandler,CommandHandler,ContextTypes,ConversationHandler,MessageHandler,filters
import database
import os, json
from datetime import datetime
from core import admin_roles
from core import user_timezone
from . import service,ui_audit

BRIEF_TIME=901

def _admin(uid): return admin_roles.is_admin_id(uid)

async def _edit(q,text,kb=None):
    try: await q.edit_message_text(text[:3900],reply_markup=kb)
    except Exception as e:
        if 'Message is not modified' not in str(e): raise

def _rows(items,cols=2):
    return [items[i:i+cols] for i in range(0,len(items),cols)]



def _bool_setting(key, default=True):
    v = database.get_setting(key, '1' if default else '0')
    return str(v).lower() not in ('0','false','off','no')

def _toggle_label(key, label, default=True):
    return ('✅ ' if _bool_setting(key, default) else '❌ ') + label

def _settings_home():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔔 Уведомления',callback_data='ux_notify')],
        [InlineKeyboardButton('💜 Аделия',callback_data='ux_ai_settings'),InlineKeyboardButton('📚 Занятия',callback_data='ux_lesson_settings')],
        [InlineKeyboardButton('💳 Оплаты',callback_data='ux_payment_settings'),InlineKeyboardButton('📢 Канал',callback_data='ux_channel_settings')],
        [InlineKeyboardButton('📣 Рассылки',callback_data='ux_broadcast_settings')],
        [InlineKeyboardButton('🕐 Время и тихие часы',callback_data='ux_time_settings')],
        [InlineKeyboardButton('🩺 Состояние системы',callback_data='ux_health'),InlineKeyboardButton('🛡 Безопасность',callback_data='core_main')],
        [InlineKeyboardButton('👨‍🏫 Моя информация',callback_data='admin_contact'),InlineKeyboardButton('⭐ Быстрые действия',callback_data='ux_favorites')],
        [InlineKeyboardButton('📜 История автоматики',callback_data='ux_automation_history'),InlineKeyboardButton('🧪 Проверка настроек',callback_data='ux_health')],
        [InlineKeyboardButton('⬅️ Назад',callback_data='admin_main'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')],
    ])

def _notify_markup():
    specs=[
      ('notify_lesson_24h','24 часа'),('notify_lesson_2h','2 часа'),
      ('notify_lesson_30m','30 минут'),('notify_lesson_10m','10 минут / ссылка'),
      ('notify_homework','Контроль ДЗ'),('notify_payment','Оплаты'),
      ('morning_brief_enabled','Утренняя преподавателю'),('evening_brief_enabled','Вечерняя преподавателю'),
      ('notify_weekly','Недельная сводка'),('notify_channel','События канала'),
      ('student_day_brief_enabled','Утром ученику в день занятия'),
    ]
    rows=[[InlineKeyboardButton(_toggle_label(k,l),callback_data=f'ux_toggle|{k}|ux_notify')] for k,l in specs]
    rows += [[InlineKeyboardButton('🔔 Включить всё',callback_data='ux_notify_all|1'),InlineKeyboardButton('🔕 Выключить всё',callback_data='ux_notify_all|0')],
             [InlineKeyboardButton('🕐 Время сводок',callback_data='ux_time_settings')],
             [InlineKeyboardButton('🧪 Проверить уведомления',callback_data='ux_notify_test'),InlineKeyboardButton('📜 История',callback_data='ux_automation_history')],
             [InlineKeyboardButton('⬅️ Назад',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]
    return InlineKeyboardMarkup(rows)

def _fast_markup(admin_id):
    btn=[]
    for code in service.favorites(admin_id):
        label,cb=service.ACTIONS[code]; btn.append(InlineKeyboardButton(label,callback_data=cb))
    rows=_rows(btn,2)
    rows += [[InlineKeyboardButton('⚙️ Настроить быстрые',callback_data='ux_favorites')],[InlineKeyboardButton('☰ Все функции',callback_data='ux_all')],[InlineKeyboardButton('⬅️ Назад',callback_data='admin_main'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]
    return InlineKeyboardMarkup(rows)

def _all_markup():
    codes=['today','inbox','messages','search','students','book','lessons','schedule','windows','stats','prices','parents','paymethods','swaps','adelia_broadcast','adelia_post','final','system','contact']
    btn=[InlineKeyboardButton(service.ACTIONS[c][0],callback_data=service.ACTIONS[c][1]) for c in codes]
    return InlineKeyboardMarkup(_rows(btn,2)+[[InlineKeyboardButton('⭐ Быстрые действия',callback_data='ux_fast')],[InlineKeyboardButton('⬅️ Назад',callback_data='admin_main'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('ux_'): return
    if not _admin(q.from_user.id): await q.answer('Нет доступа',show_alert=True); return
    await q.answer(); d=q.data
    if d=='ux_fast':
        await _edit(q,'⭐ БЫСТРЫЕ ДЕЙСТВИЯ\n\nТолько то, чем вы пользуетесь каждый день.',_fast_markup(q.from_user.id)); return
    if d=='ux_all':
        await _edit(q,'☰ ВСЕ ФУНКЦИИ\n\nПолный набор административных инструментов.',_all_markup()); return
    if d=='ux_settings':
        await _edit(q,'⚙️ НАСТРОЙКИ\n\nУправление TutorBot без сервера. Переключатели сохраняются в базе.',_settings_home()); return
    if d=='ux_notify':
        await _edit(q,'🔔 УВЕДОМЛЕНИЯ\n\nВыберите, какие автоматические уведомления разрешены.',_notify_markup()); return
    if d.startswith('ux_toggle|'):
        _,key,back=d.split('|',2); database.set_setting(key,'0' if _bool_setting(key) else '1')
        if back=='ux_notify': await _edit(q,'🔔 УВЕДОМЛЕНИЯ\n\n💜 Готово. Настройка уже применяется к автоматике.',_notify_markup())
        elif back=='ux_time_settings':
            await _edit(q,'💜 Готово. Переключатель сохранён.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К сводкам и времени',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]))
        else:
            await _edit(q,'💜 Готово. Переключатель сохранён и уже применяется.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Вернуться в раздел',callback_data=back),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]))
        return
    if d.startswith('ux_notify_all|'):
        val=d.rsplit('|',1)[1]
        for key in ('notify_lesson_24h','notify_lesson_2h','notify_lesson_30m','notify_lesson_10m','notify_homework','notify_payment','morning_brief_enabled','evening_brief_enabled','notify_weekly','notify_channel','student_day_brief_enabled'): database.set_setting(key,val)
        await _edit(q,'🔔 УВЕДОМЛЕНИЯ\n\nВсе переключатели обновлены.',_notify_markup()); return
    if d=='ux_time_settings':
        from crm_plus import service as crm_service
        qs=crm_service.get_setting('quiet_start','22:00'); qe=crm_service.get_setting('quiet_end','08:00'); quiet=f'{qs}-{qe}'; weekly=database.get_setting('weekly_summary_time','09:00')
        morning=database.get_setting('morning_brief_time','08:30'); evening=database.get_setting('evening_brief_time','21:00'); student=database.get_setting('student_day_brief_time','08:00'); tz=database.get_setting('bot_timezone','Europe/Samara')
        ml='✅' if _bool_setting('morning_brief_enabled',True) else '❌'; el='✅' if _bool_setting('evening_brief_enabled',True) else '❌'; sl='✅' if _bool_setting('student_day_brief_enabled',True) else '❌'
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(f'🌍 Часовой пояс • {user_timezone.zone_label(tz)}',callback_data='tz_menu')],
          [InlineKeyboardButton('👥 Регионы пользователей',callback_data='ux_timezone_users')],
          [InlineKeyboardButton(f'{ml} 🌅 Утренняя • {morning}',callback_data='ux_toggle|morning_brief_enabled|ux_time_settings'),InlineKeyboardButton('🕐 Изменить',callback_data='ux_brief_time|morning')],
          [InlineKeyboardButton(f'{el} 🌙 Вечерняя • {evening}',callback_data='ux_toggle|evening_brief_enabled|ux_time_settings'),InlineKeyboardButton('🕐 Изменить',callback_data='ux_brief_time|evening')],
          [InlineKeyboardButton(f'{sl} 🎓 Ученику утром • {student}',callback_data='ux_toggle|student_day_brief_enabled|ux_time_settings'),InlineKeyboardButton('🕐 Изменить',callback_data='ux_brief_time|student')],
          [InlineKeyboardButton('🧪 Утреннюю сейчас',callback_data='ux_brief_test|morning'),InlineKeyboardButton('🧪 Вечернюю сейчас',callback_data='ux_brief_test|evening')],
          [InlineKeyboardButton('🧪 Тест ученику сегодня',callback_data='ux_student_brief_test')],
          [InlineKeyboardButton(('✅ ' if crm_service.get_setting('quiet_enabled','1')=='1' else '❌ ')+' Тихие часы • '+quiet,callback_data='ux_quiet_menu')],
          [InlineKeyboardButton(f'📅 Недельная • {weekly}',callback_data='ux_weekly_menu')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        lastm=database.get_setting('morning_brief_last_ok','ещё не отправлялась'); laste=database.get_setting('evening_brief_last_ok','ещё не отправлялась')
        await _edit(q,f'🕐 СВОДКИ И ВРЕМЯ\n\n🌍 Часовой пояс: {user_timezone.zone_label(tz)}\n\n🌅 Утренняя: {morning}\nПоследняя доставка: {lastm}\n\n🌙 Вечерняя: {evening}\nПоследняя доставка: {laste}\n\n🎓 Ученику утром в день занятия: {student}\n\nТихие часы: {quiet}\nНедельная: {weekly}',kb); return
    if d=='ux_timezone':
        zones=[('🇷🇺 Москва • UTC+3','Europe/Moscow'),('🇷🇺 Самара • UTC+4','Europe/Samara'),('🇷🇺 Екатеринбург • UTC+5','Asia/Yekaterinburg'),('🇷🇺 Омск • UTC+6','Asia/Omsk'),('🇷🇺 Красноярск • UTC+7','Asia/Krasnoyarsk'),('🇷🇺 Иркутск • UTC+8','Asia/Irkutsk')]
        kb=[[InlineKeyboardButton(label,callback_data=f'ux_timezone_set|{zone}')] for label,zone in zones]
        kb.append([InlineKeyboardButton('⬅️ Назад',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')])
        await _edit(q,'🌍 ЧАСОВОЙ ПОЯС\n\n💜 Выберите основной часовой пояс TutorBot. Я сразу пересчитаю время сводок и будущих напоминаний о занятиях.',InlineKeyboardMarkup(kb)); return
    if d.startswith('ux_timezone_set|'):
        zone=d.split('|',1)[1]
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(zone)
        except Exception:
            await q.answer('Не удалось применить этот часовой пояс',show_alert=True); return
        database.set_setting('bot_timezone',zone)
        # Apply immediately to the running bot and reschedule future lesson reminders.
        try:
            import __main__ as runtime
            if hasattr(runtime,'apply_bot_timezone'): runtime.apply_bot_timezone(zone)
            if hasattr(runtime,'schedule_lesson_reminders'):
                for lesson in database.get_upcoming_lessons():
                    try: runtime.schedule_lesson_reminders(context.application,int(lesson['id']))
                    except Exception: pass
        except Exception: pass
        await _edit(q,f'💜 Готово. Теперь весь TutorBot работает по {zone}.\n\nСводки, утренние сообщения ученикам и будущие напоминания о занятиях пересчитаны под новый часовой пояс.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К времени',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_weekly_menu':
        current=database.get_setting('weekly_summary_time','09:00')
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(x,callback_data=f'ux_weekly_time|{x}') for x in ('08:00','09:00','10:00')],[InlineKeyboardButton('⬅️ Назад',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f'📅 НЕДЕЛЬНАЯ СВОДКА\n\nСейчас: {current}. Выберите удобное время.',kb); return
    if d=='ux_student_brief_test':
        from crm_plus import jobs as crm_jobs
        await crm_jobs.student_day_brief_job(context, force=True); await q.answer('💜 Проверила утреннюю сводку ученикам с занятием сегодня',show_alert=True); return
    if d.startswith('ux_brief_time|'):
        kind=d.split('|',1)[1]; context.user_data['ux_brief_kind']=kind
        current=database.get_setting('student_day_brief_time' if kind=='student' else f'{kind}_brief_time', '08:30' if kind=='morning' else ('21:00' if kind=='evening' else '08:00'))
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(x,callback_data=f'ux_brief_set|{kind}|{x}') for x in (('07:30','08:30','09:30') if kind=='morning' else (('20:00','21:00','22:00') if kind=='evening' else ('07:30','08:00','08:30')))],[InlineKeyboardButton('⬅️ Назад',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f"💜 Сейчас {'утренняя' if kind=='morning' else ('вечерняя' if kind=='evening' else 'утренняя сводка ученику в день занятия')} приходит в {current}.\n\nВыберите время ниже или просто напишите своё в формате HH:MM.",kb); return BRIEF_TIME
    if d.startswith('ux_brief_set|'):
        _,kind,value=d.split('|',2); database.set_setting('student_day_brief_time' if kind=='student' else f'{kind}_brief_time',value); await _edit(q,f'💜 Готово. Новое время: {value}. Оно начнёт работать сразу — перезапуск не нужен.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К сводкам',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return ConversationHandler.END
    if d.startswith('ux_brief_test|'):
        kind=d.split('|',1)[1]
        from crm_plus import jobs as crm_jobs
        await (crm_jobs.morning_brief_job(context) if kind=='morning' else crm_jobs.evening_brief_job(context)); await q.answer('💜 Отправила тестовую сводку',show_alert=True); return
    if d.startswith('ux_weekly_time|'):
        database.set_setting('weekly_summary_time',d.split('|',1)[1]); await _edit(q,'✅ Время недельной сводки сохранено. Применится при следующем запуске TutorBot.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Время',callback_data='ux_time_settings')]])); return
    if d=='ux_notify_test':
        try:
            await context.bot.send_message(q.from_user.id,'💜 АДЕЛИЯ • ТЕСТ\n\n🔔 Уведомления преподавателю работают.'); database.log_automation_delivery('notification_test','OK','ADMIN',q.from_user.id); await q.answer('💜 Тест отправлен',show_alert=True)
        except Exception as e:
            database.log_automation_delivery('notification_test','ERROR','ADMIN',q.from_user.id,repr(e)); await q.answer('Не удалось отправить тест',show_alert=True)
        return
    if d=='ux_ai_settings':
        from ai_assistant import client as ai_client
        from ai_assistant import providers as ai_providers
        active=ai_providers.active_provider(); model=(active or {}).get('model','—'); provider=(active or {}).get('title','не подключён'); status='✅ подключена' if active else '❌ провайдер не настроен'
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(_toggle_label('ai_student_drafts_enabled','Черновики ученикам'),callback_data='ux_toggle|ai_student_drafts_enabled|ux_ai_settings')],
          [InlineKeyboardButton(_toggle_label('ai_channel_posts_enabled','Помощь с постами'),callback_data='ux_toggle|ai_channel_posts_enabled|ux_ai_settings')],
          [InlineKeyboardButton(_toggle_label('ai_broadcast_enabled','Помощь с рассылками'),callback_data='ux_toggle|ai_broadcast_enabled|ux_ai_settings')],
          [InlineKeyboardButton('💜 Спросить Аделию',callback_data='mh_ask'),InlineKeyboardButton('🧪 Проверить AI',callback_data='ux_ai_test')],
          [InlineKeyboardButton('🤖 AI-провайдеры',callback_data='aip_home'),InlineKeyboardButton('📊 Расход AI',callback_data='aip_usage')],
          [InlineKeyboardButton('📢 Подготовить пост',callback_data='ac_channel_start'),InlineKeyboardButton('📣 Подготовить рассылку',callback_data='ac_broadcast_start')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f'💜 АДЕЛИЯ • НАСТРОЙКИ\n\nСтатус: {status}\nПровайдер: {provider}\nМодель: {model}\n\nЗдесь реально включаются и выключаются AI-функции. Обычные функции TutorBot от AI не зависят.',kb); return
    if d=='ux_lesson_settings':
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(_toggle_label('notify_lesson_24h','За 24 часа'),callback_data='ux_toggle|notify_lesson_24h|ux_lesson_settings'),InlineKeyboardButton(_toggle_label('notify_lesson_2h','За 2 часа'),callback_data='ux_toggle|notify_lesson_2h|ux_lesson_settings')],
          [InlineKeyboardButton(_toggle_label('notify_lesson_30m','За 30 минут'),callback_data='ux_toggle|notify_lesson_30m|ux_lesson_settings'),InlineKeyboardButton(_toggle_label('notify_lesson_10m','За 10 минут'),callback_data='ux_toggle|notify_lesson_10m|ux_lesson_settings')],
          [InlineKeyboardButton(_toggle_label('notify_homework','Контроль ДЗ'),callback_data='ux_toggle|notify_homework|ux_lesson_settings')],
          [InlineKeyboardButton(_toggle_label('student_day_brief_enabled','Утро ученику в день занятия'),callback_data='ux_toggle|student_day_brief_enabled|ux_lesson_settings')],
          [InlineKeyboardButton('📅 Занятия',callback_data='admin_lessons'),InlineKeyboardButton('⚙️ Расписание',callback_data='admin_schedule')],
          [InlineKeyboardButton('🕐 Время уведомлений',callback_data='ux_time_settings')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,'📚 ЗАНЯТИЯ • НАСТРОЙКИ\n\n💜 Всё, что связано с автоматикой занятий, собрано здесь. Переключатели применяются к реальным reminder-job’ам.',kb); return
    if d=='ux_payment_settings':
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(_toggle_label('notify_payment','Напоминания об оплате'),callback_data='ux_toggle|notify_payment|ux_payment_settings')],
          [InlineKeyboardButton(_toggle_label('payment_auto_cancel_enabled','Автоотмена неоплаченного'),callback_data='ux_toggle|payment_auto_cancel_enabled|ux_payment_settings')],
          [InlineKeyboardButton('💳 Неоплаченные',callback_data='admin_unpaid_lessons'),InlineKeyboardButton('💳 Способы оплаты',callback_data='admin_payment_methods')],
          [InlineKeyboardButton('💰 Цены',callback_data='admin_prices')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,'💳 ОПЛАТЫ • НАСТРОЙКИ\n\n💜 Здесь уже нет заглушек: можно управлять напоминаниями, автоотменой и сразу переходить к реальным платежным инструментам.',kb); return
    if d=='ux_channel_settings':
        try:
            import channel_admin as ca
            cid=ca.get_channel_id(); channel_state=f'✅ подключён • {cid}' if cid else '❌ не подключён'
        except Exception: channel_state='⚠️ не удалось проверить'
        t=database.get_setting('channel_summary_time','08:30') or '08:30'
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(_toggle_label('notify_channel','Утренняя статистика JOIN/LEAVE'),callback_data='ux_toggle|notify_channel|ux_channel_settings')],
          [InlineKeyboardButton(f'🕐 Статистика канала • {t}',callback_data='ux_channel_time')],
          [InlineKeyboardButton('💜 Подготовить пост',callback_data='ac_channel_start'),InlineKeyboardButton('📢 Свободные окна',callback_data='admin_free_windows')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f'📢 КАНАЛ • НАСТРОЙКИ\n\nСтатус: {channel_state}\n\nАвтоприветствий нет. JOIN/LEAVE учитываются тихо и попадают только в админскую статистику.',kb); return
    if d=='ux_broadcast_settings':
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(_toggle_label('ai_broadcast_enabled','Аделия для рассылок'),callback_data='ux_toggle|ai_broadcast_enabled|ux_broadcast_settings')],
          [InlineKeyboardButton('💜 Рассылка с Аделией',callback_data='ac_broadcast_start'),InlineKeyboardButton('📣 Обычная рассылка',callback_data='crm_broadcast')],
          [InlineKeyboardButton('📜 История автоматики',callback_data='ux_automation_history')],
          [InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,'📣 РАССЫЛКИ • НАСТРОЙКИ\n\n💜 Выберите режим и сразу переходите к рабочей рассылке.\n\n🛡 Предпросмотр перед массовой отправкой всегда обязателен и не отключается.',kb); return
    if d=='ux_ai_test':
        from ai_assistant import client as ai_client
        if not ai_client.is_enabled():
            await q.answer('AI-провайдер не настроен',show_alert=True); return
        await q.answer('✅ AI-провайдер настроен. Реальный тест доступен в «AI-провайдеры».',show_alert=True); return
    if d=='ux_quiet_menu':
        from crm_plus import service as crm_service
        enabled=crm_service.get_setting('quiet_enabled','1')=='1'; start=crm_service.get_setting('quiet_start','22:00'); end=crm_service.get_setting('quiet_end','08:00')
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton(('✅ ' if enabled else '❌ ')+'Тихие часы',callback_data='ux_quiet_toggle')],
          [InlineKeyboardButton('22:00–08:00',callback_data='ux_quiet_set|22:00|08:00'),InlineKeyboardButton('23:00–08:00',callback_data='ux_quiet_set|23:00|08:00')],
          [InlineKeyboardButton('22:00–09:00',callback_data='ux_quiet_set|22:00|09:00'),InlineKeyboardButton('23:00–09:00',callback_data='ux_quiet_set|23:00|09:00')],
          [InlineKeyboardButton('⬅️ К времени',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f'🌙 ТИХИЕ ЧАСЫ\n\nСейчас: {start}–{end}\nСтатус: {"включены" if enabled else "выключены"}.\n\nВ этот период некритичные входящие уведомления преподавателю ждут окончания тихих часов.',kb); return
    if d=='ux_quiet_toggle':
        from crm_plus import service as crm_service
        crm_service.set_setting('quiet_enabled','0' if crm_service.get_setting('quiet_enabled','1')=='1' else '1',q.from_user.id)
        await _edit(q,'💜 Готово. Режим тихих часов изменён.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К тихим часам',callback_data='ux_quiet_menu'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d.startswith('ux_quiet_set|'):
        from crm_plus import service as crm_service
        _,start,end=d.split('|',2); crm_service.set_setting('quiet_start',start,q.from_user.id); crm_service.set_setting('quiet_end',end,q.from_user.id)
        await _edit(q,f'💜 Готово. Тихие часы: {start}–{end}.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К тихим часам',callback_data='ux_quiet_menu'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_channel_time':
        current=database.get_setting('channel_summary_time','08:30') or '08:30'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(x,callback_data=f'ux_channel_time_set|{x}') for x in ('07:30','08:30','09:30')],[InlineKeyboardButton('⬅️ Канал',callback_data='ux_channel_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await _edit(q,f'🕐 СТАТИСТИКА КАНАЛА\n\nСейчас: {current}. Время считается в общем часовом поясе TutorBot.',kb); return
    if d.startswith('ux_channel_time_set|'):
        value=d.split('|',1)[1]; database.set_setting('channel_summary_time',value); await _edit(q,f'💜 Готово. Статистика канала будет приходить в {value} по общему часовому поясу TutorBot.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Канал',callback_data='ux_channel_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_health':
        issues=[]; ok=[]
        try:
            c=database.connect(); c.execute('SELECT 1').fetchone(); c.close(); ok.append('✅ База данных')
        except Exception as e: issues.append(('База данных','core_main',repr(e)))
        tz=database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'
        try:
            from zoneinfo import ZoneInfo; ZoneInfo(tz); ok.append(f'✅ Часовой пояс: {tz}')
        except Exception as e: issues.append(('Часовой пояс','ux_time_settings',repr(e)))
        if os.getenv('OPENROUTER_API_KEY','').strip() and 'ВСТАВЬ' not in os.getenv('OPENROUTER_API_KEY',''):
            ok.append('✅ OpenRouter ключ загружен')
        else: issues.append(('OpenRouter','ux_ai_settings','ключ не настроен'))
        try:
            import channel_admin as ca
            if ca.get_channel_id(): ok.append('✅ Канал подключён')
            else: issues.append(('Канал','ux_channel_settings','канал не выбран'))
        except Exception as e: issues.append(('Канал','ux_channel_settings',repr(e)))
        jobs=[]
        try:
            jq=context.application.job_queue
            jobs=[j.name for j in jq.jobs()] if jq else []
            if any('brief_dispatcher' in str(x) for x in jobs): ok.append('✅ Диспетчер сводок работает')
            else: issues.append(('Сводки','ux_time_settings','job не зарегистрирован'))
        except Exception as e: issues.append(('Фоновые задачи','core_main',repr(e)))
        lastm=database.get_setting('morning_brief_last_ok','—'); laste=database.get_setting('evening_brief_last_ok','—')
        lines=['🩺 СОСТОЯНИЕ СИСТЕМЫ','',*ok,'',f'🌅 Последняя утренняя: {lastm}',f'🌙 Последняя вечерняя: {laste}']
        if issues: lines += ['','🟠 Нужно проверить:']+[f'• {x[0]} — {x[2][:90]}' for x in issues]
        else: lines += ['','🟢 Всё основное настроено и готово к работе.']
        kb=[[InlineKeyboardButton('🔄 Проверить заново',callback_data='ux_health'),InlineKeyboardButton('📜 История',callback_data='ux_automation_history')]]
        for name,target,_ in issues[:4]: kb.append([InlineKeyboardButton(f'🔧 {name}',callback_data=target)])
        kb.append([InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')])
        await _edit(q,'\n'.join(lines),InlineKeyboardMarkup(kb)); return
    if d=='ux_automation_history':
        rows=database.get_automation_delivery_history(18); icons={'OK':'✅','ERROR':'❌','SKIPPED':'⏭'}
        names={'morning_brief':'🌅 Утренняя','evening_brief':'🌙 Вечерняя','student_day_brief':'🎓 Утро ученика','weekly_summary':'📅 Недельная','channel_daily':'📢 Канал'}
        lines=['📜 ИСТОРИЯ АВТОМАТИКИ','']
        if not rows: lines += ['💜 История пока пустая. Новые автоматические отправки начнут появляться здесь после установки этой версии.']
        else:
            for r in rows:
                lines.append(f"{icons.get(r['status'],'•')} {names.get(r['kind'],r['kind'])} · {str(r['created_at'])[5:16]}")
                if r['status']!='OK' and r['detail']: lines.append('   '+str(r['detail'])[:110])
        await _edit(q,'\n'.join(lines),InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Обновить',callback_data='ux_automation_history')],[InlineKeyboardButton('🧪 Проверить настройки',callback_data='ux_health')],[InlineKeyboardButton('⬅️ Настройки',callback_data='ux_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_favorites':
        chosen=set(service.favorites(q.from_user.id)); kb=[]
        for code,(label,_) in service.ACTIONS.items(): kb.append([InlineKeyboardButton(('✅ ' if code in chosen else '➕ ')+label,callback_data=f'ux_fav_toggle|{code}')])
        kb += [[InlineKeyboardButton('⭐ Готово',callback_data='ux_fast')]]
        await _edit(q,'⚙️ НАСТРОЙКА БЫСТРЫХ ДЕЙСТВИЙ\n\nНажмите, чтобы добавить или убрать пункт.',InlineKeyboardMarkup(kb)); return
    if d.startswith('ux_fav_toggle|'):
        service.toggle(q.from_user.id,d.split('|',1)[1]); chosen=set(service.favorites(q.from_user.id)); kb=[]
        for code,(label,_) in service.ACTIONS.items(): kb.append([InlineKeyboardButton(('✅ ' if code in chosen else '➕ ')+label,callback_data=f'ux_fav_toggle|{code}')])
        kb += [[InlineKeyboardButton('⭐ Готово',callback_data='ux_fast')]]
        await _edit(q,'⚙️ НАСТРОЙКА БЫСТРЫХ ДЕЙСТВИЙ\n\nНажмите, чтобы добавить или убрать пункт.',InlineKeyboardMarkup(kb)); return
    if d.startswith('ux_student_pin|'):
        uid=int(d.split('|')[1]); state=service.toggle_student_pin(q.from_user.id,uid)
        await q.answer('Ученик закреплён' if state else 'Ученик откреплён',show_alert=False)
        from students_admin import show_student
        await show_student(q,uid); return
    if d.startswith('ux_student_more|'):
        uid=int(d.split('|')[1]); u=database.get_user(uid); name=u['name'] if u else str(uid)
        kb=InlineKeyboardMarkup([
          [InlineKeyboardButton('📚 Занятия',callback_data=f'student_lessons|{uid}'),InlineKeyboardButton('📊 Статистика',callback_data=f'admin_student_stats|{uid}')],
          [InlineKeyboardButton('⏱ Основное время',callback_data=f'min_duration_user|{uid}'),InlineKeyboardButton('🎟 Баланс подробно',callback_data=f'student_balance|{uid}')],
          [InlineKeyboardButton('🚀 Центр ученика',callback_data=f'ff_student|{uid}'),InlineKeyboardButton('🧭 Коммуникация',callback_data=f'crm_student|{uid}')],
          [InlineKeyboardButton('🔗 Учебная связка',callback_data=f'ux_learning_chain|{uid}')],
          [InlineKeyboardButton('🖥 Доска',callback_data=f'admin_board_set|{uid}'),InlineKeyboardButton('➕ Направление',callback_data=f'admin_program_add|{uid}')],
          [InlineKeyboardButton('🏖 Пауза',callback_data=f'crm_pause|{uid}'),InlineKeyboardButton('📜 История',callback_data=f'ff_timeline|{uid}')],
          [InlineKeyboardButton('🚫 Вкл/выкл',callback_data=f'student_toggle_active|{uid}'),InlineKeyboardButton('🗑 Удалить',callback_data=f'admin_student_delete_warn|{uid}')],
          [InlineKeyboardButton('⬅️ Карточка',callback_data=f'student_view|{uid}')],
        ])
        await _edit(q,f'••• ЕЩЁ\n\n👤 {name}\n\nДополнительные действия по ученику:',kb); return
    if d.startswith('ux_learning_chain|'):
        uid=int(d.split('|')[1]); x=service.learning_chain(uid); lines=[f"🔗 УЧЕБНАЯ СВЯЗКА\n\n👤 {x['name']}"]
        if x['topics']:
            lines += ['','🧠 Что требует внимания:']+[f"• {r['topic']} — {r['mastery']}%"+(f" · {r['note']}" if r['note'] else '') for r in x['topics']]
        else: lines += ['','🧠 Темы пока не отмечены.']
        hw=x['homework']; lines += ['', '📝 ДЗ: '+(f"{hw['title']} · {hw['status']}" if hw else 'нет активного')]
        m=x['mock']; lines += ['🧪 Пробник: '+(f"{m['title']} · {m['test_score'] if m['test_score'] is not None else 'без результата'}" if m else 'нет')]
        up=x['upcoming']; lines += ['📅 Следующий урок: '+(str(up['start_time'])[:16].replace('T',' ') if up else 'не назначен')]
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🧠 Итог последнего урока',callback_data=f'crm_review_latest|{uid}'),InlineKeyboardButton('🧪 Пробники',callback_data=f'ff_mocks|{uid}')],[InlineKeyboardButton('📝 ДЗ',callback_data=f'student_homeworks|{uid}'),InlineKeyboardButton('📅 Записать',callback_data=f'admin_manual_for|{uid}')],[InlineKeyboardButton('⬅️ Ещё',callback_data=f'ux_student_more|{uid}')]])
        await _edit(q,'\n'.join(lines),kb); return
    if d.startswith('ux_review_start'):
        try: mode=d.split('|',1)[1]
        except Exception:
            tz=database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'
            try:
                from zoneinfo import ZoneInfo; hour=datetime.now(ZoneInfo(tz)).hour
            except Exception: hour=datetime.now().hour
            mode='morning' if hour<12 else ('evening' if hour>=18 else 'day')
        context.user_data['ux_review_mode']=mode; context.user_data['ux_review_done']=[]; context.user_data['ux_review_deferred']=[]
        d='ux_review_show|0'
    if d.startswith('ux_review_show|'):
        mode=context.user_data.get('ux_review_mode','day')
        from crm_plus import service as crm_service
        dash=crm_service.today_dashboard()
        c=database.connect()
        try:
            hw=0
            try: hw=int(c.execute("SELECT COUNT(*) FROM homework WHERE status IN ('ASSIGNED','REVISION') AND deadline IS NOT NULL AND datetime(deadline)<datetime('now')").fetchone()[0] or 0)
            except Exception: pass
            no_next=0
            try:
                no_next=int(c.execute("SELECT COUNT(*) FROM users u WHERE u.active=1 AND NOT EXISTS (SELECT 1 FROM lessons l WHERE l.user_id=u.id AND l.cancelled_at IS NULL AND l.finished_at IS NULL AND datetime(l.start_time)>=datetime('now'))").fetchone()[0] or 0)
            except Exception: pass
            tomorrow=0
            try: tomorrow=int(c.execute("SELECT COUNT(*) FROM lessons WHERE date(start_time)=date('now','+1 day') AND lesson_status!='CANCELLED'").fetchone()[0] or 0)
            except Exception: pass
        finally: c.close()
        messages=int(dash.get('open_messages') or 0); unpaid=int(dash.get('unpaid') or 0); attention=len(dash.get('attention') or []); lessons=len(dash.get('lessons') or [])
        try:
            from core import teacher_tasks
            teacher_tasks.sync_auto(); task_count=len(teacher_tasks.list_open(50))
        except Exception: task_count=0
        if mode=='morning':
            items=[('📌 Задачи',task_count,'Сначала соберём рабочие задачи и автоматические хвосты.','task_home'),('💬 Сообщения',messages,'Разберём ответы, которые уже ждут вас.','admin_student_messages'),('💳 Оплаты',unpaid,'Проверим неоплаченные занятия.','mh_debts'),('📝 ДЗ',hw,'Посмотрим просроченные или требующие внимания ДЗ.','admin_homework'),('📅 Сегодня',lessons,'В конце сверим сегодняшние занятия.','crm_today')]
        elif mode=='evening':
            items=[('📌 Задачи',task_count,'Закроем или отложим рабочие задачи перед завершением дня.','task_home'),('💬 Сообщения',messages,'Закроем сообщения, которые не стоит переносить на завтра.','admin_student_messages'),('💳 Оплаты',unpaid,'Проверим оставшиеся оплаты.','mh_debts'),('📝 ДЗ',hw,'Посмотрим незакрытые домашние задания.','admin_homework'),('📅 Завтра',tomorrow,'И в конце спокойно сверим завтрашний день.','crm_today')]
        else:
            items=[('📌 Задачи',task_count,'Разберём рабочие задачи.','task_home'),('💬 Сообщения',messages,'Разберём сообщения.','admin_student_messages'),('💳 Оплаты',unpaid,'Проверим оплаты.','mh_debts'),('⚠️ Требуют внимания',attention,'Посмотрим важные случаи.','mh_attention'),('📅 Сегодня',lessons,'Сверим занятия.','crm_today')]
        try:i=max(0,min(len(items)-1,int(d.split('|')[1])))
        except Exception:i=0
        done=context.user_data.get('ux_review_done',[]); deferred=context.user_data.get('ux_review_deferred',[])
        title,count,desc,target=items[i]; pct=int(((i+1)/len(items))*100); blocks='█'*max(1,round(pct/20))+'░'*(5-max(1,round(pct/20)))
        mode_title='УТРЕННИЙ РАЗБОР' if mode=='morning' else ('ВЕЧЕРНИЙ РАЗБОР' if mode=='evening' else 'РАЗБОР')
        rows=[[InlineKeyboardButton(f'Открыть: {title} • {count}',callback_data=target)],
              [InlineKeyboardButton('✅ Готово, дальше',callback_data=f'ux_review_done_item|{i}'),InlineKeyboardButton('🕐 Отложить',callback_data=f'ux_review_defer|{i}')],
              [InlineKeyboardButton('⬅️ Предыдущая',callback_data=f'ux_review_show|{max(0,i-1)}'),InlineKeyboardButton('⏭ Дальше',callback_data=f'ux_review_show|{min(len(items)-1,i+1)}')],
              [InlineKeyboardButton('💜 Спросить Аделию',callback_data='mh_ask')],
              [InlineKeyboardButton('✕ Закончить',callback_data='ux_review_done'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]
        await _edit(q,f'💜 АДЕЛИЯ • {mode_title}\n\nШаг {i+1} из {len(items)}\n{blocks} {pct}%\n\n{title} • {count}\n{desc}\n\n✅ Закрыто шагов: {len(done)}\n🕐 Отложено: {len(deferred)}',InlineKeyboardMarkup(rows)); return
    if d.startswith('ux_review_done_item|') or d.startswith('ux_review_defer|'):
        i=int(d.split('|')[1]); key='ux_review_deferred' if 'defer' in d else 'ux_review_done'; arr=context.user_data.setdefault(key,[])
        if i not in arr: arr.append(i)
        nxt=min(4,i+1); word='Отложила' if 'defer' in d else 'Отметила готовым'
        await _edit(q,f'💜 {word}. Продолжаем по очереди.',InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Следующий шаг',callback_data=f'ux_review_show|{nxt}')],[InlineKeyboardButton('✕ Закончить',callback_data='ux_review_done'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_review_done':
        mode=context.user_data.get('ux_review_mode','day'); done=len(context.user_data.get('ux_review_done',[])); deferred=len(context.user_data.get('ux_review_deferred',[]))
        context.user_data.pop('ux_review_index',None)
        ending='День подготовлен' if mode=='morning' else ('День закрыт' if mode=='evening' else 'Разбор завершён')
        await _edit(q,f'💜 {ending}.\n\n✅ Отмечено готовыми: {done}\n🕐 Отложено: {deferred}\n\nОтложенное не потерялось — к нему можно вернуться позже.',InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Разобрать ещё раз',callback_data=f'ux_review_start|{mode}')],[InlineKeyboardButton('📜 История автоматики',callback_data='ux_automation_history')],[InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    if d=='ux_ui_audit':
        hits=ui_audit.run(); lines=['🧪 ПРОВЕРКА ИНТЕРФЕЙСА','']
        if hits:
            lines.append(f'⚠️ Найдено потенциальных технических элементов: {len(hits)}')
            for f,n,line in hits[:15]: lines.append(f'• {f}:{n}\n  {line[:110]}')
        else: lines += ['✅ Технические USER_ID / PROGRAM_ID / MOCK_ID и служебные команды в пользовательских сообщениях не обнаружены.']
        lines += ['','Проверка не меняет данные и предназначена для запуска перед обновлением.']
        await _edit(q,'\n'.join(lines),InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Система',callback_data='core_main')]])); return

async def audit_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id): return
    hits=ui_audit.run(); await update.message.reply_text('🧪 UI CHECK\n\n'+('✅ Всё чисто.' if not hits else f'⚠️ Подозрительных мест: {len(hits)}'))

async def brief_time_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    value=(update.message.text or '').strip()
    try: datetime.strptime(value,'%H:%M')
    except Exception:
        await update.message.reply_text('💜 Не смогла прочитать время. Напишите, например: 21:30'); return BRIEF_TIME
    kind=context.user_data.pop('ux_brief_kind',None)
    if kind not in ('morning','evening','student'): return ConversationHandler.END
    database.set_setting('student_day_brief_time' if kind=='student' else f'{kind}_brief_time',value)
    await update.message.reply_text(f'💜 Готово. Поставила {value}. Перезапуск TutorBot не нужен.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К сводкам',callback_data='ux_time_settings'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]))
    return ConversationHandler.END

def handlers():
    conv=ConversationHandler(entry_points=[CallbackQueryHandler(callbacks,pattern=r'^ux_brief_time\|')],states={BRIEF_TIME:[MessageHandler(filters.TEXT & ~filters.COMMAND,brief_time_text),CallbackQueryHandler(callbacks,pattern=r'^ux_brief_set\|')]},fallbacks=[],allow_reentry=True)
    return [conv,CallbackQueryHandler(callbacks,pattern=r'^ux_'),CommandHandler('uicheck',audit_cmd)]
