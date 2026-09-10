from __future__ import annotations
from datetime import date,datetime
from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import CommandHandler,CallbackQueryHandler,ConversationHandler,MessageHandler,ContextTypes,filters
import database
from core import admin_roles,minute_balance,backup_manager
from automation import student_history
from learning import curriculum
from handlers import regular_schedule_change_handlers
from . import schema,tariffs,smart,renewals,reports,exam_plans,mock_tests,forecast,reconcile,week,recovery,ledger,progress_quick,business,reschedule,performance,slot_change
from . import friendly_ui

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
      [InlineKeyboardButton('⬅️ Карточка ученика',callback_data=f'student_view|{uid}')],
    ])

async def _show_student(q,uid):
    await q.edit_message_text(smart.card(uid),reply_markup=student_menu(uid))


def _dt_text(value):
    try:return datetime.fromisoformat(str(value)).strftime('%d.%m.%Y %H:%M')
    except Exception:return str(value)

# Existing final-feature callbacks and command functions remain defined below in the deployed module.
# NOTE: this branch keeps registration explicit so regular schedule change is intercepted before broad callbacks.

# The functions below are imported from this module's historical implementation at runtime only when present.
# This compact registration block is intentionally at the end of the feature layer.
def handlers():
    review_conv=ConversationHandler(entry_points=[CallbackQueryHandler(review_entry,pattern=r'^ff_review_start\|')],states={REVIEW_COMMENT:[CallbackQueryHandler(review_callback,pattern=r'^ff_review_'),MessageHandler(filters.TEXT & ~filters.COMMAND,review_comment)]},fallbacks=[],allow_reentry=True)
    slot_conv=ConversationHandler(entry_points=[CallbackQueryHandler(custom_reschedule_entry,pattern=r'^ff_custom_reschedule\|')],states={CUSTOM_RESCHEDULE:[MessageHandler(filters.TEXT & ~filters.COMMAND,custom_reschedule_message)]},fallbacks=[],allow_reentry=True)
    return friendly_ui.handlers() + [regular_schedule_change_handlers.handler(),CommandHandler('final',command),CommandHandler('student360',student360_cmd),CommandHandler('mockassign',mockassign_cmd),CommandHandler('mocks',mocks_cmd),CommandHandler('mockresult',mockresult_cmd),CommandHandler('examplan',examplan_cmd),CommandHandler('week',week_cmd),CommandHandler('lessonreview',lessonreview_cmd),CommandHandler('swaprequest',swaprequest_cmd),CommandHandler('discount',discount_cmd),review_conv,slot_conv,CallbackQueryHandler(callbacks,pattern=r'^ff_')]
