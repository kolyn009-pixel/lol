from __future__ import annotations
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import ApplicationHandlerStop,CallbackQueryHandler,CommandHandler,ContextTypes,MessageHandler,filters
import database
from web_backend import student_onboarding,public_trial_channel,public_trial,trial_followup

def _kb(r):
 rows=[]
 status=str(r.get('status') or '').upper()
 if r.get('meeting_url') and status!='TRIAL_COMPLETED':rows.append([InlineKeyboardButton('▶️ Подключиться к занятию',url=str(r['meeting_url']))])
 if r.get('board_url'):rows.append([InlineKeyboardButton('📝 Открыть доску',url=str(r['board_url']))])
 if status=='TRIAL_COMPLETED':
  rows += [[InlineKeyboardButton('💜 Продолжить заниматься',callback_data='trial_guest|continue')],[InlineKeyboardButton('🕒 Хочу подумать',callback_data='trial_guest|thinking')],[InlineKeyboardButton('Пока не планирую',callback_data='trial_guest|stop')]]
 else:rows += [[InlineKeyboardButton('🎓 Моё пробное',callback_data='trial_guest|home')],[InlineKeyboardButton('💬 Написать преподавателю',callback_data='trial_guest|message')]]
 return InlineKeyboardMarkup(rows)
def _text(r):
 st={'NEW':'ожидает подтверждения','CONTACTED':'преподаватель увидел заявку','ACCEPTED':'подтверждено','TRIAL_COMPLETED':'пробное завершено','CONVERTED':'вы стали постоянным учеником'}.get(str(r.get('status') or '').upper(),str(r.get('status') or ''))
 start=r.get('trial_start') or r.get('selected_slot_start');x=['💜 АДЕЛИЯ • ПРОБНОЕ','',f"👤 {r.get('name') or 'Ученик'}",f"📚 {r.get('subject') or 'Занятие'}",f'Статус: {st}']
 if start:x.append(f"🕐 {str(start).replace('T',' ')[:16]}")
 if str(r.get('status') or '').upper()=='TRIAL_COMPLETED':x += ['','Как тебе формат? Выбери, что делать дальше 👇']
 else:
  x.append('🎥 Ссылка на занятие готова' if r.get('meeting_url') else '🎥 Ссылка появится после подтверждения преподавателем')
  if r.get('board_url'):x.append('📝 Доска готова')
  x += ['','До перехода в постоянный формат здесь доступно только пробное занятие.']
 return '\n'.join(x)
async def _show(update,r):
 if update.callback_query:
  await update.callback_query.answer();await update.callback_query.edit_message_text(_text(r),reply_markup=_kb(r))
 else:await update.effective_message.reply_text(_text(r),reply_markup=_kb(r))
async def start_join(update:Update,context:ContextTypes.DEFAULT_TYPE):
 u=update.effective_user;m=update.effective_message
 if not u or not m:return
 # Read the current message, never a previous handler's cached arguments.
 parts=str(m.text or '').strip().split()
 raw=parts[1] if len(parts)>1 else ''
 if raw.lower().startswith('trial_'):
  try:p=public_trial_channel.confirm(raw[6:].strip().upper(),'TELEGRAM',str(u.id),username=u.username,display_name=u.full_name);r=public_trial.get(int(p['request_id']))
  except ValueError as e:
   # A successful link consumes its token. Reopening that deep link must
   # recover only this Telegram sender's verified identity, never token data.
   if str(e) in {'trial_link_expired','trial_link_not_found','request_not_actionable'}:
    user=database.get_user_by_telegram_id(u.id)
    parent=database.get_parent_by_telegram_id(u.id)
    if (user and user['active']) or (parent and parent['active']):
     return  # Existing-role /start handlers open the permanent account.
    pending=student_onboarding.pending_for_external('TELEGRAM',str(u.id))
    if pending:
     await m.reply_text('Telegram уже подключён. Вернитесь на открытую страницу регистрации Аделии и продолжите заполнение.')
     raise ApplicationHandlerStop
    trial=public_trial_channel.pending_by_external('TELEGRAM',str(u.id))
    if trial:
     await _show(update,trial)
     raise ApplicationHandlerStop
   await m.reply_text(
    'Эту ссылку подключения больше нельзя использовать. Откройте страницу Аделии, где оформляли пробное, и создайте новую ссылку. Обычная регистрация доступна по кнопке ниже.',
    reply_markup=InlineKeyboardMarkup([
     [InlineKeyboardButton('Регистрация ученика',url='https://adeliatutor.ru/onboarding/')],
     [InlineKeyboardButton('Открыть сайт Аделии',url='https://adeliatutor.ru/')],
    ]),
   )
   raise ApplicationHandlerStop
  await m.reply_text('✅ Telegram подключён к пробному занятию 💜');await _show(update,r);raise ApplicationHandlerStop
 token=''
 if raw.lower().startswith('join_'):token=raw[5:].strip().upper()
 else:
  try:pending=student_onboarding.pending_for_external('TELEGRAM',str(u.id))
  except Exception:pending=None
  if pending:token=str(pending['token'])
  else:
   try:trial=public_trial_channel.pending_by_external('TELEGRAM',str(u.id))
   except Exception:trial=None
   if trial:await _show(update,trial);raise ApplicationHandlerStop
   return
 try:p=student_onboarding.confirm_channel(token,'TELEGRAM',str(u.id),username=u.username,display_name=u.full_name)
 except ValueError as e:
  await m.reply_text('Ссылка регистрации уже недействительна. Вернитесь на сайт Аделии и начните регистрацию заново 💜' if str(e) in {'onboarding_expired','onboarding_not_found'} else 'Не удалось подтвердить Telegram. Вернитесь на сайт и попробуйте ещё раз.');raise ApplicationHandlerStop
 name=(p.get('user') or {}).get('name') or p.get('name') or u.first_name;await m.reply_text(f'✅ Telegram подключён, {name}!\n\nВернитесь на открытую страницу регистрации Аделии — она автоматически продолжится.\n\nПока регистрация не завершена, обычное меню TutorBot открываться не будет.');raise ApplicationHandlerStop
async def trial_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
 u=update.effective_user;q=update.callback_query
 if not u or not q:return
 try:r=public_trial_channel.pending_by_external('TELEGRAM',str(u.id))
 except Exception:r=None
 if not r:return
 action=str(q.data or '').split('|',1)[-1]
 if action=='message':
  context.user_data['trial_guest_message']=int(r['id']);await q.answer();await q.edit_message_text('💬 Напишите следующим сообщением то, что хотите передать преподавателю.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Моё пробное',callback_data='trial_guest|home')]]));raise ApplicationHandlerStop
 if action in {'continue','thinking','stop'}:
  decision={'continue':'CONTINUE','thinking':'THINKING','stop':'STOP'}[action]
  try:
   trial_followup.decide(int(r['id']),decision)
   continuation=public_trial.issue_continuation_code(int(r['id'])) if decision=='CONTINUE' else None
  except ValueError as e:
   await q.answer(str(e),show_alert=True);raise ApplicationHandlerStop
  if decision=='CONTINUE':
   code=continuation['continuation_code'];await q.answer();await q.edit_message_text('💜 Отлично! Данные пробного сохранены.\n\nТеперь открой сайт Аделии и заверши создание постоянного аккаунта — имя, класс, предмет и контакт повторно вводить не придётся.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('Продолжить регистрацию →',url=f"https://adeliatutor.ru/onboarding/?trial_code={code}")]]))
  elif decision=='THINKING':
   await q.answer();await q.edit_message_text('🕒 Хорошо. Я сохраню пробное и напомню через несколько дней. Если решишь раньше — просто снова открой «Моё пробное».',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎓 Моё пробное',callback_data='trial_guest|home')]]))
  else:
   await q.answer();await q.edit_message_text('Спасибо, что попробовал формат 💜\n\nПробное завершено. Никакого постоянного аккаунта создавать не будем.')
  raise ApplicationHandlerStop
 context.user_data.pop('trial_guest_message',None);await _show(update,r);raise ApplicationHandlerStop
async def trial_gate(update:Update,context:ContextTypes.DEFAULT_TYPE):
 u=update.effective_user;m=update.effective_message
 if not u or not m:return
 # /start was already routed above; let permanent-account handlers continue.
 command=str(m.text or '').strip().split(maxsplit=1)
 if command and command[0].split('@',1)[0].lower()=='/start':return
 try:r=public_trial_channel.pending_by_external('TELEGRAM',str(u.id))
 except Exception:r=None
 if not r:return
 if context.user_data.pop('trial_guest_message',None):
  text=str(m.text or m.caption or '').strip()[:1500]
  if text:
   try:
    from core import admin_roles
    for a in admin_roles.list_admins():
     if a['active']:
      try:await context.bot.send_message(int(a['telegram_id']),f"💬 ПРОБНОЕ • {r.get('name') or 'Без имени'}\n\n{text}\n\nЗаявка #{r['id']}")
      except Exception:pass
   except Exception:pass
  await m.reply_text('✅ Сообщение передано преподавателю.',reply_markup=_kb(r))
 else:await _show(update,r)
 raise ApplicationHandlerStop
def register(application):
 application.add_handler(CommandHandler('start',start_join),group=-184)
 application.add_handler(CallbackQueryHandler(trial_callback,pattern=r'^trial_guest\|'),group=-183)
 application.add_handler(MessageHandler(filters.ALL,trial_gate),group=-182)
