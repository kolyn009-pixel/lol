from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles, admin_inbox, event_center
from automation import messaging
from handlers import message_center_handlers


async def show_unified(q):
    c=admin_inbox.counts(); rows=admin_inbox.event_rows(20)
    lines=["📥 <b>ВХОДЯЩИЕ</b>","",f"Всего требует внимания: <b>{c['total']}</b>",""]
    if c['lesson_requests']: lines.append(f"🔔 Заявки на занятия: <b>{c['lesson_requests']}</b>")
    if c['regular_requests']: lines.append(f"🔁 Постоянное расписание: <b>{c['regular_requests']}</b>")
    if c['receipts']: lines.append(f"🧾 Чеки/оплаты на проверке: <b>{c['receipts']}</b>")
    if c['unpaid']: lines.append(f"💳 Неоплаченные занятия: <b>{c['unpaid']}</b>")
    if c['homework']: lines.append(f"📝 ДЗ на проверке: <b>{c['homework']}</b>")
    if c['waiting_list']: lines.append(f"📋 Лист ожидания: <b>{c['waiting_list']}</b>")
    if c['events']: lines.append(f"🟡 Другие рабочие задачи: <b>{c['events']}</b>")
    if c.get('system_events'): lines.append(f"🛠 Системные события: <b>{c['system_events']}</b> (в разделе «Система»)")
    if not any(c[k] for k in ('lesson_requests','regular_requests','receipts','unpaid','homework','waiting_list','events')):
        lines.append('✅ Сейчас всё обработано.')
    if rows:
        lines += ["","<b>Последние события:</b>"]
        for e in rows[:8]:
            icon={'CRITICAL':'🔴','ACTION':'🟠','ATTENTION':'🟡','INFO':'🔵'}.get(e.get('priority'),'•')
            lines.append(f"{icon} {e.get('title','Событие')}")
    kb=[]
    if c['lesson_requests']: kb.append([InlineKeyboardButton(f"🔔 Заявки ({c['lesson_requests']})",callback_data='admin_requests')])
    if c['regular_requests']: kb.append([InlineKeyboardButton(f"🔁 Постоянные заявки ({c['regular_requests']})",callback_data='schedule_regular_requests')])
    if c['unpaid']: kb.append([InlineKeyboardButton(f"💳 Неоплаченные ({c['unpaid']})",callback_data='admin_unpaid_lessons')])
    if c['waiting_list']: kb.append([InlineKeyboardButton(f"📋 Лист ожидания ({c['waiting_list']})",callback_data='s3_wait_admin')])
    if c.get('system_events'): kb.append([InlineKeyboardButton(f"🛠 Система ({c['system_events']})",callback_data='core_main')])
    kb.append([InlineKeyboardButton('✅ Отметить всё решённым',callback_data='admin_inbox_resolve_all_warn')])
    kb.append([InlineKeyboardButton('🔄 Обновить',callback_data='admin_inbox_all')])
    kb.append([InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')])
    await q.edit_message_text('\n'.join(lines)[:3900],parse_mode='HTML',reply_markup=InlineKeyboardMarkup(kb))


async def show_messages(q,context=None):
    await message_center_handlers.show_main(q,context)


async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not (q.data.startswith('admin_inbox_') or q.data.startswith('admin_student_msg')): return
    if not admin_roles.is_admin_id(q.from_user.id):
        await q.answer('Только для администратора.',show_alert=True); return
    await q.answer()
    if q.data=='admin_inbox_resolve_all_warn':
        await q.edit_message_text(
            '✅ <b>ОТМЕТИТЬ ВСЁ РЕШЁННЫМ?</b>\n\n'
            'Я закрою все открытые сообщения и рабочие уведомления во «Входящих».\n\n'
            'Важно: заявки на занятия, неоплаченные занятия, чеки и ДЗ я не удалю и не изменю — они останутся в своих рабочих разделах.',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton('✅ Да, всё решено',callback_data='admin_inbox_resolve_all')],
                [InlineKeyboardButton('⬅️ Назад',callback_data='admin_inbox_all')],
            ]),
        ); return
    if q.data=='admin_inbox_resolve_all':
        messages=messaging.close_all_inbox(); events=event_center.resolve_all_work_events()
        await q.answer(f'Готово 💜 Закрыто сообщений: {messages}, уведомлений: {events}.',show_alert=True)
        await show_unified(q); return
    if q.data=='admin_inbox_all': await show_unified(q); return
    if q.data=='admin_student_messages': await show_messages(q,context); return
    if q.data.startswith('admin_student_msg_close|'):
        iid=int(q.data.split('|')[1]); messaging.close_inbox(iid); event_center.resolve(iid) if False else None
        await show_messages(q,context); return


def handlers():
    return [CallbackQueryHandler(callbacks,pattern=r'^(admin_inbox_|admin_student_msg)')]
