from __future__ import annotations

from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes, ApplicationHandlerStop

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
            SELECT r.id AS receipt_id,r.payment_id,r.user_id,r.telegram_file_id,
                   r.source_platform,r.file_type,r.status AS receipt_status,r.created_at,
                   p.status AS payment_status,p.total_amount,p.lesson_id,u.name,u.grade
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            JOIN users u ON u.id=r.user_id
            WHERE r.status='WAITING' AND p.status='RECEIPT_SENT'
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
            SELECT r.id AS receipt_id,r.payment_id,r.user_id,r.telegram_file_id,
                   r.source_platform,r.file_type,r.status AS receipt_status,r.created_at,r.reviewed_at,
                   p.status AS payment_status,p.total_amount,p.lesson_id,p.lessons_count,p.minutes_total,
                   p.base_duration_minutes,p.promo_code,u.name,u.grade,u.telegram_id
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
    """
    Payment timeline for one student.

    Includes:
    - latest trial lesson, even if it is already in the past;
    - future confirmed lessons.

    Trial is informational only and never becomes debt.
    """
    c = database.connect()
    try:
        future = list(c.execute(
            """
            SELECT
                id,
                start_time,
                end_time,
                duration_minutes,
                subject,
                hourly_rate,
                price,
                payment_status,
                lesson_status,
                COALESCE(is_trial,0) AS is_trial,
                payment_offer_sent_at,
                COALESCE(payment_offer_count,0) AS payment_offer_count
            FROM lessons
            WHERE user_id=?
              AND lesson_status='CONFIRMED'
              AND datetime(start_time) >= datetime('now')
            ORDER BY datetime(start_time) ASC,id ASC
            LIMIT ?
            """,
            (int(uid), int(limit)),
        ).fetchall())

        trial = c.execute(
            """
            SELECT
                id,
                start_time,
                end_time,
                duration_minutes,
                subject,
                hourly_rate,
                price,
                payment_status,
                lesson_status,
                COALESCE(is_trial,0) AS is_trial,
                payment_offer_sent_at,
                COALESCE(payment_offer_count,0) AS payment_offer_count
            FROM lessons
            WHERE user_id=?
              AND COALESCE(is_trial,0)=1
            ORDER BY datetime(start_time) DESC,id DESC
            LIMIT 1
            """,
            (int(uid),),
        ).fetchone()

        if trial is not None and not any(
            int(row["id"]) == int(trial["id"])
            for row in future
        ):
            future.insert(0, trial)

        return future

    finally:
        c.close()


def _unpaid_students(limit=50):
    """
    Payment action queue.

    Returns only ONE nearest unpaid non-trial future lesson
    for every student. Future recurring lessons are not
    accumulated into current debt.
    """
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT
                u.id,
                u.name,
                l.id AS lesson_id,
                l.start_time AS next_start,
                l.duration_minutes,
                l.hourly_rate,
                l.price AS amount,
                l.payment_status,
                l.payment_offer_sent_at,
                COALESCE(l.payment_offer_count,0) AS payment_offer_count
            FROM users u
            JOIN lessons l ON l.id = (
                SELECT l2.id
                FROM lessons l2
                WHERE l2.user_id=u.id
                  AND l2.lesson_status='CONFIRMED'
                  AND l2.payment_status IN ('AWAITING_PAYMENT','UNPAID')
                  AND COALESCE(l2.is_trial,0)=0
                  AND datetime(l2.start_time) >= datetime('now')
                ORDER BY datetime(l2.start_time) ASC,l2.id ASC
                LIMIT 1
            )
            ORDER BY datetime(l.start_time) ASC,u.name
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall())
    finally:
        c.close()



def _waiting_receipt_for_lesson(lesson_id):
    c = database.connect()
    try:
        return c.execute(
            """
            SELECT r.id,r.created_at
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            WHERE p.lesson_id=?
              AND r.status='WAITING'
              AND p.status='RECEIPT_SENT'
            ORDER BY r.id DESC
            LIMIT 1
            """,
            (int(lesson_id),),
        ).fetchone()
    finally:
        c.close()


def _mark_payment_offer_sent(lesson_id):
    c = database.connect()
    try:
        c.execute(
            """
            UPDATE lessons
            SET payment_offer_sent_at=?,
                payment_offer_count=COALESCE(payment_offer_count,0)+1
            WHERE id=?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                int(lesson_id),
            ),
        )
        c.commit()
    finally:
        c.close()


def _payment_state(lesson):
    if int(lesson["is_trial"] or 0):
        return "🧪 Бесплатное пробное"

    status = str(lesson["payment_status"] or "").upper()

    if status == "PAID":
        return "🔵 Оплачено"

    receipt = _waiting_receipt_for_lesson(int(lesson["id"]))
    if receipt:
        return "🧾 Чек ждёт проверки"

    if lesson["payment_offer_sent_at"]:
        return f"🟡 Предложено {_fmt(lesson['payment_offer_sent_at'])}"

    return "⚪ Оплату ещё не предлагали"


def _recent_paid(limit=20):
    c = database.connect()
    try:
        return list(c.execute(
            """
            SELECT p.id AS payment_id,p.user_id,p.total_amount,p.lesson_id,p.status,
                   u.name,l.start_time
            FROM payments p
            JOIN users u ON u.id=p.user_id
            LEFT JOIN lessons l ON l.id=p.lesson_id
            WHERE p.status='PAID'
            ORDER BY p.id DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall())
    except Exception:
        return []
    finally:
        c.close()


def _queue_text(rows):
    lines = ["🧾 ЦЕНТР ЧЕКОВ", "", f"На проверке: {len(rows)}", ""]
    if not rows:
        lines.append("✅ Новых чеков сейчас нет.")
    else:
        for row in rows[:20]:
            source = "VK" if str(row["source_platform"] or "").upper() == "VK" else "TG"
            lines.append(f"• {row['name']} · {_money(row['total_amount'])} · {source} · {_fmt(row['created_at'])}")
    return "\n".join(lines)


def _queue_keyboard(rows):
    kb = []
    for row in rows[:30]:
        source = "VK" if str(row["source_platform"] or "").upper() == "VK" else "TG"
        kb.append([InlineKeyboardButton(
            f"🧾 {row['name']} · {_money(row['total_amount'])} · {source}",
            callback_data=f"receipt_center_view|{row['receipt_id']}",
        )])
    kb.extend([
        [InlineKeyboardButton("🔄 Обновить", callback_data="receipt_center")],
        [InlineKeyboardButton("💳 Оплаты", callback_data="payadmin_home")],
        [InlineKeyboardButton("🏠 Админка", callback_data="admin_main")],
    ])
    return InlineKeyboardMarkup(kb)


async def _show_queue(q):
    rows = _waiting_receipts()
    await q.edit_message_text(_queue_text(rows), reply_markup=_queue_keyboard(rows))



async def _show_payment_home(q):
    upcoming = _unpaid_students()
    receipts = _waiting_receipts()

    # Only nearest payment per student.
    total = sum(int(row["amount"] or 0) for row in upcoming)

    lines = [
        "💳 ОПЛАТЫ",
        "",
        f"🧾 Чеков на проверке: {len(receipts)}",
        f"👥 Ближайших оплат: {len(upcoming)}",
        f"💰 По ближайшим занятиям: {_money(total)}",
        "",
        "Показываю только ближайшее неоплаченное занятие каждого ученика.",
        "Остальная будущая сетка не считается текущим долгом.",
    ]

    kb = []

    for row in upcoming[:25]:
        marker = "🟡" if row["payment_offer_sent_at"] else "⚪"

        kb.append([
            InlineKeyboardButton(
                f"{marker} {row['name']} · "
                f"{_fmt(row['next_start'])} · "
                f"{_money(row['amount'])}",
                callback_data=f"payadmin_student|{row['id']}",
            )
        ])

    if not upcoming:
        lines += [
            "",
            "✅ Сейчас нет ближайших занятий, ожидающих оплаты.",
        ]

    kb.extend([
        [
            InlineKeyboardButton(
                f"🧾 Центр чеков • {len(receipts)}",
                callback_data="receipt_center",
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Обновить",
                callback_data="payadmin_home",
            )
        ],
        [
            InlineKeyboardButton(
                "🏠 Админка",
                callback_data="admin_main",
            )
        ],
    ])

    await q.edit_message_text(
        "\n".join(lines)[:3900],
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def _send_receipt_media(q, context, row):
    file_id = str(row["telegram_file_id"] or "").strip()
    source = str(row["source_platform"] or "TELEGRAM").upper()
    if not file_id or source != "TELEGRAM":
        return
    caption = f"🧾 ЧЕК · {row['name']}\n💰 {_money(row['total_amount'])}\n💳 Платёж #{row['payment_id']}"
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
        f"👤 {row['name']}\n🎓 {row['grade']}\n💰 {_money(row['total_amount'])}"
        f"{package_line}{lesson_line}\n📨 Источник: {source}\n🕐 Получен: {_fmt(row['created_at'])}\n"
        f"💳 Платёж #{row['payment_id']} · чек #{row['receipt_id']}"
    )
    if source == "VK":
        text += "\n\nℹ️ Оригинал файла остаётся доступен в VK-диалоге."
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data=f"payment_admin_approve|{row['payment_id']}")],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f"payment_admin_reject|{row['payment_id']}")],
        [InlineKeyboardButton("💳 Оплата ученика", callback_data=f"payadmin_student|{row['user_id']}")],
        [InlineKeyboardButton("⬅️ Все чеки", callback_data="receipt_center")],
    ])
    await q.edit_message_text(text, reply_markup=kb)
    await _send_receipt_media(q, context, row)



async def _show_student_payment(q, uid):
    user = database.get_user(int(uid))

    if not user:
        await q.answer("Ученик не найден.", show_alert=True)
        return

    rows = _student_unpaid(uid, 20)

    c = database.connect()
    try:
        waiting = c.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM receipts r
            JOIN payments p ON p.id=r.payment_id
            WHERE r.user_id=?
              AND r.status='WAITING'
              AND p.status='RECEIPT_SENT'
            """,
            (int(uid),),
        ).fetchone()

        history = list(c.execute(
            """
            SELECT id,total_amount,lesson_id,status
            FROM payments
            WHERE user_id=?
              AND status='PAID'
            ORDER BY id DESC
            LIMIT 5
            """,
            (int(uid),),
        ).fetchall())
    finally:
        c.close()

    next_unpaid_id = None

    for lesson in rows:
        if (
            not int(lesson["is_trial"] or 0)
            and str(lesson["payment_status"] or "").upper()
                in {"AWAITING_PAYMENT", "UNPAID"}
        ):
            next_unpaid_id = int(lesson["id"])
            break

    lines = [
        "💳 ОПЛАТА УЧЕНИКА",
        "",
        f"👤 {user['name']}",
        f"🎓 {user['grade']}",
        f"🧾 Чеков на проверке: "
        f"{int(waiting['cnt'] or 0) if waiting else 0}",
        "",
        "📅 Предстоящие занятия:",
    ]

    kb = []

    for lesson in rows[:15]:
        lid = int(lesson["id"])
        is_trial = int(lesson["is_trial"] or 0)
        payment_status = str(
            lesson["payment_status"] or ""
        ).upper()

        if is_trial:
            prefix = "🧪"
            description = "Бесплатное пробное"

        elif payment_status == "PAID":
            prefix = "🔵"
            description = "Оплачено"

        elif lid == next_unpaid_id:
            prefix = "🔴"
            description = (
                "СЛЕДУЮЩЕЕ · "
                + _payment_state(lesson)
            )

        else:
            prefix = "⚪"
            description = "Будущее занятие"

        lines += [
            "",
            f"{prefix} {_fmt(lesson['start_time'])} "
            f"· {_money(lesson['price'])}",
            f"   {description}",
        ]

        # Payment action only for the nearest unpaid lesson.
        if (
            lid == next_unpaid_id
            and not is_trial
            and payment_status in {
                "AWAITING_PAYMENT",
                "UNPAID",
            }
        ):
            if lesson["payment_offer_sent_at"]:
                button = (
                    "🔁 Напомнить об оплате · "
                    f"{_money(lesson['price'])}"
                )
            else:
                button = (
                    "💳 Предложить оплатить · "
                    f"{_money(lesson['price'])}"
                )

            kb.append([
                InlineKeyboardButton(
                    button,
                    callback_data=f"payadmin_offer_preview|{lid}",
                )
            ])

    if not rows:
        lines += [
            "",
            "✅ Предстоящих подтверждённых занятий нет.",
        ]

    if history:
        lines += [
            "",
            "✅ Последние подтверждённые оплаты:",
        ]

        for payment in history:
            suffix = (
                f" · занятие #{payment['lesson_id']}"
                if payment["lesson_id"]
                else ""
            )

            lines.append(
                f"• {_money(payment['total_amount'])} "
                f"· платёж #{payment['id']}{suffix}"
            )

    kb.extend([
        [
            InlineKeyboardButton(
                "🧾 Центр чеков",
                callback_data="receipt_center",
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Все оплаты",
                callback_data="payadmin_home",
            )
        ],
    ])

    await q.edit_message_text(
        "\n".join(lines)[:3900],
        reply_markup=InlineKeyboardMarkup(kb),
    )



async def _offer_preview(q, lesson_id):
    lesson = database.get_lesson(int(lesson_id))

    if not lesson:
        await q.answer(
            "Занятие не найдено.",
            show_alert=True,
        )
        return

    user = database.get_user(int(lesson["user_id"]))

    if not user:
        await q.answer(
            "Ученик не найден.",
            show_alert=True,
        )
        return

    if (
        str(lesson["lesson_status"] or "").upper()
        != "CONFIRMED"
        or str(lesson["payment_status"] or "").upper()
        not in {"AWAITING_PAYMENT", "UNPAID"}
    ):
        await q.answer(
            "Это занятие уже не ждёт оплаты.",
            show_alert=True,
        )
        return

    sent_at = lesson["payment_offer_sent_at"]

    if sent_at:
        title = "🔁 НАПОМИНАНИЕ ОБ ОПЛАТЕ"
        action = "🔁 Отправить напоминание"
        info = (
            f"🟡 Предыдущее предложение: "
            f"{_fmt(sent_at)}"
        )
    else:
        title = "💸 ПРЕДЛОЖЕНИЕ ОПЛАТЫ"
        action = "✅ Отправить предложение"
        info = "⚪ Ранее оплату не предлагали"

    text = (
        f"{title}\n\n"
        f"👤 {user['name']}\n"
        f"📅 {_fmt(lesson['start_time'])}\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} мин\n"
        f"💰 {_money(lesson['price'])}\n"
        f"{info}\n\n"
        "Ученику придёт сообщение с кнопкой "
        "«💳 Оплатить занятие»."
    )

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    action,
                    callback_data=f"payadmin_offer_send|{lesson_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "⬅️ Назад",
                    callback_data=(
                        f"payadmin_student|{lesson['user_id']}"
                    ),
                )
            ],
        ]),
    )



async def _send_offer(q, context, lesson_id):
    lesson = database.get_lesson(int(lesson_id))

    if not lesson:
        await q.answer(
            "Занятие не найдено.",
            show_alert=True,
        )
        return

    user = database.get_user(int(lesson["user_id"]))

    if not user:
        await q.answer(
            "Ученик не найден.",
            show_alert=True,
        )
        return

    if (
        str(lesson["lesson_status"] or "").upper()
        != "CONFIRMED"
        or str(lesson["payment_status"] or "").upper()
        not in {"AWAITING_PAYMENT", "UNPAID"}
    ):
        await q.answer(
            "Это занятие уже не ждёт оплаты.",
            show_alert=True,
        )
        return

    text = (
        "💳 ОПЛАТА ЗАНЯТИЯ\n\n"
        f"📅 {_fmt(lesson['start_time'])}\n"
        f"⏱ {int(lesson['duration_minutes'] or 0)} минут\n"
        f"💰 {_money(lesson['price'])}\n\n"
        "До занятия осталось неоплаченное место. "
        "Можно открыть оплату по кнопке ниже 💜"
    )

    sent = False

    if user["telegram_id"]:
        try:
            await context.bot.send_message(
                int(user["telegram_id"]),
                text,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "💳 Оплатить занятие",
                            callback_data=f"payment_lesson|{lesson_id}",
                        )
                    ]
                ]),
            )
            sent = True
        except Exception:
            pass

    try:
        from vk_adapter import channel_delivery

        result = channel_delivery.send_student(
            int(user["id"]),
            text
            + "\n\nОткройте раздел оплаты в боте, "
              "чтобы прикрепить чек.",
        )

        sent = bool(result) or sent

    except Exception:
        pass

    # Record the offer only after successful delivery.
    if sent:
        _mark_payment_offer_sent(int(lesson_id))

    await q.answer(
        "Предложение отправлено."
        if sent
        else "Не удалось доставить сообщение ни в один канал.",
        show_alert=True,
    )

    await _show_student_payment(
        q,
        int(user["id"]),
    )



async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query

    if not q or not _admin(q.from_user.id):
        return

    await q.answer()
    d = q.data

    # mh_debts is kept only for old buttons.
    # payadmin_home is the canonical payment screen.
    if d in {"mh_debts", "payadmin_home"}:
        await _show_payment_home(q)
        raise ApplicationHandlerStop

    if d == "receipt_center":
        await _show_queue(q)
        raise ApplicationHandlerStop

    if d.startswith("receipt_center_view|"):
        await _show_receipt(
            q,
            context,
            int(d.split("|", 1)[1]),
        )
        raise ApplicationHandlerStop

    if d.startswith("payadmin_student|"):
        await _show_student_payment(
            q,
            int(d.split("|", 1)[1]),
        )
        raise ApplicationHandlerStop

    if d.startswith("payadmin_offer_preview|"):
        await _offer_preview(
            q,
            int(d.split("|", 1)[1]),
        )
        raise ApplicationHandlerStop

    if d.startswith("payadmin_offer_send|"):
        await _send_offer(
            q,
            context,
            int(d.split("|", 1)[1]),
        )
        raise ApplicationHandlerStop


def handlers():
    return [CallbackQueryHandler(
        callbacks,
        pattern=r"^(?:mh_debts$|payadmin_home$|receipt_center$|receipt_center_view\||payadmin_student\||payadmin_offer_preview\||payadmin_offer_send\|)",
    )]
