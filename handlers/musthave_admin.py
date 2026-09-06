from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, ContextTypes

import database
from core import admin_roles
from crm_plus import service


def _admin(uid):
    return admin_roles.is_admin_id(uid)


def _debts(limit=40):
    c=database.connect()
    try:
        return c.execute("""
            SELECT u.id,u.name,COUNT(l.id) cnt,COALESCE(SUM(l.price),0) amount,MIN(l.start_time) since
            FROM lessons l JOIN users u ON u.id=l.user_id
            WHERE l.lesson_status='CONFIRMED' AND l.payment_status='AWAITING_PAYMENT'
            GROUP BY u.id,u.name ORDER BY datetime(since) LIMIT ?
        """,(int(limit),)).fetchall()
    finally:c.close()


def _waiting_receipt_count():
    c=database.connect()
    try:
        row=c.execute("""
            SELECT COUNT(*) cnt FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            WHERE r.status='WAITING' AND p.status='RECEIPT_SENT'
        """).fetchone()
        return int(row['cnt'] or 0) if row else 0
    except Exception:return 0
    finally:c.close()


async def show_debts(update, context=None):
    q=update.callback_query if hasattr(update,'callback_query') else update
    if q is None:return ConversationHandler.END
    rows=_debts(); total=sum(int(r['amount'] or 0) for r in rows); checks=_waiting_receipt_count()
    lines=['💳 ОПЛАТЫ','','Здесь собраны долги, неоплаченные занятия и чеки на проверке.','',f'🧾 Чеков на проверке: {checks}',f'💸 Учеников с неоплаченными занятиями: {len(rows)}']
    if rows:
        lines += ['', 'Неоплаченные занятия:']
        for r in rows:
            lines.append(f"• {r['name']} — {r['cnt']} зан. · {int(r['amount'] or 0):,} ₽".replace(',',' '))
        lines += ['',f"Всего: {total:,} ₽".replace(',',' ')]
    else:lines += ['','✅ Неоплаченных подтверждённых занятий нет.']
    kb=[[InlineKeyboardButton(f"🧾 Все чеки • {checks}",callback_data='receipt_center')]]
    kb += [[InlineKeyboardButton(f"💳 {r['name']}",callback_data=f"payadmin_student|{r['id']}")] for r in rows[:30]]
    kb += [[InlineKeyboardButton('🧾 Последние платежи',callback_data='mh_payments')],[InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')]]
    await q.edit_message_text('\n'.join(lines)[:3900],reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q or not _admin(q.from_user.id):return ConversationHandler.END
    await q.answer(); d=q.data
    if d=='mh_debts':return await show_debts(update,context)
    if d=='mh_attention':
        rows=service.today_dashboard()['attention']; lines=['⚠️ ТРЕБУЕТ ВНИМАНИЯ','']
        kb=[]
        for uid,name,reasons in rows[:30]:
            lines.append(f"• {name}: {', '.join(reasons)}");kb.append([InlineKeyboardButton(f'👤 {name}',callback_data=f'admin_student|{uid}')])
        if not rows:lines.append('✅ Сейчас ничего срочного.')
        kb.append([InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')]);await q.edit_message_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup(kb));return ConversationHandler.END
    if d=='mh_payments':
        c=database.connect()
        try:rows=c.execute("""SELECT p.id,p.user_id,p.total_amount,p.status,p.created_at,u.name FROM payments p JOIN users u ON u.id=p.user_id WHERE p.payment_type<>'BONUS' ORDER BY p.id DESC LIMIT 25""").fetchall()
        finally:c.close()
        icons={'PAID':'✅','RECEIPT_SENT':'🧾','WAITING':'⏳','REJECTED':'❌','CANCELLED':'🚫'};lines=['🧾 ПОСЛЕДНИЕ ПЛАТЕЖИ','']
        for r in rows:lines.append(f"{icons.get(r['status'],'•')} #{r['id']} · {r['name']} · {int(r['total_amount'] or 0):,} ₽ · {r['status']}".replace(',',' '))
        if not rows:lines.append('Пока платежей нет.')
        await q.edit_message_text('\n'.join(lines)[:3900],reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧾 Чеки на проверке',callback_data='receipt_center')],[InlineKeyboardButton('⬅️ Оплаты',callback_data='mh_debts')]]));return ConversationHandler.END
    return ConversationHandler.END


def handlers():
    return [CallbackQueryHandler(callbacks,pattern=r'^mh_(?:debts|attention|payments)$')]
