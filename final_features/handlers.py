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
from handlers import post_lesson_review

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
      [InlineKeyboardButton('🎓 Школа / колледж',callback_data=f'edu_profile|{uid}'),InlineKeyboardButton('📚 Направления',callback_data=f'edu_programs|{uid}')],
      [InlineKeyboardButton('⚡ Следующее действие',callback_data=f'ff_student|{uid}'),InlineKeyboardButton('📦 Продление',callback_data=f'ff_renew|{uid}')],
      [InlineKeyboardButton('🧪 Пробники',callback_data=f'ff_mocks|{uid}'),InlineKeyboardButton('📜 История',callback_data=f'ff_timeline|{uid}')],
      [InlineKeyboardButton('📈 Прогноз результата',callback_data=f'ff_performance|{uid}'),InlineKeyboardButton('🔄 Обмен окнами',callback_data=f'ff_swap|{uid}')],
      [InlineKeyboardButton('📊 Отчёт за месяц',callback_data=f'ff_report|{uid}'),InlineKeyboardButton('🎯 План экзамена',callback_data=f'ff_plan|{uid}')],
      [InlineKeyboardButton('💳 Журнал минут',callback_data=f'ff_ledger|{uid}')],
      [InlineKeyboardButton('🧭 Коммуникация и контроль',callback_data=f'crm_student|{uid}')],
      [InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'admin_student|{uid}')],
    ])

async def _show_student(q,uid):
    await q.edit_message_text(smart.card(uid),reply_markup=student_menu(uid))

def _dt_text(value):
    try:return datetime.fromisoformat(str(value)).strftime('%d.%m.%Y %H:%M')
    except Exception:return str(value)

async def _send_admin_slot_request(context, req_id):
    req=slot_change.get_request(req_id)
    if not req:return
    student=database.get_user(req['requester_student_id']);occ=database.get_user(req['occupant_student_id']) if req['occupant_student_id'] else None
    flags=[]
    if req['outside_working_hours']:flags.append('⚠️ вне рабочих часов')
    if occ:flags.append(f"🔄 слот занят: {occ['name']}")
    if not flags:flags.append('🟢 слот свободен')
    text=(f"🔄 ЗАЯВКА НА ПЕРЕНОС / ОБМЕН #{req_id}\n\nУченик: {student['name'] if student else req['requester_student_id']}\nЖелаемое время: {_dt_text(req['desired_start'])}\nДлительность: {int((datetime.fromisoformat(req['desired_end'])-datetime.fromisoformat(req['desired_start'])).total_seconds()/60)} мин\n"+'\n'.join(flags)+"\n\nСначала преподаватель решает, можно ли предлагать это время.")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Разрешить',callback_data=f'ff_x_admin_accept|{req_id}'),InlineKeyboardButton('❌ Отклонить',callback_data=f'ff_x_admin_decline|{req_id}')]])
    for a in admin_roles.list_admins():
        try:await context.bot.send_message(int(a['telegram_id']),text,reply_markup=kb)
        except Exception:pass

async def _notify_family(context, student_id, text):
    u=database.get_user(student_id)
    if u and u['telegram_id']:
        try:await context.bot.send_message(int(u['telegram_id']),text)
        except Exception:pass
    for p in database.get_student_parents(student_id, schedule_only=True):
        try:await context.bot.send_message(int(p['telegram_id']),text)
        except Exception:pass

async def _offer_exchange_to_occupant(context, req_id):
    req=slot_change.get_request(req_id)
    if not req or not req['occupant_student_id']:return
    occ=database.get_user(req['occupant_student_id']);original=database.get_lesson(req['requester_lesson_id'])
    if not occ or not occ['telegram_id'] or not original:return
    text=("🔄 ПРЕДЛОЖЕНИЕ ОБМЕНА ВРЕМЕНЕМ\n\n"f"Другой ученик хотел бы занять ваше время {_dt_text(req['desired_start'])}.\n\n"f"Взамен предлагается его текущее время: {_dt_text(original['start_time'])}.\n\nОбмен произойдёт только после вашего согласия и финального подтверждения преподавателя.")
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
            if event_id:await __import__('asyncio').to_thread(tutor_bot.update_google_event,event_id,user,lesson)
            else:
                new_id=await __import__('asyncio').to_thread(tutor_bot.create_google_event,user,lesson);tutor_bot.save_google_event_id(lid,new_id)
        except Exception as e:print('SLOT CHANGE GOOGLE:',repr(e))
        try:c=database.connect();c.execute('DELETE FROM lesson_reminders WHERE lesson_id=?',(lid,));c.commit();c.close()
        except Exception:pass
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
    q=update.callback_query;await q.answer();lesson_id=int(q.data.split('|')[1]);lesson=database.get_lesson(lesson_id)
    if not lesson:return ConversationHandler.END
    uid=q.from_user.id;student=database.get_user_by_telegram_id(uid)
    if not _admin(uid) and (not student or int(student['id'])!=int(lesson['user_id'])):await q.answer('Это не ваше занятие.',show_alert=True);return ConversationHandler.END
    context.user_data['ff_custom_slot']={'lesson_id':lesson_id,'student_id':int(lesson['user_id'])}
    await q.edit_message_text('✍️ ПРЕДЛОЖИТЬ СВОЁ ВРЕМЯ\n\nСвободные слоты не подошли? Отправьте желаемые дату и время одним сообщением.\n\nНапример: 25.08.2026 18:30\n\nМожно предложить даже время вне рабочих часов. Преподаватель отдельно решит, готов ли провести занятие. Если слот занят другим учеником, после разрешения преподавателя ему будет предложен обмен.');return CUSTOM_RESCHEDULE

async def custom_reschedule_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    st=context.user_data.get('ff_custom_slot')
    if not st:return ConversationHandler.END
    try:
        import bot as tutor_bot
        start=slot_change.parse_user_datetime(update.message.text,tutor_bot.TIMEZONE)
        if start<=datetime.now(tutor_bot.TIMEZONE):raise ValueError('Нужно выбрать будущее время.')
        lesson=database.get_lesson(st['lesson_id']);duration=int(lesson['duration_minutes'] or 60);end=start+__import__('datetime').timedelta(minutes=duration);rid=slot_change.create_request(st['student_id'],st['lesson_id'],start,end,update.effective_user.id);await _send_admin_slot_request(context,rid);req=slot_change.get_request(rid);extra='\n⚠️ Время вне стандартных рабочих часов — преподаватель решит отдельно.' if req['outside_working_hours'] else ''
        if req['occupant_lesson_id']:extra+='\n🔄 В это время уже есть ученик. Возможный обмен будет предложен только после разрешения преподавателя.'
        await update.message.reply_text(f'✅ Готово, я отправила заявку #{rid} преподавателю.{extra}');context.user_data.pop('ff_custom_slot',None);return ConversationHandler.END
    except Exception as e:await update.message.reply_text(f'❌ {e}\n\nПример: 25.08.2026 18:30');return CUSTOM_RESCHEDULE

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('ff_'):return
    d=q.data
    if d=='ff_my_mocks':
        u=database.get_user_by_telegram_id(q.from_user.id)
        if not u:await q.answer('Профиль ученика не найден.',show_alert=True);return
        await q.answer();rows=mock_tests.list_for_user(u['id']);text='🧪 МОИ ПРОБНИКИ\n\n'+('\n\n'.join(f"#{r['id']} {r['title']} • {r['status']}\nДедлайн: {r['deadline'] or '—'}\nРезультат: {r['test_score'] if r['test_score'] is not None else '—'}" for r in rows) if rows else 'Пока нет назначенных пробников.');await q.edit_message_text(text[:3900],reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Главное меню',callback_data='main')]]));return
    if d.startswith('ff_x_occupant_accept|') or d.startswith('ff_x_occupant_decline|'):
        req_id=int(d.split('|')[1]);req=slot_change.get_request(req_id)
        if not req or req['status']!='WAITING_OCCUPANT':await q.answer('Предложение уже не актуально.',show_alert=True);return
        occ=database.get_user(req['occupant_student_id']) if req['occupant_student_id'] else None
        if not occ or int(occ['telegram_id'] or 0)!=int(q.from_user.id):await q.answer('Это предложение не для вас.',show_alert=True);return
        await q.answer()
        if d.startswith('ff_x_occupant_decline|'):
            slot_change.set_status(req_id,'DECLINED',occupant_response='DECLINED');await q.edit_message_text('❌ Вы отказались от обмена. Расписание не изменено.');requester=database.get_user(req['requester_student_id'])
            if requester and requester['telegram_id']:
                try:await context.bot.send_message(int(requester['telegram_id']),'ℹ️ Второму ученику предложенный обмен не подошёл. Я оставила ваше текущее занятие без изменений.')
                except Exception:pass
            return
        slot_change.set_status(req_id,'WAITING_FINAL_ADMIN',occupant_response='ACCEPTED');await q.edit_message_text('✅ Вы согласились на обмен. Теперь преподаватель должен подтвердить его окончательно.');text=f"🔄 ОБМЕН СОГЛАСОВАН УЧЕНИКОМ #{req_id}\n\nОба слота готовы к обмену. Подтвердить окончательно?";kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Подтвердить обмен',callback_data=f'ff_x_admin_final|{req_id}'),InlineKeyboardButton('❌ Отменить',callback_data=f'ff_x_admin_decline|{req_id}')]])
        for a in admin_roles.list_admins():
            try:await context.bot.send_message(int(a['telegram_id']),text,reply_markup=kb)
            except Exception:pass
        return
    if not _admin(q.from_user.id):await q.answer('Нет доступа',show_alert=True);return
    await q.answer()
    if d=='ff_main':await q.edit_message_text('🚀 ФИНАЛЬНЫЙ ЦЕНТР УПРАВЛЕНИЯ',reply_markup=main_menu());return
    if d=='ff_swap_admin':
        c=database.connect();users=c.execute("SELECT id,name FROM users WHERE active=1 ORDER BY name COLLATE NOCASE LIMIT 80").fetchall();c.close();kb=[[InlineKeyboardButton(u['name'],callback_data=f"ff_swap|{u['id']}")] for u in users];kb.append([InlineKeyboardButton('⬅️ Назад',callback_data='ff_main')]);await q.edit_message_text('🔄 ПЕРЕНОС / ОБМЕН\n\nВыберите ученика:',reply_markup=InlineKeyboardMarkup(kb));return
    if d.startswith('ff_x_admin_decline|'):
        rid=int(d.split('|')[1]);req=slot_change.get_request(rid)
        if not req:await q.answer('Запрос не найден.',show_alert=True);return
        slot_change.set_status(rid,'DECLINED',admin_final_by=q.from_user.id);await q.edit_message_text(f'❌ Заявка #{rid} отклонена. Расписание не изменено.');await _notify_family(context,req['requester_student_id'],'❌ Преподаватель не подтвердил предложенный перенос/обмен. Я оставила текущее занятие без изменений.');return
    if d.startswith('ff_x_admin_accept|'):
        rid=int(d.split('|')[1]);req=slot_change.get_request(rid)
        if not req or req['status']!='PENDING_ADMIN':await q.answer('Заявка уже обработана.',show_alert=True);return
        if req['occupant_lesson_id']:slot_change.set_status(rid,'WAITING_OCCUPANT',admin_preapproved_by=q.from_user.id);await _offer_exchange_to_occupant(context,rid);await q.edit_message_text(f'✅ Обмен #{rid} разрешён. Второму ученику отправлено предложение. После его согласия потребуется ваше финальное подтверждение.')
        else:
            try:await _apply_slot_request(context,rid);slot_change.set_status(rid,'APPLIED',admin_preapproved_by=q.from_user.id,admin_final_by=q.from_user.id);await q.edit_message_text(f'✅ Перенос #{rid} подтверждён и применён.')
            except Exception as e:await q.edit_message_text(f'❌ Не удалось применить перенос: {e}')
        return
    if d.startswith('ff_x_admin_final|'):
        rid=int(d.split('|')[1]);req=slot_change.get_request(rid)
        if not req or req['status']!='WAITING_FINAL_ADMIN':await q.answer('Обмен не готов к финальному подтверждению.',show_alert=True);return
        try:await _apply_slot_request(context,rid);slot_change.set_status(rid,'APPLIED',admin_final_by=q.from_user.id);await q.edit_message_text(f'✅ Обмен #{rid} выполнен. Оба ученика и родители уведомлены, Calendar и напоминания обновлены.')
        except Exception as e:await q.edit_message_text(f'❌ Не удалось выполнить обмен: {e}')
        return
    if d.startswith('ff_swap_lesson|'):
        lid=int(d.split('|')[1]);lesson=database.get_lesson(lid)
        if not lesson:await q.answer('Занятие не найдено.',show_alert=True);return
        import bot as tutor_bot
        duration=int(lesson['duration_minutes'] or 60);today=datetime.now(tutor_bot.TIMEZONE).date();kb=[]
        for i in range(14):
            day=today+__import__('datetime').timedelta(days=i)
            try:slots=await __import__('asyncio').to_thread(tutor_bot.get_free_slots,day,duration,lid)
            except Exception:slots=[]
            if slots:kb.append([InlineKeyboardButton(f"📅 {day.strftime('%d.%m')} • свободно {len(slots)}",callback_data=f"ff_swap_day|{lid}|{day.isoformat()}")])
        kb.append([InlineKeyboardButton('✍️ Предложить своё время',callback_data=f'ff_custom_reschedule|{lid}')]);kb.append([InlineKeyboardButton('⬅️ Назад',callback_data=f"ff_swap|{lesson['user_id']}")]);await q.edit_message_text(f"🔄 Перенос занятия\nТекущее время: {_dt_text(lesson['start_time'])}\n\nСначала выберите одно из свободных окон. Если ничего не подходит — предложите своё время.",reply_markup=InlineKeyboardMarkup(kb));return
    if d.startswith('ff_swap_day|'):
        _,lid_s,day_s=d.split('|',2);lid=int(lid_s);lesson=database.get_lesson(lid)
        if not lesson:return
        import bot as tutor_bot
        day=__import__('datetime').date.fromisoformat(day_s);duration=int(lesson['duration_minutes'] or 60);slots=await __import__('asyncio').to_thread(tutor_bot.get_free_slots,day,duration,lid);kb=[];row=[]
        for dt in slots:
            row.append(InlineKeyboardButton(dt.strftime('%H:%M'),callback_data=f"ff_swap_free|{lid}|{dt.isoformat()}"))
            if len(row)==3:kb.append(row);row=[]
        if row:kb.append(row)
        kb.append([InlineKeyboardButton('✍️ Предложить другое время',callback_data=f'ff_custom_reschedule|{lid}')]);kb.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'ff_swap_lesson|{lid}')]);await q.edit_message_text(f"📅 {day.strftime('%d.%m.%Y')}\n\nСвободные окна:",reply_markup=InlineKeyboardMarkup(kb));return
    if d.startswith('ff_swap_free|'):
        _,lid_s,start_s=d.split('|',2);lid=int(lid_s);lesson=database.get_lesson(lid)
        if not lesson:return
        start=datetime.fromisoformat(start_s);duration=int(lesson['duration_minutes'] or 60);end=start+__import__('datetime').timedelta(minutes=duration)
        try:new_id=database.free_reschedule_lesson(lid,start.isoformat(),end.isoformat());await _refresh_calendar_and_reminders(context,[new_id]);new_lesson=database.get_lesson(new_id);await _notify_family(context,lesson['user_id'],f"✅ Готово, я перенесла занятие. Новое время: {_dt_text(new_lesson['start_time'])}.");await q.edit_message_text(f"✅ Перенос выполнен\n\nНовое время: {_dt_text(new_lesson['start_time'])}",reply_markup=student_menu(lesson['user_id']))
        except Exception as e:await q.edit_message_text(f'❌ {e}',reply_markup=student_menu(lesson['user_id']))
        return
    if d.startswith('ff_student|'):await _show_student(q,int(d.split('|')[1]));return
    if d=='ff_business':
        x=business.dashboard();f=x['finance'];text=(f"🧭 КОНТРОЛЬ БИЗНЕСА\n\n👥 Активных: {x['students']}\n📅 На 7 дней: {x['lessons7']} занятий / {round((x['minutes7'] or 0)/60,1)} ч\n💳 Оплат ждут: {x['pending_payments']}\n⚠️ Аномалий: {len(x['issues'])}\n\n💰 Заработано: {f['earned']} ₽\n📦 Предоплачено: {f['prepaid']} ₽\n📈 Прогноз месяца: {f['projected_earned']} ₽");await q.edit_message_text(text,reply_markup=_back());return
    if d=='ff_week':
        s,e,by,mins,plan,cap,free=week.view();names=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];lines=[f'📅 НЕДЕЛЯ {s:%d.%m}–{e:%d.%m}','']
        for i in range(7):lines.append(f"{names[i]}: {len(by[i])} зан. / {sum(int(r['duration_minutes'] or 0) for r in by[i])} мин")
        lines+=['',f'⏱ Занято: {mins} мин',f'🟢 Свободно по рабочим часам: {free} мин',f'💰 Плановый заработок: {plan} ₽'];await q.edit_message_text('\n'.join(lines),reply_markup=_back());return
    if d=='ff_finforecast':
        f=forecast.finance();text=f"💰 ФИНАНСОВЫЙ ПРОГНОЗ\n\n💳 Получено: {f['received']} ₽\n💰 Уже заработано: {f['earned']} ₽\n📅 Будущие занятия до конца месяца: {f['future_earned']} ₽ / {f['future_minutes']} мин\n📈 Прогноз заработка: {f['projected_earned']} ₽\n📦 Предоплачено: {f['prepaid']} ₽";await q.edit_message_text(text,reply_markup=_back());return
    if d=='ff_tariffs':
        rows=tariffs.list_rules();groups={}
        for r in rows:groups.setdefault((r['study_goal'],r['base_duration_minutes']),[]).append(r)
        lines=['⚙️ ТАРИФЫ И СКИДКИ','','Цена за 60 минут берётся из действующего прайса/индивидуальной цены.']
        for (goal,base),rs in groups.items():lines.append(f"\n{goal} • база {base} мин: "+', '.join(f"{x['equivalent_lessons']} зан. = {x['equivalent_lessons']*base} мин ({x['discount_percent']}%)" for x in rs))
        await q.edit_message_text('\n'.join(lines)[:3900],reply_markup=_back());return
    if d=='ff_reconcile':
        issues=reconcile.run();lines=['🔍 СВЕРКА ДЕНЬГИ ↔ МИНУТЫ ↔ ЗАНЯТИЯ',''];lines += [f"{'🔴' if s=='CRITICAL' else '🟠' if s=='ATTENTION' else '🔵'} {code}: {det}" for s,code,det,uid in issues[:40]] or ['✅ Расхождений не найдено.'];await q.edit_message_text('\n'.join(lines)[:3900],reply_markup=_back());return
    if d=='ff_recovery':
        h=recovery.health();text='🚑 RECOVERY\n\n'+'\n'.join(('✅' if ok else '🔴')+f' {n}: {det}' for n,ok,det in h)+'\n\nПеред обновлением используйте safe_update/backup. Восстановление выполняет только владелец.';await q.edit_message_text(text,reply_markup=_back());return
    if d=='ff_renewals':
        c=database.connect();users=c.execute('SELECT id,name FROM users WHERE active=1 ORDER BY name').fetchall();c.close();lines=['📦 ПРОДЛЕНИЯ МИНУТ','']
        for u in users:
            ps=database.get_student_programs(u['id'],active_only=True,approved_only=True)
            for p in ps:
                try:
                    rec=renewals.recommendation(u['id'],p['id'])
                    if rec['available_after_bookings']<=180:qte=rec['quote'];lines.append(f"⚠️ {u['name']} • {p['study_goal']} {p['subject']}: {rec['balance']} мин, после броней {rec['available_after_bookings']} мин → {qte['minutes']} мин / {qte['total']} ₽")
                except Exception:pass
        await q.edit_message_text('\n'.join(lines)[:3900] if len(lines)>2 else '📦 Продления\n\nСрочных продлений нет.',reply_markup=_back());return
    if d.startswith('ff_renew|'):
        uid=int(d.split('|')[1]);ps=database.get_student_programs(uid,active_only=True,approved_only=True);lines=['📦 РЕКОМЕНДАЦИЯ ПО ПРОДЛЕНИЮ','']
        for p in ps:r=renewals.recommendation(uid,p['id']);qte=r['quote'];lines.append(f"{p['study_goal']} {p['subject']}: баланс {r['balance']} мин; резерв {r['reserved']} мин; рекомендовано {qte['equivalent_lessons']} зан. = {qte['minutes']} мин за {qte['total']} ₽ ({qte['discount_percent']}%)")
        await q.edit_message_text('\n\n'.join(lines),reply_markup=student_menu(uid));return
    if d.startswith('ff_report|'):
        uid=int(d.split('|')[1]);text=reports.build(uid);reports.save(uid,text,actor=q.from_user.id);await q.edit_message_text(text,reply_markup=student_menu(uid));return
    if d.startswith('ff_timeline|'):
        uid=int(d.split('|')[1]);student_history.rebuild_basic(uid);rows=student_history.recent(uid,30);text='📜 ИСТОРИЯ УЧЕНИКА\n\n'+('\n\n'.join(f"{r['created_at'][:16]} • {r['title']}\n{r['details'] or ''}" for r in rows) if rows else 'История пока пуста.');await q.edit_message_text(text[:3900],reply_markup=student_menu(uid));return
    if d.startswith('ff_ledger|'):
        uid=int(d.split('|')[1]);rows=ledger.history(uid,40);text='💳 ЖУРНАЛ МИНУТ\n\n'+('\n'.join(f"{r['created_at'][5:16]} • {r['operation']} • paid {r['paid_minutes_delta']:+d} / bonus {r['bonus_minutes_delta']:+d} мин • {r['reason'] or ''}" for r in rows) if rows else 'Журнал пока пуст.');await q.edit_message_text(text[:3900],reply_markup=student_menu(uid));return
    if d.startswith('ff_performance|'):
        uid=int(d.split('|')[1]);pr=performance.projection(uid);text='📈 ДИНАМИКА И ПРОГНОЗ\n\n';text += 'Пока нет результатов пробников.' if pr['current'] is None else f"Пробников: {pr['tests']}\nТекущий результат: {pr['current']}\nИзменение от первого: {pr['change']:+}\nОсторожный краткосрочный прогноз: {pr['forecast_low']}–{pr['forecast_high']}\n\nЭто ориентир по недавней динамике, а не гарантия результата.";await q.edit_message_text(text,reply_markup=student_menu(uid));return
    if d.startswith('ff_swap|'):
        uid=int(d.split('|')[1]);c=database.connect();rows=c.execute("SELECT id,start_time,duration_minutes,subject,study_goal FROM lessons WHERE user_id=? AND lesson_status='CONFIRMED' AND start_time>? ORDER BY start_time LIMIT 20",(uid,datetime.now().isoformat())).fetchall();c.close();reqs=slot_change.requests_for_student(uid);lines=['🔄 ПЕРЕНОС / ОБМЕН','','Выберите занятие, которое ученик хочет перенести. Сначала будут предложены свободные окна.']
        if reqs:lines+=['','Активные заявки:']+[f"#{r['id']} • {_dt_text(r['desired_start'])} • {r['status']}" for r in reqs[:8]]
        kb=[[InlineKeyboardButton(f"{_dt_text(r['start_time'])} • {r['subject'] or r['study_goal'] or 'занятие'}",callback_data=f"ff_swap_lesson|{r['id']}")] for r in rows];kb.append([InlineKeyboardButton('⬅️ К ученику',callback_data=f'ff_student|{uid}')]);await q.edit_message_text('\n'.join(lines)[:3900],reply_markup=InlineKeyboardMarkup(kb));return
    if d.startswith('ff_mocks|'):
        uid=int(d.split('|')[1]);rows=mock_tests.list_for_user(uid);text='🧪 ПРОБНИКИ\n\n'+('\n\n'.join(f"#{r['id']} {r['title']} • {r['status']}\nДедлайн: {r['deadline'] or '—'}\nРезультат: {r['test_score'] if r['test_score'] is not None else '—'}" for r in rows) if rows else 'Пробников пока нет.');await q.edit_message_text(text[:3900],reply_markup=student_menu(uid));return
    if d=='ff_mocks_admin':await q.edit_message_text('🧪 ПРОБНИКИ\n\nВыберите ученика и работайте с пробниками через пошаговое меню.',reply_markup=_back());return
    if d.startswith('ff_plan|'):
        uid=int(d.split('|')[1]);await q.edit_message_text('🎯 ПЛАН ЭКЗАМЕНА\n\nНастройка выполняется через пошаговое меню: направление → дата экзамена → цель → нагрузка.',reply_markup=student_menu(uid));return

async def mockassign_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<4:return
    uid,pid=int(context.args[0]),int(context.args[1]);deadline=context.args[2];title=' '.join(context.args[3:]);mid=mock_tests.assign(uid,pid,title,deadline=deadline,actor=update.effective_user.id);u=database.get_user(uid)
    if u and u['telegram_id']:
        try:await context.bot.send_message(int(u['telegram_id']),f'🧪 Вам назначен пробник\n\n{title}\nДедлайн: {deadline}\n\nОткройте «🧪 Пробники» в главном меню.')
        except Exception:pass
    await update.message.reply_text(f'✅ Пробник #{mid} назначен и уведомление отправлено ученику.')

async def mocks_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=None
    if _admin(update.effective_user.id) and context.args:uid=int(context.args[0])
    else:u=database.get_user_by_telegram_id(update.effective_user.id);uid=u['id'] if u else None
    if not uid:return
    rows=mock_tests.list_for_user(uid);await update.message.reply_text('🧪 ПРОБНИКИ\n\n'+('\n\n'.join(f"#{r['id']} {r['title']} • {r['status']} • дедлайн {r['deadline'] or '—'} • {r['test_score'] if r['test_score'] is not None else 'без результата'}" for r in rows) if rows else 'Пока нет назначенных пробников.'))

async def mockresult_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<2:return
    mid=int(context.args[0]);test=float(context.args[1]);primary=float(context.args[2]) if len(context.args)>2 else None;mins=int(context.args[3]) if len(context.args)>3 else None;mock_tests.complete(mid,primary,test,mins);await update.message.reply_text('✅ Результат пробника сохранён и добавлен в динамику.')

async def examplan_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<5:return
    uid,pid=int(context.args[0]),int(context.args[1]);summary=exam_plans.generate(uid,pid,context.args[2],float(context.args[3]),int(context.args[4]));await update.message.reply_text(summary)

async def week_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):return
    s,e,by,mins,plan,cap,free=week.view();await update.message.reply_text(f'📅 Неделя {s:%d.%m}–{e:%d.%m}\nЗанято {mins} мин, свободно {free} мин, плановый заработок {plan} ₽.')

async def lessonreview_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or not context.args:return
    lid=int(context.args[0]);c=database.connect();l=c.execute('SELECT user_id FROM lessons WHERE id=?',(lid,)).fetchone();c.close()
    if not l:return
    await update.message.reply_text('Начать опрос по занятию:',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧠 Начать',callback_data=f"ff_review_start|{lid}|{l['user_id']}")]]))

async def swaprequest_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<6:return
    uid=int(context.args[0]);lid=int(context.args[1]);rid=reschedule.request(uid,lid,context.args[2],context.args[3],context.args[4],int(context.args[5]));matches=reschedule.candidates(rid);await update.message.reply_text(f'✅ Запрос обмена #{rid} создан. Совпадений: {len(matches)}.')

async def discount_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id) or len(context.args)<4:return
    goal=context.args[0].upper();base=int(context.args[1]);count=int(context.args[2]);pct=int(context.args[3]);schema.initialize();c=database.connect();now=datetime.now().isoformat(timespec='seconds');c.execute('''INSERT INTO tariff_discount_rules(study_goal,subject,base_duration_minutes,equivalent_lessons,discount_percent,active,created_at,updated_at) VALUES(?,'',?,?,?,1,?,?) ON CONFLICT(study_goal,subject,base_duration_minutes,equivalent_lessons) DO UPDATE SET discount_percent=excluded.discount_percent,active=1,updated_at=excluded.updated_at''',(goal,base,count,pct,now,now));c.commit();c.close();await update.message.reply_text(f'✅ {goal}: {count} занятий × {base} мин = {count*base} мин, скидка {pct}%.')

def handlers():
    slot_conv=ConversationHandler(entry_points=[CallbackQueryHandler(custom_reschedule_entry,pattern=r'^ff_custom_reschedule\|')],states={CUSTOM_RESCHEDULE:[MessageHandler(filters.TEXT & ~filters.COMMAND,custom_reschedule_message)]},fallbacks=[],allow_reentry=True)
    return friendly_ui.handlers()+[CommandHandler('final',command),CommandHandler('student360',student360_cmd),CommandHandler('mockassign',mockassign_cmd),CommandHandler('mocks',mocks_cmd),CommandHandler('mockresult',mockresult_cmd),CommandHandler('examplan',examplan_cmd),CommandHandler('week',week_cmd),CommandHandler('lessonreview',lessonreview_cmd),CommandHandler('swaprequest',swaprequest_cmd),CommandHandler('discount',discount_cmd),post_lesson_review.handler(),slot_conv,CallbackQueryHandler(callbacks,pattern=r'^ff_')]
