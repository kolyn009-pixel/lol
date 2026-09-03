from telegram import Update
from telegram.ext import CallbackQueryHandler,CommandHandler,ContextTypes,ConversationHandler
import database,admin
from core import admin_roles,test_lab

async def home(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q: await q.answer()
    context.user_data.clear()
    tid=update.effective_user.id
    test_active = bool(test_lab.active(tid) and (test_lab._is_tester_prod(tid) or admin_roles.is_owner(tid)))
    if test_active:
        database.set_test_mode(True); test_lab.ensure_test_db()
        role=test_lab.get_test_role(tid)
        import bot as b
        if role=='TEACHER':
            text=admin.admin_home_text(); markup=admin.admin_menu()
        elif role=='PARENT':
            parent=database.get_parent_by_telegram_id(tid)
            if parent and parent['active']:
                text=b.parent_home_text(parent); markup=b.parent_menu()
            else:
                text='🧪 Режим родителя\n\n💜 В тестовой базе пока нет вашего родительского профиля. Отправьте /start и зарегистрируйте его один раз — он сохранится для записи гайда.'; markup=None
        else:
            user=database.get_user_by_telegram_id(tid)
            if user and user['active']:
                text=b.student_home_text(user); markup=b.student_menu(user['id'])
            else:
                text='🧪 Режим ученика\n\n💜 В тестовой базе пока нет вашего профиля ученика. Отправьте /start и зарегистрируйте его один раз — он сохранится для записи гайда.'; markup=None
    elif admin_roles.is_admin_id(tid):
        text=admin.admin_home_text();markup=admin.admin_menu()
    else:
        parent=database.get_parent_by_telegram_id(tid);user=database.get_user_by_telegram_id(tid)
        import bot as b
        if parent and parent['active']:
            text=b.parent_home_text(parent);markup=b.parent_menu()
        elif user and user['active']:
            text=b.student_home_text(user);markup=b.student_menu(user['id'])
        else:
            text='🏠 Я не нашла профиль. Нажмите /start — помогу зарегистрироваться 💜';markup=None
    if q: await q.edit_message_text(text,reply_markup=markup)
    else: await update.message.reply_text(text,reply_markup=markup)
    return ConversationHandler.END

def handlers(): return [CommandHandler('home',home),CallbackQueryHandler(home,pattern=r'^global_home$')]
