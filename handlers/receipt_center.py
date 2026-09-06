from __future__ import annotations

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles


def _admin(uid):
    return admin_roles.is_admin_id(uid)


def _money(value):
    try:
        return f"{int(round(float(value))):,} ₽".replace(",", " ")
    except Exception:
        return "0 ₽"


def _fmt(value):
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m %H:%M")
    except Exception:
        return str(value)


def _waiting_receipts(limit=50):
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT
                r.id AS receipt_id,
                r.payment_id,
                r.user_id,
                r.telegram_file_id,
                r.source_platform,
                r.file_type,
                r.status AS receipt_status,
                r.created_at,
                p.status AS payment_status,
                p.total_amount,
                p.lesson_id,
                u.name,
                u.grade
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            JOIN users u ON u.id=r.user_id
            WHERE r.status='WAITING'
              AND p.status='RECEIPT_SENT'
            ORDER BY datetime(r.created_at) ASC,r.id ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall())
    finally:
        c.close()


def _receipt(receipt_id):
    c = database.connect()
    try:
        return c.execute(
            """
            SELECT
                r.id AS receipt_id,
                r.payment_id,
                r.user_id,
                r.telegram_file_id,
                r.source_platform,
                r.file_type,
                r.status AS receipt_status,
                r.created_at,
                r.reviewed_at,
                p.status AS payment_status,
                p.total_amount,
                p.lesson_id,
                p.lessons_count,
                p.minutes_total,
                p.base_duration_minutes,
                p.promo_code,
                u.name,
                u.grade,
                u.telegram_id
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            JOIN users u ON u.id=r.user_id
            WHERE r.id=?
            """,
            (int(receipt_id),),
        ).fetchone()
    finally:
        c.close()


def _student_unpaid(uid, limit=20):
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT id,start_time,end_time,duration_minutes,subject,price,payment_status,lesson_status
            FROM lessons
            WHERE user_id=?
              AND lesson_status='CONFIRMED'
              AND payment_status='AWAITING_PAYMENT'
            ORDER BY datetime(start_time) ASC,id ASC
            LIMIT ?
            """,
            (int(uid), int(limit)),
        ).fetchall())
    finally:
        c.close()


def _queue_text(rows):
    lines = [
        "🧾 ЦЕНТР ЧЕКОВ",
        "",
        f"На проверке: {len(rows)}",
        "",
    ]
    if not rows:
        lines.append("✅ Новых чеков сейчас нет.")
    else:
        for row in rows[:20]:
            source = "VK" if str(row["source_platform"] or "").upper() == "VK" else "TG"
            lines.append(
                f"• {row['name']} · {_money(row['total_amount'])} · {source} · {_fmt(row['created_at'])}"
            )
    return "\n".join(lines)


def _queue_keyboard(rows):
    kb = []
    for row in rows[:30]:
        source = "VK" if str(row["source_platform"] or "").upper() == "VK" else "TG"
        kb.append([
            InlineKeyboardButton(
                f"🧾 {row['name']} · {_money(row['total_amount'])} · {source}",
                callback_data=f"receipt_center_view|{row['receipt_id']}",
            )
        ])
    kb.extend([
        [InlineKeyboardButton("🔄 Обновить", callback_data="receipt_center")],
        [InlineKeyboardButton("💳 Долги и оплаты", callback_data="mh_debts")],
        [InlineKeyboardButton("🏠 Админка", callback_data="admin_main")],
    ])
    return InlineKeyboardMarkup(kb)


async def _show_queue(q):
    rows = _waiting_receipts()
    await q.edit_message_text(_queue_text(rows), reply_markup=_queue_keyboard(rows))


async def _send_receipt_media(q, context, row):
    file_id = str(row["telegram_file_id"] or "").strip()
    source = str(row["source_platform"] or "TELEGRAM").upper()
    if not file_id:
        return
    if source != "TELEGRAM":
        # VK attachment ids cannot be reused as Telegram file ids.
        return
    caption = (
        f"🧾 ЧЕК · {row['name']}\n"
        f"💰 {_money(row['total_amount'])}\n"
        f"💳 Платёж #{row['payment_id']}"
    )
    try:
        if str(row["file_type"] or "").upper() == "PHOTO":
            await context.bot.send_photo(q.message.chat_id, file_id, caption=caption)
        else:
            await context.bot.send_document(q.message.chat_id, file_id, caption=caption)
    except Exception:
        pass


async def _show_receipt(q, context, receipt_id):
    row = _receipt(receipt_id)
    if not row:
        await q.answer("Чек не найден.", show_alert=True)
        return
    source = str(row["source_platform"] or "TELEGRAM").upper()
    lesson_line = f"\n📅 Занятие #{row['lesson_id']}" if row["lesson_id"] else ""
    package_line = ""
    if int(row["minutes_total"] or 0):
        package_line = f"\n🎟 {int(row['minutes_total'])} мин"
    elif int(row["lessons_count"] or 0):
        package_line = f"\n🎟 {int(row['lessons_count'])} занятий"
    text = (
        "🧾 ЧЕК НА ПРОВЕРКЕ\n\n"
        f"👤 {row['name']}\n"
        f"🎓 {row['grade']}\n"
        f"💰 {_money(row['total_amount'])}"
        f"{package_line}{lesson_line}\n"
        f"📨 Источник: {source}\n"
        f"🕐 Получен: {_fmt(row['created_at'])}\n"
        f"💳 Платёж #{row['payment_id']} · чек #{row['receipt_id']}"
    )
    if source == "VK":
        text += "\n\nℹ️ Сам файл пришёл из VK. Здесь показываю карточку и действия; оригинал остаётся доступен в VK-диалоге."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"payment_admin_approve|{row['payment_id']}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"payment_admin_reject|{row['payment_id']}")],
        [InlineKeyboardButton("👤 Оплата ученика", callback_data=f"payadmin_student|{row['user_id']}")],
        [InlineKeyboardButton("⬅️ Все чеки", callback_data="receipt_center")],
    ])
    await q.edit_message_text(text, reply_markup=kb)
    await _send_receipt_media(q, context, row)


async def _show_student_payment(q, uid):
    user = database.get_user(int(uid))
    if not user:
        await q.answer("Ученик не найден.", show_alert=True)
        return
    rows = _student_unpaid(uid)
    c = database.connect()
    try:
        waiting = c.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM receipts r JOIN payments p ON p.id=r.payment_id
            WHERE r.user_id=? AND r.status='WAITING' AND p.status='RECEIPT_SENT'
            """,
            (int(uid),),
        ).fetchone()
    finally:
        c.close()
    lines = [
        "💳 ОПЛАТА УЧЕНИКА",
        "",
        f"👤 {user['name']}",
        f"🎓 {user['grade']}",
        f"🧾 Чеков на проверке: {int(waiting['cnt'] or 0) if waiting else 0}",
        f"📅 Неоплаченных занятий: {len(rows)}",
        "",
        "Выберите занятие — сначала покажу предложение, ничего автоматически не отправляю.",
    ]
    kb = []
    for lesson in rows[:15]:
        when = _fmt(lesson["start_time"])
        kb.append([
            InlineKeyboardButton(
                f"💸 {when} · {_money(lesson['price'])}",
                callback_data=f"payadmin_offer_preview|{lesson['id']}",
            )
        ])
    if not rows:
        lines.append("\n✅ Нет занятий, которые сейчас ждут отдельной оплаты.")
    kb.extend([
        [InlineKeyboardButton("🧾 Центр чеков", callback_data="receipt_center")],
        [InlineKeyboardButton("👤 Карточка ученика", callback_data=f"admin_student|{uid}")],
        [InlineKeyboardButton("⬅️ Долги и оплаты", callback_data="mh_debts")],
    ])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))


async def _offer_preview(q, lesson_id):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        await q.answer("Занятие не найдено.", show_alert=True)
        return
    user = database.get_user(int(lesson["user_id"]))
    if not user:
        await q.answer("Ученик не найден.", show_alert=True)
        return
    if str(lesson["lesson_status"] or "").upper() != "CONFIRMED" or str(lesson["payment_status"] or "").upper() != "AWAITING_PAYMENT":
        await q.answer("Это занятие уже не ждёт оплаты.", show_alert=True)
        return
    text = (
        "💸 ПРЕДЛОЖЕНИЕ ОПЛАТЫ\n\n"
        f"👤 {user['name']}\n"
        f"📅 {_fmt(lesson['start_time'])}\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} мин\n"
        f"💰 {_money(lesson['price'])}\n\n"
        "После подтверждения ученику придёт сообщение с кнопкой «💳 Оплатить занятие»."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить предложение", callback_data=f"payadmin_offer_send|{lesson_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"payadmin_student|{lesson['user_id']}")],
    ])
    await q.edit_message_text(text, reply_markup=kb)


async def _send_offer(q, context, lesson_id):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        await q.answer("Занятие не найдено.", show_alert=True)
        return
    user = database.get_user(int(lesson["user_id"]))
    if not user:
        await q.answer("Ученик не найден.", show_alert=True)
        return
    if str(lesson["lesson_status"] or "").upper() != "CONFIRMED" or str(lesson["payment_status"] or "").upper() != "AWAITING_PAYMENT":
        await q.answer("Это занятие уже не ждёт оплаты.", show_alert=True)
        return
    text = (
        "💳 ОПЛАТА ЗАНЯТИЯ\n\n"
        f"📅 {_fmt(lesson['start_time'])}\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} минут\n"
        f"💰 {_money(lesson['price'])}\n\n"
        "До занятия осталось неоплаченное место. Можно открыть оплату по кнопке ниже 💜"
    )
    sent = False
    if user["telegram_id"]:
        try:
            await context.bot.send_message(
                int(user["telegram_id"]),
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Оплатить занятие", callback_data=f"payment_lesson|{lesson_id}")]]),
            )
            sent = True
        except Exception:
            pass
    # VK gets the same factual reminder; payment continues through the linked bot flow.
    try:
        from vk_adapter import channel_delivery
        result = channel_delivery.send_student(int(user["id"]), text + "\n\nОткройте раздел оплаты в боте, чтобы прикрепить чек.")
        sent = bool(result) or sent
    except Exception:
        pass
    if sent:
        await q.answer("Предложение отправлено.", show_alert=True)
    else:
        await q.answer("Не удалось доставить сообщение ни в один канал.", show_alert=True)
    await _show_student_payment(q, int(user["id"]))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not _admin(q.from_user.id):
        return
    await q.answer()
    d = q.data
    if d == "receipt_center":
        await _show_queue(q)
        return
    if d.startswith("receipt_center_view|"):
        await _show_receipt(q, context, int(d.split("|", 1)[1]))
        return
    if d.startswith("payadmin_student|"):
        await _show_student_payment(q, int(d.split("|", 1)[1]))
        return
    if d.startswith("payadmin_offer_preview|"):
        await _offer_preview(q, int(d.split("|", 1)[1]))
        return
    if d.startswith("payadmin_offer_send|"):
        await _send_offer(q, context, int(d.split("|", 1)[1]))
        return


def handlers():
    return [
        CallbackQueryHandler(
            callbacks,
            pattern=r"^(?:receipt_center$|receipt_center_view\||payadmin_student\||payadmin_offer_preview\||payadmin_offer_send\|)",
        )
    ]
