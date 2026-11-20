from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
import database
from core import admin_roles, audit_log, event_center
from automation import waiting_list, balance_forecast, family, notifications, messaging, referrals, student_history, schedule_tools, operations


def _student(update):
    return database.get_user_by_telegram_id(update.effective_user.id)


def _parent(update):
    conn=database.connect(); row=conn.execute('SELECT * FROM parent_accounts WHERE telegram_id=?',(update.effective_user.id,)).fetchone(); conn.close(); return row

async def operations_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    lessons=operations.today_dashboard(); attention=operations.attention_items()
    lines=['🤖 <b>ОПЕРАЦИОННЫЙ ПОМОЩНИК</b>','','🔥 <b>Сегодня</b>']
    if lessons:
        for r in lessons[:20]: lines.append(f"{str(r['start_time'])[11:16]} · {r['name']} · {r['subject'] or 'занятие'} · {r['lesson_status']}")
    else: lines.append('Занятий нет.')
    lines += ['',f"📥 <b>Требует внимания: {len(attention)}</b>"]
    for x in attention[:12]: lines.append(f"• {x['title']} — {x['details']}")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('📋 Лист ожидания',callback_data='s3_wait_admin'),InlineKeyboardButton('📩 Обращения',callback_data='s3_inbox')],[InlineKeyboardButton('🧭 История ученика',callback_data='s3_history_help'),InlineKeyboardButton('💳 Прогноз баланса',callback_data='s3_forecast_help')]])
    await update.message.reply_text('\n'.join(lines)[:3900],parse_mode='HTML',reply_markup=kb)

async def waitlist_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user=_student(update)
    if not user: return
    note=' '.join(context.args).strip() if context.args else None
    wid=waiting_list.add(user['id'],subject=user['main_subject'],study_goal=user['study_goal'],note=note)
    student_history.add(user['id'],'WAITING_LIST','Добавлен в лист ожидания',note,'waiting_list',wid)
    event_center.push('WAITING_LIST',f"Лист ожидания: {user['name']}",note or 'Без комментария',priority='INFO',dedupe_key=f'wait:{wid}')
    await update.message.reply_text('✅ Готово, я добавила тебя в лист ожидания. Если подходящее окно освободится, я смогу предложить его тебе 💜')

async def forecast_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user=_student(update)
    if not user: return
    f=balance_forecast.forecast(user['id']); text=f"🎟 <b>Баланс и прогноз</b>\n\nОсталось времени: <b>{f['remaining']} мин</b>"
    if f['through']: text += f"\n📅 При текущих уже назначенных занятиях хватит примерно до <b>{f['through']}</b>."
    if f['nominals']:
        text += '\n\nНоминалы:\n'+'\n'.join(f"• {r.get('hourly_rate',0)} ₽/60 мин — {r.get('total',0)} мин" for r in f['nominals'])
    await update.message.reply_text(text,parse_mode='HTML')

async def referral_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user=_student(update)
    if not user:return
    r=referrals.get_or_create(user['id'])
    await update.message.reply_text(f"🎁 <b>Ваш реферальный код</b>\n\n<code>{r['code']}</code>\n\nПередайте его знакомому. Бонус начисляется после выполнения условий, заданных преподавателем.",parse_mode='HTML')

async def claimref_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user=_student(update)
    if not user or not context.args: return
    ok,res=referrals.claim(context.args[0],user['id'])
    if ok:
        event_center.push('REFERRAL_CLAIM','Использован реферальный код',f"Ученик {user['name']} использовал {context.args[0]}",priority='ACTION',dedupe_key=f"refclaim:{res['id']}")
        student_history.add(user['id'],'REFERRAL','Использован реферальный код',context.args[0],'referral',res['id'])
        await update.message.reply_text('✅ Код принят. Бонус будет начислен после выполнения условий.')
    else: await update.message.reply_text('❌ '+str(res))

async def family_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    p=_parent(update)
    if not p:return
    rows=family.dashboard(p['id']); lines=['👨‍👩‍👧 <b>Семейный кабинет</b>','']
    for x in rows:
        s=x['student']; n=x['next_lesson']; f=x['forecast']; lines.append(f"👤 <b>{s['name']}</b>\n🎟 Остаток: {f['remaining']} мин" + (f"\n📅 Следующее: {str(n['start_time'])[:10]} {str(n['start_time'])[11:16]}" if n else '\n📅 Ближайших занятий нет')+'\n')
    await update.message.reply_text('\n'.join(lines)[:3900],parse_mode='HTML')

async def history_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text('Использование: /history STUDENT_ID'); return
    sid=int(context.args[0]); student_history.rebuild_basic(sid); rows=student_history.recent(sid,30); u=database.get_user(sid)
    lines=[f"📜 <b>История: {u['name'] if u else sid}</b>",'']+[f"{r['created_at'][5:16].replace('T',' ')} · {r['title']}"+(f" — {r['details']}" if r['details'] else '') for r in rows]
    await update.message.reply_text('\n'.join(lines)[:3900],parse_mode='HTML')

async def pause_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if len(context.args)<3 or not context.args[0].isdigit():
        await update.message.reply_text('Использование: /pause STUDENT_ID YYYY-MM-DD YYYY-MM-DD [причина]'); return
    sid=int(context.args[0]); rid=schedule_tools.add_pause(sid,context.args[1],context.args[2],' '.join(context.args[3:]) or None,update.effective_user.id); audit_log.log('STUDENT_PAUSE',update.effective_user.id,'student',sid,{'from':context.args[1],'to':context.args[2]}); await update.message.reply_text(f'✅ Готово, я оформила паузу #{rid}. 💜')

async def absence_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    if len(context.args)<2:
        await update.message.reply_text('Использование: /absence YYYY-MM-DD YYYY-MM-DD [причина]'); return
    rid=schedule_tools.add_teacher_absence(context.args[0],context.args[1],' '.join(context.args[2:]) or None,'SICK',update.effective_user.id); affected=schedule_tools.affected_lessons(context.args[0],context.args[1]); audit_log.log('TEACHER_ABSENCE',update.effective_user.id,'absence',rid,{'affected':len(affected)}); await update.message.reply_text(f'🩺 Период недоступности сохранён. Затронутых занятий: {len(affected)}.\n\nПеред массовой отменой/переносом требуется отдельное подтверждение — бот ничего не удалил автоматически.')

async def broadcast_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    text=' '.join(context.args).strip()
    if not text: await update.message.reply_text('Использование: /broadcast текст сообщения'); return
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Отправить всем ученикам',callback_data='s3_broadcast_confirm')],[InlineKeyboardButton('❌ Отмена',callback_data='s3_cancel')]])
    context.user_data['s3_broadcast']=text; await update.message.reply_text(f'⚠️ Массовая рассылка:\n\n{text[:2500]}',reply_markup=kb)

async def schedulemsg_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    raw=' '.join(context.args)
    if '|' not in raw:
        await update.message.reply_text('Использование: /schedulemsg YYYY-MM-DD HH:MM | текст'); return
    left,text=[x.strip() for x in raw.split('|',1)]
    try: local_at=datetime.strptime(left,'%Y-%m-%d %H:%M')
    except ValueError: await update.message.reply_text('Неверная дата. Пример: /schedulemsg 2026-09-01 10:00 | Текст'); return
    # Input is the admin's local time (personal region, else bot_timezone);
    # messaging.schedule converts it to the queue's MSK storage convention.
    tz,label=schedulemsg_input_tz(update.effective_user.id)
    mid=messaging.schedule(update.effective_user.id,text,local_at.replace(tzinfo=tz),'ALL'); await update.message.reply_text(f'✅ Сообщение #{mid} запланировано на {left} ({label}).')


def schedulemsg_input_tz(telegram_id):
    from zoneinfo import ZoneInfo
    from core import user_timezone
    zone=database.get_setting('bot_timezone','Europe/Samara') or 'Europe/Samara'
    try:
        return user_timezone.user_tz(int(telegram_id),zone),user_timezone.user_label(int(telegram_id),zone)
    except Exception:
        try: return ZoneInfo(zone),zone
        except Exception: return ZoneInfo('Europe/Samara'),'Europe/Samara'

async def question_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    text=' '.join(context.args).strip()
    if not text:
        await update.message.reply_text('Использование: /question ваш организационный вопрос'); return
    s=_student(update); p=_parent(update); iid=messaging.create_inbox(text,update.effective_user.id,student_id=s['id'] if s else None,parent_id=p['id'] if p else None,subject='Организационный вопрос')
    event_center.push('TEACHER_INBOX','Новый организационный вопрос',text[:500],priority='ACTION',dedupe_key=f'inbox:{iid}')
    await update.message.reply_text('✅ Готово, я отправила вопрос преподавателю. 💜')

async def notifysettings_cmd(update:Update, context:ContextTypes.DEFAULT_TYPE):
    p=_parent(update)
    if not p:return
    students=database.get_parent_students(p['id'])
    if not students:
        await update.message.reply_text('Нет привязанных учеников.'); return
    if context.args and context.args[0].isdigit():
        sid=int(context.args[0])
    elif len(students)==1:
        sid=students[0]['id']
    else:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(st['name'],callback_data=f's3_notify_student|{st["id"]}')] for st in students])
        await update.message.reply_text('Для кого настроить напоминания?',reply_markup=kb); return
    await _show_notify_settings(update.effective_message,p['id'],sid)

async def _show_notify_settings(message,parent_id,student_id,edit=False):
    prefs=notifications.get(parent_id,student_id); u=database.get_user(student_id)
    labels=[('remind_24h','24 часа'),('remind_2h','2 часа'),('remind_30m','30 минут'),('remind_10m','10 минут'),('schedule_changes','изменения расписания'),('payments','оплаты'),('monthly_report','месячный отчёт')]
    text=f"🔔 <b>Уведомления: {u['name'] if u else student_id}</b>\n\n"+'\n'.join(('✅' if prefs[k] else '❌')+' '+label for k,label in labels)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton(('✅ ' if prefs[k] else '❌ ')+label,callback_data=f's3_notify_toggle|{student_id}|{k}')] for k,label in labels])
    if edit: await message.edit_text(text,parse_mode='HTML',reply_markup=kb)
    else: await message.reply_text(text,parse_mode='HTML',reply_markup=kb)

async def callbacks(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q.data.startswith('s3_'): return
    await q.answer(); data=q.data
    if data=='s3_cancel': await q.edit_message_text('Отменено.'); return
    if data=='s3_broadcast_confirm':
        if not admin_roles.is_admin_id(q.from_user.id): return
        text=context.user_data.pop('s3_broadcast',None)
        if not text: await q.edit_message_text('Черновик рассылки уже недоступен.'); return
        conn=database.connect(); ids=[r['telegram_id'] for r in conn.execute('SELECT telegram_id FROM users WHERE telegram_id IS NOT NULL').fetchall()]; conn.close(); ok=0
        for tid in ids:
            try: await context.bot.send_message(tid,text); ok+=1
            except Exception: pass
        audit_log.log('BROADCAST',q.from_user.id,details={'sent':ok,'total':len(ids)}); await q.edit_message_text(f'✅ Отправлено: {ok}/{len(ids)}'); return
    if data=='s3_wait_admin':
        if not admin_roles.is_admin_id(q.from_user.id): return
        rows=waiting_list.active(); txt='📋 ЛИСТ ОЖИДАНИЯ\n\n'+('\n'.join(f"#{r['id']} · {r['name']} · {r['preferred_date'] or 'любая дата'} · {r['note'] or 'без комментария'}" for r in rows[:40]) if rows else 'Пусто.')
        await q.edit_message_text(txt[:3900]); return
    if data=='s3_inbox':
        if not admin_roles.is_admin_id(q.from_user.id): return
        rows=messaging.inbox(); txt='📩 ОБРАЩЕНИЯ\n\n'+('\n\n'.join(f"#{r['id']} · {r['created_at'][5:16]}\n{r['body']}" for r in rows[:25]) if rows else 'Нет открытых обращений.')
        await q.edit_message_text(txt[:3900]); return
    if data=='s3_history_help': await q.edit_message_text('Использование: /history STUDENT_ID'); return
    if data=='s3_forecast_help': await q.edit_message_text('Ученик может использовать /balanceforecast. Для администратора прогноз показывается в операционном помощнике при низком остатке.'); return


def handlers():
    return [
        CommandHandler('ops',operations_cmd), CommandHandler('waitlist',waitlist_cmd), CommandHandler('balanceforecast',forecast_cmd),
        CommandHandler('referral',referral_cmd), CommandHandler('claimref',claimref_cmd), CommandHandler('family',family_cmd),
        CommandHandler('history',history_cmd), CommandHandler('pause',pause_cmd), CommandHandler('absence',absence_cmd),
        CommandHandler('broadcast',broadcast_cmd), CommandHandler('schedulemsg',schedulemsg_cmd), CommandHandler('question',question_cmd), CommandHandler('notifysettings',notifysettings_cmd),
        CallbackQueryHandler(callbacks,pattern=r'^s3_')
    ]
