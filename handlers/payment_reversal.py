"""Teacher-only Telegram correction with an explicit second confirmation."""
import database
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from core import payment_reversal

ERRORS = {
    "payment_not_paid": "Этот платёж сейчас не подтверждён.",
    "provider_payment_requires_refund": "Это платёж через кассу. Для него нужен возврат через платёжный сервис.",
    "bonus_payment_not_reversible": "Бонусы исправляются через управление балансом.",
    "payment_not_found": "Платёж не найден.",
}


async def _edit(query, text, markup):
    if query.message.photo or query.message.document:
        await query.edit_message_caption(caption=text, reply_markup=markup)
    else:
        await query.edit_message_text(text, reply_markup=markup)


async def handle(update, context):
    import admin
    if not admin.is_admin(update):
        await update.callback_query.answer("Нет доступа.", show_alert=True)
        return
    q = update.callback_query
    parts = q.data.split("|")
    try:
        value = int(parts[1])
        if parts[0] == "payment_admin_history":
            page = max(0, int(parts[2])) if len(parts) > 2 else 0
            c = database.connect()
            try:
                user = c.execute("SELECT name FROM users WHERE id=?", (value,)).fetchone()
                if not user:
                    raise ValueError("Ученик не найден.")
                rows = c.execute("SELECT id,total_amount,status,created_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 11 OFFSET ?", (value, page*10)).fetchall()
            finally:
                c.close()
            labels = {"PAID": "оплачено", "REVERSED": "подтверждение отменено", "WAITING": "ожидает оплаты", "RECEIPT_SENT": "на проверке", "REJECTED": "отклонено"}
            text = f"💳 Оплаты · {user['name']}\n\n"
            buttons = []
            for p in rows[:10]:
                text += f"#{p['id']} · {p['total_amount']} ₽ · {labels.get(p['status'], p['status'])}\n"
                if p["status"] == "PAID" and int(p["total_amount"] or 0) > 0:
                    buttons.append([InlineKeyboardButton(f"Отменить подтверждение #{p['id']} · {p['total_amount']} ₽", callback_data=f"payment_admin_reverse|{p['id']}")])
            nav = []
            if page: nav.append(InlineKeyboardButton("← Назад", callback_data=f"payment_admin_history|{value}|{page-1}"))
            if len(rows)>10: nav.append(InlineKeyboardButton("Далее →", callback_data=f"payment_admin_history|{value}|{page+1}"))
            if nav: buttons.append(nav)
            buttons.append([InlineKeyboardButton("Карточка ученика", callback_data=f"admin_student|{value}")])
            await _edit(q, text if rows else text+"Оплат пока нет.", InlineKeyboardMarkup(buttons))
            return
        if parts[0] == "payment_admin_reverse":
            p = payment_reversal.preview(value)
            if p["status"] == "REVERSED":
                await q.message.reply_text("Это подтверждение уже отменено.")
                return
            text = (f"Отменить ошибочное подтверждение?\n\n{p['name']}\nПлатёж #{value} · {p['amount']} ₽\n"
                    f"Связанных занятий: {p['lessons_count']}.\n\n"
                    "Ошибочное начисление будет убрано. Связанные занятия останутся в расписании со статусом «Ожидает оплаты». "
                    "История сохранится. Деньги через банк не возвращаются.")
            await _edit(q, text, InlineKeyboardMarkup([
                [InlineKeyboardButton("Да, отменить подтверждение", callback_data=f"payment_admin_reverse_yes|{value}")],
                [InlineKeyboardButton("Оставить оплату", callback_data=f"payment_admin_history|{p['user_id']}")]]))
            return
        if parts[0] == "payment_admin_reverse_yes":
            result = payment_reversal.reverse(value, actor_id=update.effective_user.id, source="TELEGRAM")
            payment_reversal.notify(result)
            if not result["already_reversed"]:
                user = database.get_user(result["user_id"])
                if user and user["telegram_id"]:
                    try:
                        await context.bot.send_message(chat_id=user["telegram_id"],
                            text=f"Преподаватель исправил ошибочное подтверждение оплаты {result['amount']} ₽. Проверьте статус оплаты в кабинете.")
                    except Exception as exc:
                        print("PAYMENT REVERSAL TG NOTIFY:", type(exc).__name__, flush=True)
            await _edit(q, "Подтверждение отменено. Баланс и статусы занятий исправлены. История сохранена.",
                        InlineKeyboardMarkup([[InlineKeyboardButton("Оплаты ученика", callback_data=f"payment_admin_history|{result['user_id']}")]]))
    except (ValueError, TypeError, IndexError) as exc:
        await q.message.reply_text(ERRORS.get(str(exc), str(exc) or "Не удалось отменить подтверждение."))
