from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes
import database
from learning import formula_study

DONE={'DONE','APPROVED','REVIEWED'}
ACTIVE={'ASSIGNED','UNDER_REVIEW','REVISION'}

def _student(tid): return database.get_user_by_telegram_id(tid)
def _parent(tid): return database.get_parent_by_telegram_id(tid)
def _bar(done,total=10):
    done=max(0,min(total,int(done))); return '█'*done+'░'*(total-done)
def _hw_stats(uid):
    rows=database.get_student_homework(uid,False); total=len(rows); done=sum(1 for r in rows if str(r['status']).upper() in DONE); active=sum(1 for r in rows if str(r['status']).upper() in ACTIVE); revision=sum(1 for r in rows if str(r['status']).upper()=='REVISION')
    return rows,total,done,active,revision

def _lessons(uid):
    c=database.connect(); rows=c.execute("SELECT * FROM lessons WHERE user_id=? ORDER BY start_time DESC",(uid,)).fetchall(); c.close(); return rows

def _parent_pick(parent, prefix):
    sts=database.get_parent_students(parent['id'])
    return InlineKeyboardMarkup([[InlineKeyboardButton(s['name'],callback_data=f'{prefix}|{s["id"]}')] for s in sts]+[[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])

async def cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; d=q.data or ''
    if not d.startswith(('uxs3_','uxp3_')): return
    await q.answer(); tid=q.from_user.id
    if d=='uxs3_study':
        u=_student(tid)
        if not u:return
        rows,total,done,active,revision=_hw_stats(u['id']); lessons=_lessons(u['id']); held=sum(1 for x in lessons if str(x['lesson_status']).upper() in {'DONE','COMPLETED','HELD'})
        pct=round(done*100/total) if total else 0
        text=f"📚 <b>МОЯ УЧЁБА</b>\n\n{u['main_subject'] or 'Учёба'} • {u['grade'] or 'класс не указан'}\n\n📈 ДЗ выполнено: <b>{done} из {total}</b> ({pct}%)\n{_bar(round(pct/10))}\n🎓 Проведено занятий: {held}\n📝 Сейчас активно: {active}"
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('📝 Мои ДЗ',callback_data='homework'),InlineKeyboardButton('🧮 Формулы',callback_data='fh_home')],[InlineKeyboardButton('💡 Что повторить',callback_data='uxs3_repeat'),InlineKeyboardButton('📤 Мои решения',callback_data='uxs3_solutions')],[InlineKeyboardButton('🕘 Недавнее',callback_data='fh_recent')],[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await q.edit_message_text(text,parse_mode='HTML',reply_markup=kb); return
    if d=='uxs3_repeat':
        u=_student(tid); rows,total,done,active,revision=_hw_stats(u['id'])
        items=[r for r in rows if str(r['status']).upper() in {'REVISION','ASSIGNED'}][:6]
        lines=['💡 <b>ЧТО ПОВТОРИТЬ</b>','', 'Я собрала это без ИИ — по твоим текущим и возвращённым ДЗ.','']
        if items:
            for r in items: lines.append(f"• {r['title'] or r['description'] or 'Домашнее задание'}"[:180])
        else: lines.append('Сейчас нет тем, которые требуют обязательного повторения 👍')
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🧮 Открыть формулы',callback_data='fh_home'),InlineKeyboardButton('📝 Домашка',callback_data='homework')],[InlineKeyboardButton('⬅️ Моя учёба',callback_data='uxs3_study'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await q.edit_message_text('\n'.join(lines),parse_mode='HTML',reply_markup=kb); return
    if d=='uxs3_solutions':
        u=_student(tid); rows,total,done,active,revision=_hw_stats(u['id']); under=sum(1 for r in rows if str(r['status']).upper()=='UNDER_REVIEW')
        text=f"📤 <b>МОИ РЕШЕНИЯ</b>\n\n🟡 На проверке: {under}\n🔴 Нужно исправить: {revision}\n✅ Проверено: {done}\n\nЗдесь статус берётся из реальных домашних заданий."
        await q.edit_message_text(text,parse_mode='HTML',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📝 Открыть домашку',callback_data='homework')],[InlineKeyboardButton('⬅️ Моя учёба',callback_data='uxs3_study'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return
    p=_parent(tid)
    if not p:return
    if d in {'uxp3_summary','uxp3_report','uxp3_attention','uxp3_homework'}:
        sts=database.get_parent_students(p['id'])
        if len(sts)!=1:
            prefix={'uxp3_summary':'uxp3_summary_s','uxp3_report':'uxp3_report_s','uxp3_attention':'uxp3_attention_s','uxp3_homework':'uxp3_homework_s'}[d]
            await q.edit_message_text('👨‍👩‍👧 Выберите ученика:',reply_markup=_parent_pick(p,prefix)); return
        d=d+'_s|'+str(sts[0]['id'])
    if '|' in d:
        kind,sid=d.split('|',1)
        if not sid.isdigit():return
        sid=int(sid); allowed={x['id'] for x in database.get_parent_students(p['id'])}
        if sid not in allowed:return
        u=database.get_user(sid); rows,total,done,active,revision=_hw_stats(sid); lessons=_lessons(sid); held=sum(1 for x in lessons if str(x['lesson_status']).upper() in {'DONE','COMPLETED','HELD'}); pct=round(done*100/total) if total else 0
        if kind=='uxp3_summary_s':
            text=f"📊 <b>{u['name']} • УЧЁБА</b>\n\n🎓 {u['grade'] or ''}\n📚 Занятий проведено: {held}\n📝 ДЗ выполнено: {done}/{total} ({pct}%)\n🟡 Активных ДЗ: {active}\n🔴 На исправлении: {revision}"
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('📝 Домашние задания',callback_data=f'uxp3_homework_s|{sid}'),InlineKeyboardButton('📄 Отчёт',callback_data=f'uxp3_report_s|{sid}')],[InlineKeyboardButton('🔔 Что требует внимания',callback_data=f'uxp3_attention_s|{sid}')],[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        elif kind=='uxp3_report_s':
            text=f"📄 <b>ОТЧЁТ ЗА ПЕРИОД</b>\n\n👤 {u['name']}\n📚 Проведено занятий: {held}\n📝 ДЗ: {done} выполнено из {total}\n📈 Выполнение ДЗ: {pct}%\n🔴 Требует исправления: {revision}\n\nОтчёт сформирован по данным TutorBot без ИИ."
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('📊 К прогрессу',callback_data=f'uxp3_summary_s|{sid}')],[InlineKeyboardButton('⬅️ Назад',callback_data='global_home'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        elif kind=='uxp3_attention_s':
            issues=[]
            if revision: issues.append(f'🔴 ДЗ на исправлении: {revision}')
            if active: issues.append(f'🟡 Активных ДЗ: {active}')
            text=f"🔔 <b>ЧТО ТРЕБУЕТ ВНИМАНИЯ</b>\n\n👤 {u['name']}\n\n"+('\n'.join(issues) if issues else '🟢 Сейчас критичных учебных моментов нет.')
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('📝 Посмотреть ДЗ',callback_data=f'uxp3_homework_s|{sid}')],[InlineKeyboardButton('⬅️ Назад',callback_data=f'uxp3_summary_s|{sid}'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        else:
            shown=rows[:8]; lines=[f"📝 <b>ДЗ • {u['name']}</b>",'']
            for r in shown: lines.append(f"• {r['title'] or r['description'] or 'Домашнее задание'} — {r['status']}"[:200])
            if not shown: lines.append('Домашних заданий пока нет.')
            lines += ['','🧮 Если к ДЗ прикреплены формулы, ученик видит их прямо под заданием.']
            text='\n'.join(lines); kb=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К прогрессу',callback_data=f'uxp3_summary_s|{sid}'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])
        await q.edit_message_text(text[:3900],parse_mode='HTML',reply_markup=kb); return

def handlers(): return [CallbackQueryHandler(cb,pattern=r'^(uxs3_|uxp3_)')]
