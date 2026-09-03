from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles, audit_log, financial_ledger, minute_balance


def _program_name(program):
    goals={"EGE":"ЕГЭ","OGE":"ОГЭ","OLYMPIAD":"Олимпиада","SCHOOL":"Школьная программа"}
    subjects={"PHYSICS":"Физика","CHEMISTRY":"Химия"}
    return f"{goals.get(program['study_goal'],program['study_goal'])} • {subjects.get(program['subject'],program['subject'])}"


async def _show_duration_programs(q, user_id):
    user=database.get_user(int(user_id))
    programs=database.get_student_programs(int(user_id),active_only=True,approved_only=True)
    text=f"⏱ <b>ОСНОВНОЕ ВРЕМЯ ЗАНЯТИЯ</b>\n\n👤 {user['name'] if user else user_id}\n\nВыберите направление:"
    kb=[]
    for p in programs:
        duration=minute_balance.get_program_duration(p['id'])
        kb.append([InlineKeyboardButton(f"{_program_name(p)} • {duration} мин",callback_data=f"min_duration_program|{user_id}|{p['id']}")])
    kb.append([InlineKeyboardButton("⬅️ Ученик",callback_data=f"admin_student|{user_id}")])
    await q.edit_message_text(text,parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))


async def _show_duration_options(q, user_id, program_id):
    p=database.get_student_program(int(program_id))
    if not p or int(p['user_id'])!=int(user_id):
        await q.answer('Направление не найдено.',show_alert=True); return
    current=minute_balance.get_program_duration(program_id)
    values=[60,75,90,105,120,150,180]
    if current not in values: values.append(current); values.sort()
    kb=[]; row=[]
    for m in values:
        row.append(InlineKeyboardButton(("✅ " if m==current else "")+f"{m} мин",callback_data=f"min_duration_set|{user_id}|{program_id}|{m}"))
        if len(row)==3: kb.append(row); row=[]
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("⬅️ К направлениям",callback_data=f"min_duration_user|{user_id}")])
    await q.edit_message_text(
        f"⏱ <b>{_program_name(p)}</b>\n\nТекущее основное время: <b>{current} минут</b>.\n\n"
        "Ученик сможет выбрать это время или больше. Меньше основного времени выбрать нельзя.",
        parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))


async def _show_balance(q,user_id):
    user=database.get_user(int(user_id))
    programs=database.get_student_programs(int(user_id),active_only=True,approved_only=True)
    by_rate=minute_balance.get_balance_by_rate(int(user_id))
    lines=["🎟 <b>БАЛАНС В МИНУТАХ</b>","",f"👤 {user['name'] if user else user_id}",""]
    if not by_rate:
        lines.append('Баланс пуст.')
    else:
        for rate,item in by_rate.items():
            if rate==0:
                lines.append(f"🎁 Бонусная копилка: <b>{item['bonus']} мин</b>")
            else:
                lines.append(f"💰 {rate:,} ₽ / 60 мин: <b>{item['paid']} мин</b>".replace(',',' '))
        bonus=sum(x['bonus'] for x in by_rate.values())
        if bonus and 0 not in by_rate:
            lines.append(f"🎁 Бонусная копилка: <b>{bonus} мин</b>")
    kb=[]
    for p in programs:
        d=minute_balance.get_program_duration(p['id']); r=minute_balance.effective_hourly_rate(p['id'])
        kb.append([InlineKeyboardButton(f"➕ {d} мин • {_program_name(p)}",callback_data=f"min_balance_add|{user_id}|{p['id']}|{d}")])
        kb.append([InlineKeyboardButton(f"➖ {d} мин • {_program_name(p)}",callback_data=f"min_balance_remove|{user_id}|{p['id']}|{d}")])
    kb.append([InlineKeyboardButton("⬅️ Ученик",callback_data=f"admin_student|{user_id}")])
    await q.edit_message_text('\n'.join(lines),parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))


async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('min_'): return
    if not admin_roles.is_admin_id(q.from_user.id):
        await q.answer('Только для администратора.',show_alert=True); return
    await q.answer(); data=q.data
    if data.startswith('min_duration_user|'):
        await _show_duration_programs(q,int(data.split('|')[1])); return
    if data.startswith('min_duration_program|'):
        _,uid,pid=data.split('|'); await _show_duration_options(q,int(uid),int(pid)); return
    if data.startswith('min_duration_set|'):
        _,uid,pid,m=data.split('|'); minute_balance.set_program_duration(int(pid),int(m)); audit_log.log('PROGRAM_DURATION_SET',q.from_user.id,'program',int(pid),{'minutes':int(m),'user_id':int(uid)}); await _show_duration_options(q,int(uid),int(pid)); return
    if data.startswith('min_balance|'):
        await _show_balance(q,int(data.split('|')[1])); return
    if data.startswith('min_balance_add|') or data.startswith('min_balance_remove|'):
        parts=data.split('|'); uid,pid,mins=map(int,parts[1:]); delta=mins if data.startswith('min_balance_add|') else -mins
        try:
            result=minute_balance.admin_adjust_minutes(uid,pid,delta)
        except Exception as e:
            await q.answer(str(e),show_alert=True); return
        rate=minute_balance.effective_hourly_rate(pid)
        # Keep the immutable legacy ledger meaningful: one entry carries minute metadata in description.
        financial_ledger.append(uid,lessons_delta=0,nominal=rate,entry_type='ADMIN_MINUTES_ADD' if delta>0 else 'ADMIN_MINUTES_REMOVE',source_type='minute_adjustment',source_id=None,description=f"Ручная корректировка {delta:+d} минут",actor_id=q.from_user.id)
        audit_log.log('MINUTE_BALANCE_ADJUST',q.from_user.id,'user',uid,{'program_id':pid,'minutes_delta':delta,'rate':rate})
        await q.answer(f"Баланс изменён на {delta:+d} минут.")
        await _show_balance(q,uid); return


def handlers():
    return [CallbackQueryHandler(callbacks,pattern=r'^min_')]
