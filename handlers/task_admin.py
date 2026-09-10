from __future__ import annotations
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters
from core import admin_roles, teacher_tasks
import database

WAIT_TITLE=1301

def _admin(uid): return admin_roles.is_admin_id(uid)

async def _edit(q,text,kb=None):
    try: await q.edit_message_text(text[:3900],reply_markup=kb)
    except Exception as e:
        if 'Message is not modified' not in str(e): raise

def _home_markup():
    teacher_tasks.sync_auto(); rows=teacher_tasks.list_open(15); kb=[]
    for r in rows:
        icon='🔴' if int(r['priority'] or 2)==1 else ('🟡' if int(r['priority'] or 2)==2 else '🟢')
        kb.append([InlineKeyboardButton(f"{icon} {str(r['title'])[:42]}",callback_data=f"task_view|{r['id']}")])
    kb += [[InlineKeyboardButton('➕ Добавить задачу',callback_data='task_add')],
           [InlineKeyboardButton('🔄 Обновить умные задачи',callback_data='task_sync')],
           [InlineKeyboardButton('⬅️ Назад',callback_data='admin_main'),InlineKeyboardButton('🏠 Главная',callback_data='global_home')]]
    return InlineKeyboardMarkup(kb),len(rows)

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not q.data.startswith('task_'): return
    if not _admin(q.from_user.id): await q.answer('Нет доступа',show_alert=True); return
    await q.answer(); d=q.data
    if d in ('task_home','task_sync'):
        kb,n=_home_markup(); await _edit(q,f'📌 МОИ ЗАДАЧИ\n\n💜 Я собрала рабочие дела в одном месте. Открыто: {n}.\n\nАвтоматические задачи создаются без ИИ: оплаты, несданные ДЗ и отсутствие следующей записи.',kb); return
    if d=='task_add':
        context.user_data['task_user_id']=None
        await _edit(q,'📌 НОВАЯ ЗАДАЧА\n\nНапишите одним сообщением, что нужно сделать.\n\nНапример: «Написать маме Ивана после занятия».',InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data='task_home')]])); return WAIT_TITLE
    if d.startswith('task_add_user|'):
        context.user_data['task_user_id']=int(d.split('|')[1]); u=database.get_user(context.user_data['task_user_id']); name=u['name'] if u else 'ученику'
        await _edit(q,f'📌 ЗАДАЧА • {name}\n\nНапишите, что нужно сделать.',InlineKeyboardMarkup([[InlineKeyboardButton('❌ Отмена',callback_data=f'admin_student|{context.user_data["task_user_id"]}')]])); return WAIT_TITLE
    if d.startswith('task_remind|'):
        tid=int(d.split('|')[1]);r=teacher_tasks.get(tid)
        if not r or not str(r['source_key'] or '').startswith('homework-missed:'):
            await q.answer('Напоминание недоступно',show_alert=True);return
        from web_backend.homework_watchdog import remind_from_task
        result=remind_from_task(r['source_key']);status=result.get('status')
        labels={'ok':'Напоминание поставлено в отправку','already_reminded':'Сегодня уже напоминали','already_submitted':'ДЗ уже сдано','suppressed':'У ученика больничный/отпуск — не напоминаю'}
        await q.answer(labels.get(status,'Не удалось создать напоминание'),show_alert=True)
        if status=='already_submitted':teacher_tasks.set_status(tid,'DONE')
        return
    if d.startswith('task_view|'):
        tid=int(d.split('|')[1]); r=teacher_tasks.get(tid)
        if not r: await _edit(q,'💜 Эта задача уже недоступна.',InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К задачам',callback_data='task_home')]])); return
        who=f"\n👤 {r['user_name']}" if r['user_name'] else ''
        due=f"\n🕐 {str(r['due_at'])[:16].replace('T',' ')}" if r['due_at'] else ''
        kb=[]

        source_key = str(
            r['source_key']
            or ''
        )

        hw_lesson_id = None

        if source_key.startswith(
            'assign_hw:'
        ):
            try:
                hw_lesson_id = int(
                    source_key.split(
                        ':',
                        1,
                    )[1]
                )
            except Exception:
                hw_lesson_id = None

        if hw_lesson_id:
            kb.append([
                InlineKeyboardButton(
                    '📝 Задать ДЗ',
                    callback_data=(
                        f'hw_task_start|'
                        f'{hw_lesson_id}'
                    ),
                )
            ])

            kb.append([
                InlineKeyboardButton(
                    '⏭ Без ДЗ',
                    callback_data=(
                        f'admin_homework_skip|'
                        f'{hw_lesson_id}'
                    ),
                )
            ])

        if source_key.startswith('homework-missed:'):
            kb.append([
                InlineKeyboardButton(
                    '💬 Напомнить',
                    callback_data=f'task_remind|{tid}',
                )
            ])

        if r['user_id']:
            kb.append([
                InlineKeyboardButton(
                    '👤 Карточка ученика',
                    callback_data=(
                        f"admin_student|"
                        f"{r['user_id']}"
                    ),
                ),
                InlineKeyboardButton(
                    '💜 Аделия',
                    callback_data=(
                        f"mh_student_ask|"
                        f"{r['user_id']}"
                    ),
                ),
            ])

        if hw_lesson_id:
            # This task is state-derived.
            # It cannot be manually "completed".
            # Creating homework or choosing Без ДЗ
            # is the only way to close it.
            kb.append([
                InlineKeyboardButton(
                    '🕐 На завтра',
                    callback_data=(
                        f'task_defer|{tid}'
                    ),
                )
            ])
        else:
            kb.append([
                InlineKeyboardButton(
                    '✅ Выполнено',
                    callback_data=(
                        f'task_done|{tid}'
                    ),
                ),
                InlineKeyboardButton(
                    '🕐 На завтра',
                    callback_data=(
                        f'task_defer|{tid}'
                    ),
                ),
            ])

        kb.append([
            InlineKeyboardButton(
                '⬅️ К задачам',
                callback_data='task_home',
            ),
            InlineKeyboardButton(
                '🏠 Главная',
                callback_data='global_home',
            ),
        ])
        await _edit(q,f"📌 ЗАДАЧА{who}{due}\n\n{r['title']}",InlineKeyboardMarkup(kb)); return
    if d.startswith('task_done|'):
        teacher_tasks.set_status(int(d.split('|')[1]),'DONE'); kb,n=_home_markup(); await _edit(q,f'💜 Готово. Закрыла задачу.\n\nОсталось: {n}.',kb); return
    if d.startswith('task_defer|'):
        teacher_tasks.defer(int(d.split('|')[1]),24); kb,n=_home_markup(); await _edit(q,f'💜 Отложила до завтра. Она не потеряется.\n\nСейчас в очереди: {n}.',kb); return

async def title_text(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id): return ConversationHandler.END
    title=(update.message.text or '').strip()
    if len(title)<2:
        await update.message.reply_text('💜 Напишите задачу чуть подробнее.'); return WAIT_TITLE
    uid=context.user_data.pop('task_user_id',None); teacher_tasks.add(title,user_id=uid)
    await update.message.reply_text('💜 Готово. Добавила задачу.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📌 Мои задачи',callback_data='task_home')],[InlineKeyboardButton('🏠 Главная',callback_data='global_home')]])); return ConversationHandler.END

def handlers():
    conv=ConversationHandler(entry_points=[CallbackQueryHandler(callbacks,pattern=r'^task_(?:add|add_user\|\d+)$')],states={WAIT_TITLE:[MessageHandler(filters.TEXT & ~filters.COMMAND,title_text)]},fallbacks=[],allow_reentry=True)
    return [conv,CallbackQueryHandler(callbacks,pattern=r'^task_')]
