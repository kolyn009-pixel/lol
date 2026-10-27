"""Explicit language commands only. No jobs, menu replacement or automatic messages."""
from telegram import InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import CommandHandler,CallbackQueryHandler,ApplicationHandlerStop
from web_backend.self_study_bot import entry


async def language_entry(update,context):
 chat=update.effective_chat
 if not chat or chat.type!='private':raise ApplicationHandlerStop
 query=update.callback_query
 view='cards' if context.args and context.args[0]=='cards' else 'today'
 role=None
 if query:
  parts=str(query.data).split(':')
  role=parts[1];view=parts[2]
  await query.answer()
 elif update.effective_message.text.split()[0].split('@')[0]=='/language_cards':view='cards'
 result=entry(int(update.effective_user.id),role,view)
 buttons=[]
 if result['status']=='choose':
  labels={'teacher':'Мой профиль владельца','student':'Мой ученический профиль','parent':'Мой родительский профиль'}
  buttons=[[InlineKeyboardButton(labels[r],callback_data='familylang:'+r+':'+view)] for r in result['roles']]
 elif result['status']=='ready':
  buttons=[[InlineKeyboardButton('Открыть мои языки',url=result['url'])],[InlineKeyboardButton('Получить обычный код входа',callback_data=result['login_callback'])]]
 await update.effective_message.reply_text(result['text'],reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)
 raise ApplicationHandlerStop


def install(application):
 if application.bot_data.get('self_study_family_handlers_installed'):return
 application.add_handler(CommandHandler(['languages','language_today','language_cards'],language_entry),group=-181)
 application.add_handler(CallbackQueryHandler(language_entry,pattern=r'^familylang:(teacher|student|parent):(today|cards)$'),group=-181)
 application.bot_data['self_study_family_handlers_installed']=True
