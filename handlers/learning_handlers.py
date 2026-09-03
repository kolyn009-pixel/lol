from telegram import InlineKeyboardButton,InlineKeyboardMarkup,Update
from telegram.ext import CommandHandler,CallbackQueryHandler,ContextTypes
from core import admin_roles
from learning import schema,curriculum
from learning.prelesson_brief import build as build_brief
from learning.exam_results import history
from learning.student_progress import get_goal

async def learning_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
 if not admin_roles.is_admin_id(update.effective_user.id): return
 schema.initialize();curriculum.seed()
 kb=[[InlineKeyboardButton('🔎 Карточка ученика',callback_data='learn_help_card'),InlineKeyboardButton('📚 Программа',callback_data='learn_help_program')],[InlineKeyboardButton('🧪 Диагностика',callback_data='learn_help_diag'),InlineKeyboardButton('📈 Пробники',callback_data='learn_help_exam')]]
 await update.effective_message.reply_text('🧠 <b>Учебный контур — Stage 2</b>\n\nКоманды:\n<code>/studentbrief ID</code> — сводка перед уроком\n<code>/learningcard ID</code> — учебная карточка\n\nДанные хранятся отдельно от старой логики.',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))

async def brief_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
 if not admin_roles.is_admin_id(update.effective_user.id):return
 if not context.args or not context.args[0].isdigit():
  await update.message.reply_text('Использование: /studentbrief ID');return
 await update.message.reply_text(build_brief(int(context.args[0])),parse_mode='HTML')

async def card_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
 if not admin_roles.is_admin_id(update.effective_user.id):return
 if not context.args or not context.args[0].isdigit(): await update.message.reply_text('Использование: /learningcard ID');return
 uid=int(context.args[0]); rows=curriculum.summary(uid); goal=get_goal(uid); exams=history(uid)
 mastered=sum(1 for r in rows if r['status']=='MASTERED'); review=sum(1 for r in rows if r['status']=='REVIEW'); total=len(rows)
 text=['🎓 <b>Учебная карточка</b>',f'📚 Темы: {mastered}/{total} освоено • {review} повторить']
 if goal:text.append('🎯 Цель: '+goal['target_text'])
 if exams:text.append(f"📈 Последний пробник: {exams[-1]['test_score']}")
 text.append('\n'+build_brief(uid))
 await update.message.reply_text('\n'.join(text),parse_mode='HTML')

async def help_cb(update:Update,context:ContextTypes.DEFAULT_TYPE):
 q=update.callback_query
 if not admin_roles.is_admin_id(q.from_user.id):return
 await q.answer()
 texts={'learn_help_card':'Карточка объединяет цель, темы, ДЗ, пробники и приватные заметки.','learn_help_program':'Статусы тем: ⚪ не проходили, 🔵 изучаем, 🟡 повторить, 🟢 освоено. Формулы остаются в существующих справочниках и связываются с темами.','learn_help_diag':'Диагностика поддерживает QUICK и WORK: быстрая оценка преподавателя или результат диагностической работы.','learn_help_exam':'Пробники хранят дату, первичный и тестовый балл; история используется для динамики.'}
 await q.message.reply_text(texts.get(q.data,'Учебный модуль'))

def handlers():
 return [CommandHandler('learning',learning_cmd),CommandHandler('studentbrief',brief_cmd),CommandHandler('learningcard',card_cmd),CallbackQueryHandler(help_cb,pattern=r'^learn_help_')]
