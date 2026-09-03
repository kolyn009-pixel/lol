import database
from telegram.ext import MessageHandler, CallbackQueryHandler, filters, ApplicationHandlerStop
from . import admin_roles

KEY='maintenance_mode'
MESSAGE_KEY='maintenance_message'

def enabled(): return str(database.get_setting(KEY,'0'))=='1'
def set_enabled(value): database.set_setting(KEY,'1' if value else '0')
def message(): return database.get_setting(MESSAGE_KEY,'🔧 Бот временно находится на техническом обслуживании. Пожалуйста, попробуйте позже.')

def set_message(text): database.set_setting(MESSAGE_KEY,text)

async def _guard(update, context):
    uid=update.effective_user.id if update.effective_user else None
    if not enabled() or admin_roles.is_admin_id(uid) or admin_roles.is_tester(uid): return
    if update.callback_query:
        await update.callback_query.answer('🔧 Сейчас идут технические работы.',show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(message())
    raise ApplicationHandlerStop

def handlers():
    return [MessageHandler(filters.ALL,_guard), CallbackQueryHandler(_guard)]
