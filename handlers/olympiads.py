"""Explicit /olympiads and student-menu callback, after existing access guards."""
import asyncio
import admin
import database
from telegram import InlineKeyboardButton,InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler,CommandHandler,ApplicationHandlerStop
from web_backend.olympiad_bot import summary,cabinet


async def show(update,context):
    if update.effective_chat.type!='private':
        await update.effective_message.reply_text('Откройте «Олимпиады» в личном чате с ботом Аделии.');raise ApplicationHandlerStop
    query=update.callback_query
    if query:await query.answer()
    external=int(update.effective_user.id)
    teacher=external==int(admin.ADMIN_ID)
    user=None if teacher else database.get_user_by_telegram_id(external)
    if not teacher and (not user or not user['active']):
        await update.effective_message.reply_text('Сначала откройте /start и войдите в Аделию.');raise ApplicationHandlerStop
    role='teacher' if teacher else 'student';uid=external if teacher else int(user['id'])
    raw=str(query.data if query else '')
    subject=raw.split(':',1)[1] if ':' in raw else ''
    if subject not in {'PHYSICS','CHEMISTRY'}:subject=''
    try:text=await asyncio.to_thread(summary,role,uid,subject)
    except Exception:text='🏆 Олимпиады\n\nРасписание временно недоступно. Откройте календарь в кабинете.'
    keyboard=InlineKeyboardMarkup([
        [InlineKeyboardButton('⚛️ Физика',callback_data='olympiads:PHYSICS'),InlineKeyboardButton('🧪 Химия',callback_data='olympiads:CHEMISTRY')],
        [InlineKeyboardButton('🗓 Календарь · подготовка · напоминания',url=cabinet(role))],
        [InlineKeyboardButton('🏆 Все олимпиады',callback_data='olympiads')]])
    await update.effective_message.reply_text(text,reply_markup=keyboard,disable_web_page_preview=True)
    raise ApplicationHandlerStop


def register(app):
    app.add_handler(CommandHandler('olympiads',show),group=-99)
    app.add_handler(CallbackQueryHandler(show,pattern=r'^olympiads(?::(?:PHYSICS|CHEMISTRY))?$'),group=-99)
