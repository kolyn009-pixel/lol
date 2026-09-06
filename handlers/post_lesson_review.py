from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from core import admin_roles, post_lesson

REVIEW = 9211


def _admin(uid):
    return admin_roles.is_admin_id(uid)


def _state(context):
    return context.user_data.get("post_lesson_review")


def _clear(context):
    context.user_data.pop("post_lesson_review", None)
    context.user_data.pop("post_lesson_pending_mark", None)


def _summary(st):
    lines = post_lesson.mark_lines(st.get("marks", []))
    if not lines:
        return "Пока ни одной темы не отмечено."
    return "Выбрано:\n" + "\n".join(f"• {line[2:] if len(line) > 2 else line}" for line in lines)


def _sections_keyboard(st):
    rows = []
    for idx, (subject, section) in enumerate(st.get("sections", [])[:30]):
        rows.append([
            InlineKeyboardButton(
                f"{subject} • {section}",
                callback_data=f"plr_section|{idx}",
            )
        ])
    if st.get("marks"):
        rows.append([InlineKeyboardButton("✅ Темы выбраны", callback_data="plr_confirm_topics")])
    else:
        rows.append([InlineKeyboardButton("⏭ Без отметок", callback_data="plr_finish_empty")])
    return InlineKeyboardMarkup(rows)


def _after_mark_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить ещё тему", callback_data="plr_add_more")],
        [InlineKeyboardButton("✅ Темы выбраны", callback_data="plr_confirm_topics")],
    ])


def _homework_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Задать ДЗ по этим темам", callback_data="plr_homework")],
        [InlineKeyboardButton("➕ Добавить ещё тему", callback_data="plr_add_more")],
        [InlineKeyboardButton("⏭ Без ДЗ", callback_data="plr_no_homework")],
    ])


def _persist(st, channel="TG"):
    st["marks"] = post_lesson.save_draft_marks(
        st["lesson_id"],
        st["uid"],
        st.get("marks", []),
        channel,
    )


async def entry(update: Update, context):
    q = update.callback_query
    if not q or not _admin(q.from_user.id):
        return ConversationHandler.END
    await q.answer()
    try:
        _, lesson_id, user_id = q.data.split("|", 2)
        lesson_id, user_id = int(lesson_id), int(user_id)
    except Exception:
        await q.edit_message_text("❌ Не удалось определить занятие.")
        return ConversationHandler.END

    if post_lesson.review_completed(lesson_id):
        row = post_lesson.sync_row(lesson_id)
        channel = row["completed_channel"] if row else None
        suffix = f" в {channel}" if channel else ""
        await q.edit_message_text(
            f"✅ Опрос по этому занятию уже пройден{suffix}.\n\nИтоги сохранены и повторно отмечать темы не нужно.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В админку", callback_data="admin_main")]]),
        )
        return ConversationHandler.END

    sections = post_lesson.sections_for_student(user_id, lesson_id)
    post_lesson.ensure_sync(lesson_id, user_id, "TG")
    restored = post_lesson.draft_marks(lesson_id)
    st = {
        "lesson_id": lesson_id,
        "uid": user_id,
        "marks": restored,
        "sections": sections,
    }
    context.user_data["post_lesson_review"] = st
    if not sections:
        await q.edit_message_text(
            "🧠 Опрос после занятия\n\nДля этого ученика пока нет тем в карте обучения. Можно завершить опрос без отметок.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Завершить без отметок", callback_data="plr_finish_empty")]]),
        )
        return REVIEW
    intro = "📚 Что прошли на занятии?\n\n"
    if restored:
        intro += _summary(st) + "\n\nМожно продолжить с того места, где остановились.\n\n"
    intro += "Выберите раздел, затем можно отметить одну или несколько тем."
    await q.edit_message_text(intro, reply_markup=_sections_keyboard(st))
    return REVIEW


async def callback(update: Update, context):
    q = update.callback_query
    await q.answer()
    st = _state(context)
    if not st:
        await q.edit_message_text("ℹ️ Сессия опроса завершена. Откройте опрос заново.")
        return ConversationHandler.END
    d = q.data

    if post_lesson.review_completed(st["lesson_id"]):
        _clear(context)
        await q.edit_message_text(
            "✅ Опрос по этому занятию уже сохранён в другом канале. Повторное прохождение не требуется.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В админку", callback_data="admin_main")]]),
        )
        return ConversationHandler.END

    if d == "plr_add_more":
        await q.edit_message_text(
            "📚 Добавить ещё тему\n\n" + _summary(st) + "\n\nВыберите раздел:",
            reply_markup=_sections_keyboard(st),
        )
        return REVIEW

    if d.startswith("plr_section|"):
        idx = int(d.split("|", 1)[1])
        if idx < 0 or idx >= len(st["sections"]):
            return REVIEW
        subject, section = st["sections"][idx]
        topics = post_lesson.topics_for_section(st["uid"], st["lesson_id"], subject, section)
        st["topics"] = topics
        kb = [[InlineKeyboardButton(r["topic"], callback_data=f"plr_topic|{i}")] for i, r in enumerate(topics[:40])]
        kb.append([InlineKeyboardButton("⬅️ К разделам", callback_data="plr_add_more")])
        if st["marks"]:
            kb.append([InlineKeyboardButton("✅ Темы выбраны", callback_data="plr_confirm_topics")])
        await q.edit_message_text(
            f"📚 {subject} • {section}\n\nВыберите тему:",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return REVIEW

    if d.startswith("plr_topic|"):
        idx = int(d.split("|", 1)[1])
        topics = st.get("topics", [])
        if idx < 0 or idx >= len(topics):
            return REVIEW
        topic = topics[idx]
        st["topic"] = topic
        await q.edit_message_text(
            f"Тема: {topic['topic']}\n\nКак прошла тема?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⚪ Только начали", callback_data="plr_level|STARTED"),
                    InlineKeyboardButton("🔴 Есть сложности", callback_data="plr_level|NEEDS_WORK"),
                ],
                [
                    InlineKeyboardButton("🟡 Нужно закрепить", callback_data="plr_level|GOOD"),
                    InlineKeyboardButton("🟢 Усвоено", callback_data="plr_level|MASTERED"),
                ],
            ]),
        )
        return REVIEW

    if d.startswith("plr_level|"):
        level = d.split("|", 1)[1]
        topic = st.get("topic")
        if not topic:
            return REVIEW
        topic_id = int(topic["topic_id"] if "topic_id" in topic.keys() else topic["id"])
        context.user_data["post_lesson_pending_mark"] = (topic_id, level)
        await q.edit_message_text(
            f"Тема: {topic['topic']}\n\nМожно добавить короткий комментарий обычным сообщением или сохранить без комментария.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Без комментария", callback_data="plr_no_comment")],
                [InlineKeyboardButton("⬅️ Выбрать другую тему", callback_data="plr_add_more")],
            ]),
        )
        return REVIEW

    if d == "plr_no_comment":
        pending = context.user_data.pop("post_lesson_pending_mark", None)
        if not pending:
            return REVIEW
        topic_id, level = pending
        st["marks"] = post_lesson.upsert_mark(st["marks"], topic_id, level, None)
        _persist(st)
        await q.edit_message_text(
            "✅ Тема отмечена.\n\n" + _summary(st),
            reply_markup=_after_mark_keyboard(),
        )
        return REVIEW

    if d == "plr_confirm_topics":
        if not st["marks"]:
            await q.answer("Сначала отметьте хотя бы одну тему.", show_alert=True)
            return REVIEW
        _persist(st)
        await q.edit_message_text(
            "📚 Темы занятия\n\n" + _summary(st) + "\n\nЧто делаем с домашним заданием?",
            reply_markup=_homework_keyboard(),
        )
        return REVIEW

    if d == "plr_homework":
        if not st["marks"]:
            await q.answer("Сначала выберите темы.", show_alert=True)
            return REVIEW
        post_lesson.save_review(st["lesson_id"], st["uid"], st["marks"], actor=q.from_user.id, channel="TG")
        did = post_lesson.prepare_homework_draft(q.from_user.id, st["lesson_id"], st["uid"], st["marks"])
        _clear(context)
        from learning import homework_flow
        await q.edit_message_text(
            "📝 ДОМАШНЕЕ ЗАДАНИЕ\n\nТемы занятия сохранены. Теперь можно составить ДЗ; подходящие темы уже перенесены в черновик, если нашлось точное соответствие.",
        )
        await homework_flow._show_step1(q, did)
        return ConversationHandler.END

    if d == "plr_no_homework":
        post_lesson.save_review(st["lesson_id"], st["uid"], st["marks"], actor=q.from_user.id, channel="TG")
        post_lesson.set_homework_status(st["lesson_id"], "SKIPPED")
        _clear(context)
        await q.edit_message_text(
            "✅ Итоги занятия сохранены.\n\n🧠 Карта тем обновлена.\n📝 Домашнее задание пропущено.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В админку", callback_data="admin_main")]]),
        )
        return ConversationHandler.END

    if d == "plr_finish_empty":
        post_lesson.save_review(st["lesson_id"], st["uid"], [], actor=q.from_user.id, channel="TG")
        post_lesson.set_homework_status(st["lesson_id"], "SKIPPED")
        _clear(context)
        await q.edit_message_text(
            "✅ Опрос завершён без отметок по темам.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 В админку", callback_data="admin_main")]]),
        )
        return ConversationHandler.END

    return REVIEW


async def comment(update: Update, context):
    st = _state(context)
    pending = context.user_data.pop("post_lesson_pending_mark", None)
    if not st or not pending:
        return ConversationHandler.END
    if post_lesson.review_completed(st["lesson_id"]):
        _clear(context)
        await update.message.reply_text("✅ Этот опрос уже завершён в другом канале.")
        return ConversationHandler.END
    topic_id, level = pending
    st["marks"] = post_lesson.upsert_mark(st["marks"], topic_id, level, (update.message.text or "").strip())
    _persist(st)
    await update.message.reply_text(
        "✅ Комментарий сохранён.\n\n" + _summary(st),
        reply_markup=_after_mark_keyboard(),
    )
    return REVIEW


def handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(entry, pattern=r"^ff_review_start\|")],
        states={
            REVIEW: [
                CallbackQueryHandler(callback, pattern=r"^plr_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, comment),
            ]
        },
        fallbacks=[],
        allow_reentry=True,
    )
