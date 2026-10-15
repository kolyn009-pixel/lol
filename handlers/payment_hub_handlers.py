"""Telegram payment hub shared by student and parent entry points.

This is intentionally a thin UI layer over the canonical finance functions.
Parents can pay only for linked students. A payment menu always puts the
nearest unpaid lesson first and the subscription action directly underneath.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, MessageHandler, ContextTypes, filters

import database
import payments
from web_backend import payment_hub, student_finance


def _money(value):
    return f"{int(value or 0):,} ₽".replace(",", " ")


def _subject(value):
    return payments.SUBJECT_NAMES.get(value, value or "Занятие")


def _parent_and_allowed(tid, student_id):
    parent=database.get_parent_by_telegram_id(int(tid))
    if not parent or not parent["active"]:
        raise PermissionError("parent_not_found")
    allowed={int(x["id"]) for x in database.get_parent_students(int(parent["id"]))}
    if int(student_id) not in allowed:
        raise PermissionError("student_not_linked")
    return parent


def _hub_markup(hub, *, prefix, student_id):
    rows=[]
    lesson=hub.get("nearest_unpaid_lesson")
    if lesson:
        rows.append([InlineKeyboardButton(
            "💳 Оплатить ближайшее занятие",
            callback_data=f"{prefix}_nearest|{int(student_id)}|{int(lesson['id'])}",
        )])
    rows.append([InlineKeyboardButton(
        "🎟 Оплатить несколько занятий",
        callback_data=f"{prefix}_packages|{int(student_id)}",
    )])
    rows.append([InlineKeyboardButton(
        "📜 История оплат",
        callback_data=f"{prefix}_history|{int(student_id)}",
    )])
    back="parent_main" if prefix=="parent_payhub" else "main"
    rows.append([InlineKeyboardButton("⬅️ Назад",callback_data=back)])
    return InlineKeyboardMarkup(rows)


def _hub_text(hub):
    student=hub["student"]
    lines=[f"💳 ОПЛАТА — {student['name']}",""]
    nearest=hub.get("nearest_unpaid_lesson")
    if nearest:
        lines.extend([
            "Ближайшее неоплаченное занятие:",
            f"📅 {str(nearest['start_time'])[:16].replace('T',' ')}",
            f"📚 {_subject(nearest['subject'])}",
            f"⏱ {int(nearest.get('duration_minutes') or 0)} минут",
            f"💰 {_money(nearest.get('price'))}",
            "",
            "Можно оплатить его отдельно или купить абонемент.",
        ])
    else:
        lines.extend([
            "✅ Сейчас нет ближайших занятий, требующих отдельной оплаты.",
            "",
            "Абонемент можно пополнить заранее — кнопка ниже.",
        ])
    waiting=(hub.get("finance") or {}).get("waiting_payment")
    if waiting:
        lines.extend(["",f"🧾 Есть незавершённый платёж: {_money(waiting.get('total_amount'))} · {waiting.get('status')}"])
    return "\n".join(lines)


async def open_parent(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();tid=int(update.effective_user.id)
    parent=database.get_parent_by_telegram_id(tid)
    if not parent or not parent["active"]:return
    children=database.get_parent_students(int(parent["id"]))
    if not children:
        await q.edit_message_text("К профилю пока не привязан ученик.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад",callback_data="parent_main")]]));return
    if len(children)>1:
        rows=[[InlineKeyboardButton(f"🎓 {x['name']}",callback_data=f"parent_payhub_student|{int(x['id'])}")] for x in children]
        rows.append([InlineKeyboardButton("⬅️ Назад",callback_data="parent_main")])
        await q.edit_message_text("💳 За кого хотите посмотреть оплату?",reply_markup=InlineKeyboardMarkup(rows));return
    uid=int(children[0]["id"]);context.user_data["parent_acting_student_id"]=uid
    hub=payment_hub.student_hub(uid)
    await q.edit_message_text(_hub_text(hub),reply_markup=_hub_markup(hub,prefix="parent_payhub",student_id=uid))


async def open_parent_student(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();uid=int(q.data.split("|",1)[1]);_parent_and_allowed(update.effective_user.id,uid)
    context.user_data["parent_acting_student_id"]=uid
    hub=payment_hub.student_hub(uid)
    await q.edit_message_text(_hub_text(hub),reply_markup=_hub_markup(hub,prefix="parent_payhub",student_id=uid))


async def open_student(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();user=database.get_user_by_telegram_id(int(update.effective_user.id))
    if not user:return
    hub=payment_hub.student_hub(int(user["id"]))
    await q.edit_message_text(_hub_text(hub),reply_markup=_hub_markup(hub,prefix="student_payhub",student_id=int(user["id"])))


def _verify_actor(update,uid,prefix):
    if prefix=="parent_payhub":
        _parent_and_allowed(update.effective_user.id,uid);return
    user=database.get_user_by_telegram_id(int(update.effective_user.id))
    if not user or int(user["id"])!=int(uid):raise PermissionError("student_not_found")


async def pay_nearest(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();prefix=q.data.split("_nearest|",1)[0];parts=q.data.split("|");uid=int(parts[1]);lesson_id=int(parts[2]);_verify_actor(update,uid,prefix)
    nearest=payment_hub.nearest_payable_lesson(uid)
    if not nearest or int(nearest["id"])!=lesson_id:
        await q.answer("Список уже изменился — обновляю.",show_alert=True);hub=payment_hub.student_hub(uid);await q.edit_message_text(_hub_text(hub),reply_markup=_hub_markup(hub,prefix=prefix,student_id=uid));return
    result=student_finance.create_lesson_payment(uid,lesson_id)
    p=result["payment"]
    context.user_data["payhub_receipt_payment_id"]=int(p["id"]);context.user_data["payhub_receipt_user_id"]=uid;context.user_data["payhub_receipt_prefix"]=prefix
    await q.edit_message_text(
        f"💳 ОПЛАТА БЛИЖАЙШЕГО ЗАНЯТИЯ\n\n💰 К оплате: {_money(p['total_amount'])}\n\n{result['payment_method']}\n\nПосле перевода нажмите кнопку ниже и отправьте чек.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📎 Прикрепить чек",callback_data=f"payhub_receipt|{uid}|{int(p['id'])}")],[InlineKeyboardButton("⬅️ К оплате",callback_data="parent_payment_hub" if prefix=="parent_payhub" else "student_payment_hub")]])
    )


async def packages(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();prefix=q.data.split("_packages|",1)[0];uid=int(q.data.split("|",1)[1]);_verify_actor(update,uid,prefix)
    finance=student_finance.overview(uid);tariffs=finance.get("tariffs") or []
    rows=[]
    for t in tariffs:
        label=f"🎟 {_subject(t['subject'])} · {int(t['duration'])} мин · {_money(t['nominal'])}/занятие"
        rows.append([InlineKeyboardButton(label,callback_data=f"{prefix}_tariff|{uid}|{int(t['selection_key'])}")])
    rows.append([InlineKeyboardButton("⬅️ К оплате",callback_data="parent_payment_hub" if prefix=="parent_payhub" else "student_payment_hub")])
    await q.edit_message_text("🎟 АБОНЕМЕНТ\n\nВыберите направление. На следующем шаге — количество занятий.",reply_markup=InlineKeyboardMarkup(rows))


async def tariff(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();prefix=q.data.split("_tariff|",1)[0];_,uid_raw,key_raw=q.data.split("|");uid=int(uid_raw);key=int(key_raw);_verify_actor(update,uid,prefix)
    rows=[]
    for count in (1,2,4,8,12):
        quote=student_finance.quote(uid,key,count)
        rows.append([InlineKeyboardButton(f"{count} {'занятие' if count==1 else 'занятия' if count in (2,4) else 'занятий'} · {_money(quote['total_amount'])}",callback_data=f"{prefix}_buy|{uid}|{key}|{count}")])
    rows.append([InlineKeyboardButton("⬅️ К тарифам",callback_data=f"{prefix}_packages|{uid}")])
    await q.edit_message_text("🎟 Выберите количество занятий. Например, 2 занятия на неделю — один платёж и один чек.",reply_markup=InlineKeyboardMarkup(rows))


async def buy_package(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();prefix=q.data.split("_buy|",1)[0];_,uid_raw,key_raw,count_raw=q.data.split("|");uid=int(uid_raw);key=int(key_raw);count=int(count_raw);_verify_actor(update,uid,prefix)
    result=student_finance.create_package_payment(uid,key,count);p=result["payment"]
    context.user_data["payhub_receipt_payment_id"]=int(p["id"]);context.user_data["payhub_receipt_user_id"]=uid;context.user_data["payhub_receipt_prefix"]=prefix
    await q.edit_message_text(
        f"🎟 АБОНЕМЕНТ · {count} занятий\n\n💰 К оплате: {_money(p['total_amount'])}\n\n{result['payment_method']}\n\nПосле перевода нажмите кнопку ниже и отправьте чек.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📎 Прикрепить чек",callback_data=f"payhub_receipt|{uid}|{int(p['id'])}")],[InlineKeyboardButton("⬅️ К оплате",callback_data="parent_payment_hub" if prefix=="parent_payhub" else "student_payment_hub")]])
    )


async def receipt_prompt(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();_,uid_raw,pid_raw=q.data.split("|");uid=int(uid_raw);pid=int(pid_raw)
    prefix=context.user_data.get("payhub_receipt_prefix") or ("parent_payhub" if database.get_parent_by_telegram_id(int(update.effective_user.id)) else "student_payhub")
    _verify_actor(update,uid,prefix)
    payment=database.get_payment(pid)
    if not payment or int(payment["user_id"])!=uid:raise PermissionError("payment_not_found")
    context.user_data["payhub_receipt_payment_id"]=pid;context.user_data["payhub_receipt_user_id"]=uid;context.user_data["payhub_receipt_prefix"]=prefix;context.user_data["payhub_wait_receipt"]=True
    await q.edit_message_text("📎 Отправьте сюда фото/скриншот чека или PDF одним сообщением.\n\nЯ прикреплю его к платежу и передам преподавателю на проверку.")


async def receipt_message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("payhub_wait_receipt"):return
    uid=int(context.user_data.get("payhub_receipt_user_id") or 0);pid=int(context.user_data.get("payhub_receipt_payment_id") or 0);prefix=context.user_data.get("payhub_receipt_prefix") or "student_payhub"
    try:_verify_actor(update,uid,prefix)
    except Exception:return
    file_id=None;file_type=None
    if update.message.photo:
        file_id=update.message.photo[-1].file_id;file_type="PHOTO"
    elif update.message.document:
        mime=str(update.message.document.mime_type or "").lower()
        if mime!="application/pdf":
            await update.message.reply_text("Пришлите изображение или PDF чека.");return
        file_id=update.message.document.file_id;file_type="DOCUMENT"
    else:
        await update.message.reply_text("Пришлите фото/скриншот или PDF чека.");return
    payment=database.get_payment(pid)
    if not payment or int(payment["user_id"])!=uid:
        context.user_data.pop("payhub_wait_receipt",None);return
    receipt_id=database.add_receipt(payment_id=pid,user_id=uid,file_id=file_id,file_type=file_type,source_platform="TELEGRAM_PARENT" if prefix=="parent_payhub" else "TELEGRAM")
    for k in ("payhub_wait_receipt","payhub_receipt_payment_id","payhub_receipt_user_id","payhub_receipt_prefix"):context.user_data.pop(k,None)
    back="parent_payment_hub" if prefix=="parent_payhub" else "student_payment_hub"
    await update.message.reply_text("✅ Чек получен и отправлен преподавателю на проверку.\n\nПосле подтверждения статус оплаты обновится автоматически.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Вернуться к оплате",callback_data=back)]]))


async def history(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer();prefix=q.data.split("_history|",1)[0];uid=int(q.data.split("|",1)[1]);_verify_actor(update,uid,prefix)
    rows=student_finance.history(uid,20);lines=["📜 ИСТОРИЯ ОПЛАТ",""]
    if not rows:lines.append("История пока пуста.")
    for p in rows[:12]:lines.append(f"• {str(p.get('created_at') or '')[:10]} · {_money(p.get('total_amount'))} · {p.get('status')}")
    back="parent_payment_hub" if prefix=="parent_payhub" else "student_payment_hub"
    await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К оплате",callback_data=back)]]))


def handlers():
    return [
        CallbackQueryHandler(open_parent,pattern=r"^parent_payment_hub$"),
        CallbackQueryHandler(open_parent_student,pattern=r"^parent_payhub_student\|"),
        CallbackQueryHandler(open_student,pattern=r"^student_payment_hub$"),
        CallbackQueryHandler(pay_nearest,pattern=r"^(?:parent|student)_payhub_nearest\|"),
        CallbackQueryHandler(packages,pattern=r"^(?:parent|student)_payhub_packages\|"),
        CallbackQueryHandler(tariff,pattern=r"^(?:parent|student)_payhub_tariff\|"),
        CallbackQueryHandler(buy_package,pattern=r"^(?:parent|student)_payhub_buy\|"),
        CallbackQueryHandler(history,pattern=r"^(?:parent|student)_payhub_history\|"),
        CallbackQueryHandler(receipt_prompt,pattern=r"^payhub_receipt\|"),
        MessageHandler((filters.PHOTO|filters.Document.PDF)&~filters.COMMAND,receipt_message),
    ]

