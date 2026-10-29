"""Private language commands and additive per-chat menu; no automatic messages."""
import logging
import re
import time
from telegram import Update,BotCommand,BotCommandScopeChat,BotCommandScopeAllPrivateChats,BotCommandScopeDefault,InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import CommandHandler,CallbackQueryHandler,ApplicationHandlerStop,TypeHandler
from web_backend.self_study_bot import entry,identities


MENU_DESCRIPTION='Мои языки · семейное обучение'

async def sync_language_menu(update,context):
 """Observe private updates without consuming them or sending messages.

 Telegram applies the first nonempty scope/language list, so preserve that
 effective list when adding our entry. Access is always rechecked separately.
 """
 chat=update.effective_chat;user=update.effective_user
 if not chat or chat.type!='private' or not user:return
 try:
  allowed=bool(identities(int(user.id)))
  language=str(getattr(user,'language_code','') or '').lower()
  if not re.fullmatch('[a-z]{2}',language):language=''
  cache=context.chat_data.setdefault('family_language_menu_sync',{})
  key=language
  previous=cache.get(key)
  if previous and previous[0]==allowed and time.monotonic()-previous[1]<300:return
  bot=context.bot;scope=BotCommandScopeChat(chat.id)
  own=list(await bot.get_my_commands(scope=scope,language_code=language))
  managed=lambda c:c.command=='languages' and c.description==MENU_DESCRIPTION
  if not allowed:
   if any(managed(c) for c in own):
    remaining=[c for c in own if not managed(c)]
    if remaining:await bot.set_my_commands(remaining,scope=scope,language_code=language)
    else:await bot.delete_my_commands(scope=scope,language_code=language)
  elif not any(c.command=='languages' for c in own):
   effective=own
   options=[]
   if language:options.append((scope,''))
   for fallback in (BotCommandScopeAllPrivateChats(),BotCommandScopeDefault()):
    if language:options.append((fallback,language))
    options.append((fallback,''))
   for fallback,code in options:
    if effective:break
    effective=list(await bot.get_my_commands(scope=fallback,language_code=code))
   if not any(c.command=='languages' for c in effective) and len(effective)<100:
    await bot.set_my_commands(effective+[BotCommand('languages',MENU_DESCRIPTION)],scope=scope,language_code=language)
  cache[key]=(allowed,time.monotonic())
 except Exception:
  # Menu/network failure must never interrupt homework, login or /start.
  logging.getLogger(__name__).warning('Family language menu sync failed')


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
 application.add_handler(TypeHandler(Update,sync_language_menu),group=-182)
 application.add_handler(CommandHandler(['languages','language_today','language_cards'],language_entry),group=-181)
 application.add_handler(CallbackQueryHandler(language_entry,pattern=r'^familylang:(teacher|student|parent):(today|cards)$'),group=-181)
 application.bot_data['self_study_family_handlers_installed']=True
