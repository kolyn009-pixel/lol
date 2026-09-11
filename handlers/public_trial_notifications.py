from __future__ import annotations

from urllib.parse import quote

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles
from web_backend import public_trial

LAST_ID_KEY = "public_trial_last_notified_id"


def _admins():
    try:
        return [int(r["telegram_id"]) for r in admin_roles.list_admins() if r["active"]]
    except Exception:
        return []


def _pending_after(last_id: int, limit: int = 20):
    public_trial.ensure_schema()
    c = database.connect()
    try:
        return c.execute(
            """
            SELECT id,name,telegram,phone,grade,subject,study_goal,preferred_time,note,status,created_at
            FROM public_trial_requests
            WHERE id>? AND status='NEW'
            ORDER BY id ASC
            LIMIT ?
            """,
            (int(last_id), int(limit)),
        ).fetchall()
    finally:
        c.close()


def _text(row):
    parts = [
        "🎓 НОВАЯ ЗАЯВКА С САЙТА",
        "",
        f"Заявка №{int(row['id'])}",
        f"👤 {row['name']}",
    ]
    if row["grade"]:
        parts.append(f"🏫 Класс: {row['grade']}")
    if row["subject"]:
        parts.append(f"📚 Предмет: {row['subject']}")
    if row["study_goal"]:
        parts.append(f"🎯 Цель: {row['study_goal']}")
    if row["preferred_time"]:
        parts.append(f"🕒 Когда удобно: {row['preferred_time']}")
    if row["telegram"]:
        parts.append(f"✈️ Telegram: {row['telegram']}")
    if row["phone"]:
        parts.append(f"📞 Телефон: {row['phone']}")
    if row["note"]:
        parts.extend(["", f"💬 Комментарий: {row['note']}"])
    parts.extend(["", "Выберите, что сделать с заявкой:"])
    return "\n".join(parts)


def _markup(row):
    rid = int(row["id"])
    rows = []
    username = str(row["telegram"] or "").strip()
    if username.startswith("@") and len(username) > 1:
        rows.append([InlineKeyboardButton("✈️ Написать в Telegram", url=f"https://t.me/{quote(username[1:])}")])
    rows.append([
        InlineKeyboardButton("✅ Взять в работу", callback_data=f"ptrial|contacted|{rid}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"ptrial|declined|{rid}"),
    ])
    return InlineKeyboardMarkup(rows)


async def dispatch_job(context):
    admins = _admins()
    if not admins:
        return
    try:
        last_id = int(database.get_setting(LAST_ID_KEY, "0") or 0)
    except Exception:
        last_id = 0
    rows = _pending_after(last_id)
    for row in rows:
        rid = int(row["id"])
        delivered = False
        for aid in admins:
            try:
                await context.bot.send_message(
                    chat_id=aid,
                    text=_text(row),
                    reply_markup=_markup(row),
                    disable_web_page_preview=True,
                )
                delivered = True
            except Exception as exc:
                print("PUBLIC TRIAL NOTIFY FAILED", rid, aid, repr(exc), flush=True)
        if not delivered:
            break
        database.set_setting(LAST_ID_KEY, str(rid))
        database.log_automation_delivery("public_trial_notify", "OK", "ADMIN", rid)


async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    if int(q.from_user.id) not in set(_admins()):
        await q.answer("Недостаточно прав", show_alert=True)
        return
    try:
        _, action, raw_id = (q.data or "").split("|", 2)
        rid = int(raw_id)
    except Exception:
        await q.answer("Некорректная заявка", show_alert=True)
        return

    if action == "contacted":
        try:
            public_trial.set_status(rid, "CONTACTED", reviewer_id=q.from_user.id)
            await q.answer("Заявка взята в работу")
            await q.edit_message_text((q.message.text or "") + "\n\n✅ ВЗЯТО В РАБОТУ")
        except Exception as exc:
            await q.answer("Не удалось обновить заявку", show_alert=True)
            print("PUBLIC TRIAL CONTACTED FAILED", rid, repr(exc), flush=True)
        return

    if action == "declined":
        try:
            public_trial.set_status(rid, "DECLINED", reviewer_id=q.from_user.id)
            await q.answer("Заявка отклонена")
            await q.edit_message_text((q.message.text or "") + "\n\n❌ ОТКЛОНЕНО")
        except Exception as exc:
            await q.answer("Не удалось обновить заявку", show_alert=True)
            print("PUBLIC TRIAL DECLINE FAILED", rid, repr(exc), flush=True)
        return

    await q.answer("Неизвестное действие", show_alert=True)


def register(application):
    application.add_handler(CallbackQueryHandler(callback, pattern=r"^ptrial\|"))
    jq = application.job_queue
    if jq:
        names = {job.name for job in jq.jobs()}
        if "public_trial_notify" not in names:
            jq.run_repeating(dispatch_job, interval=15, first=5, name="public_trial_notify")
