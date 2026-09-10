from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from core import post_lesson
from . import channel_delivery

_STATE = {}
_INSTALLED = False


def _review_marks(lesson_id: int):
    c = database.connect()
    try:
        review = c.execute(
            "SELECT id FROM post_lesson_reviews WHERE lesson_id=? ORDER BY id DESC LIMIT 1",
            (int(lesson_id),),
        ).fetchone()
        if not review:
            return []
        rows = c.execute(
            """
            SELECT topic_id,level,comment
            FROM post_lesson_topic_marks
            WHERE review_id=?
            ORDER BY id
            """,
            (int(review["id"]),),
        ).fetchall()
        return [(int(r["topic_id"]), str(r["level"]), r["comment"]) for r in rows]
    finally:
        c.close()


def _notify_tg_done(admin_tid: int, lesson_id: int):
    try:
        channel_delivery.send_telegram_chat(
            int(admin_tid),
            (
                "✅ ОПРОС ПОСЛЕ ЗАНЯТИЯ ПРОЙДЕН В VK\n\n"
                f"Занятие #{int(lesson_id)} уже сохранено.\n"
                "Повторно проходить опрос в Telegram не нужно."
            ),
            reply_markup={
                "inline_keyboard": [[
                    {"text": "🏠 Главное меню", "callback_data": "global_home"}
                ]]
            },
        )
    except Exception as exc:
        print("VK REVIEW TG SYNC ERROR:", repr(exc))


def _state(vk_id: int):
    return _STATE.get(int(vk_id))


def _start_state(vk_id: int, lesson_id: int):
    lesson = database.get_lesson(int(lesson_id))
    if not lesson:
        return None
    uid = int(lesson["user_id"])
    post_lesson.ensure_sync(int(lesson_id), uid, "VK")
    st = {
        "lesson_id": int(lesson_id),
        "uid": uid,
        "sections": post_lesson.sections_for_student(uid, int(lesson_id)),
        "marks": post_lesson.draft_marks(int(lesson_id)),
        "topics": [],
    }
    _STATE[int(vk_id)] = st
    return st


def _summary(st):
    lines = post_lesson.mark_lines(st.get("marks") or [])
    if not lines:
        return "Пока ни одной темы не отмечено."
    return "Выбрано:\n" + "\n".join(f"• {x[2:] if len(x) > 2 else x}" for x in lines)


def _send_sections(app, peer, st):
    if not st["sections"]:
        app.send(
            peer,
            "🧠 ОПРОС ПОСЛЕ ЗАНЯТИЯ\n\nВ карте обучения пока нет тем. Можно завершить опрос без отметок.",
            True,
            "teacher_review_sections",
            {"lesson_id": st["lesson_id"], "sections": [], "has_marks": False},
        )
        return
    extra = ("\n\n" + _summary(st)) if st.get("marks") else ""
    app.send(
        peer,
        "🧠 ОПРОС ПОСЛЕ ЗАНЯТИЯ\n\nЧто прошли? Выбери раздел, затем можно отметить несколько тем." + extra,
        True,
        "teacher_review_sections",
        {
            "lesson_id": st["lesson_id"],
            "sections": st["sections"],
            "has_marks": bool(st.get("marks")),
        },
    )


def _send_after_mark(app, peer, st):
    app.send(
        peer,
        "✅ Тема отмечена.\n\n" + _summary(st),
        True,
        "teacher_review_after_mark",
        {"lesson_id": st["lesson_id"]},
    )


def _finish_result_text(result):
    return (
        "✅ ЗАНЯТИЕ ЗАВЕРШЕНО\n\n"
        f"⏱ Фактически: {result['actual_minutes']} мин\n"
        f"⏳ Недоработано: {result['underworked_minutes']} мин\n"
        f"🎁 Бонус ученику: {result['bonus_minutes_awarded']} мин\n\n"
        "Теперь отметь, что прошли на занятии 👇"
    )


def install(app):
    global _INSTALLED
    if _INSTALLED or getattr(app, "_teacher_post_lesson_installed", False):
        return

    original_keyboard = app.keyboard
    original_handle = app._handle_teacher

    def keyboard(linked=False, mode="home", data=None):
        data = data or {}
        b = app._button
        rows = app._keyboard_rows
        if mode == "teacher_review_start":
            lid = int(data["lesson_id"])
            return rows([[
                b("🧠 Пройти опрос", f"t_review|{lid}", "primary"),
            ], [
                b("🏠 Главная", "t_home"),
            ]])
        if mode == "teacher_review_sections":
            lid = int(data["lesson_id"])
            sections = list(data.get("sections") or [])
            page = max(0, int(data.get("page") or 0))

            # VK ограничивает размер клавиатуры.
            # Оставляем максимум 6 разделов на странице.
            per_page = 6
            pages = max(
                1,
                (len(sections) + per_page - 1) // per_page,
            )
            page = min(page, pages - 1)

            start_i = page * per_page
            end_i = min(start_i + per_page, len(sections))

            out = []

            for i in range(start_i, end_i):
                subject, section = sections[i]
                out.append([
                    b(
                        f"📚 {subject} • {section}"[:38],
                        f"t_review_section|{lid}|{i}",
                        "primary",
                    )
                ])

            if pages > 1:
                nav = []

                if page > 0:
                    nav.append(
                        b(
                            "⬅️",
                            f"t_review_sections_page|{lid}|{page - 1}",
                        )
                    )

                if page + 1 < pages:
                    nav.append(
                        b(
                            "➡️",
                            f"t_review_sections_page|{lid}|{page + 1}",
                        )
                    )

                if nav:
                    out.append(nav)

            if data.get("has_marks"):
                out.append([
                    b(
                        "✅ Темы выбраны",
                        f"t_review_confirm|{lid}",
                        "positive",
                    )
                ])
            elif not sections:
                out.append([
                    b(
                        "⏭ Без отметок",
                        f"t_review_empty|{lid}",
                    )
                ])

            out.append([
                b("🏠 Главная", "t_home")
            ])

            return rows(out)

        if mode == "teacher_review_topics":
            lid = int(data["lesson_id"])
            topics = list(data.get("topics") or [])
            page = max(0, int(data.get("page") or 0))

            per_page = 6
            pages = max(
                1,
                (len(topics) + per_page - 1) // per_page,
            )
            page = min(page, pages - 1)

            start_i = page * per_page
            end_i = min(start_i + per_page, len(topics))

            out = []

            for i in range(start_i, end_i):
                out.append([
                    b(
                        str(topics[i]["topic"])[:38],
                        f"t_review_topic|{lid}|{i}",
                    )
                ])

            if pages > 1:
                nav = []

                if page > 0:
                    nav.append(
                        b(
                            "⬅️",
                            f"t_review_topics_page|{lid}|{page - 1}",
                        )
                    )

                if page + 1 < pages:
                    nav.append(
                        b(
                            "➡️",
                            f"t_review_topics_page|{lid}|{page + 1}",
                        )
                    )

                if nav:
                    out.append(nav)

            out.append([
                b(
                    "➕ К другим разделам",
                    f"t_review_more|{lid}",
                )
            ])

            if data.get("has_marks"):
                out.append([
                    b(
                        "✅ Темы выбраны",
                        f"t_review_confirm|{lid}",
                        "positive",
                    )
                ])

            return rows(out)

        if mode == "teacher_review_level":
            lid = int(data["lesson_id"])
            return rows([
                [b("⚪ Только начали", f"t_review_level|{lid}|STARTED"), b("🔴 Есть сложности", f"t_review_level|{lid}|NEEDS_WORK")],
                [b("🟡 Закрепить", f"t_review_level|{lid}|GOOD"), b("🟢 Усвоено", f"t_review_level|{lid}|MASTERED")],
                [b("⬅️ Назад", f"t_review_more|{lid}")],
            ])
        if mode == "teacher_review_after_mark":
            lid = int(data["lesson_id"])
            return rows([
                [b("➕ Добавить ещё тему", f"t_review_more|{lid}")],
                [b("✅ Темы выбраны", f"t_review_confirm|{lid}", "positive")],
            ])
        if mode == "teacher_review_homework":
            lid = int(data["lesson_id"])
            return rows([
                [b("📝 Задать ДЗ по этим темам", f"t_review_hw|{lid}", "primary")],
                [b("➕ Добавить ещё тему", f"t_review_more|{lid}")],
                [b("⏭ Без ДЗ", f"t_review_nohw|{lid}")],
                [b("🏠 Главная", "t_home")],
            ])
        return original_keyboard(linked, mode, data)

    def handle_teacher(peer, vk_id, command, raw, attachments=None):
        attachments = attachments or []
        admin_tid = None
        try:
            admin_tid = int(__import__("vk_adapter.teacher_service", fromlist=["is_teacher"]).is_teacher(vk_id) or 0)
        except Exception:
            admin_tid = 0

        pending = app._PENDING.get(vk_id)
        if pending and isinstance(pending, tuple) and pending and pending[0] == "t_hw_review" and not command:
            app._PENDING.pop(vk_id, None)
            _, lid, uid = pending
            text = str(raw or "").strip()
            if not text and attachments:
                text = "📎 " + app._attachment_label(attachments)
            if not text:
                app.send(peer, "Пришли текст ДЗ или прикрепи файл 💜", True, "teacher")
                return
            from . import teacher_service
            hid, delivered = teacher_service.create_homework(int(uid), text)
            marks = _review_marks(int(lid))
            if hid:
                try:
                    post_lesson.link_homework_topics(int(hid), marks)
                    post_lesson.set_homework_status(int(lid), "SENT", int(hid))
                except Exception as exc:
                    print("VK REVIEW HOMEWORK LINK ERROR:", repr(exc))
            if attachments and hid:
                try:
                    from .attachment_bridge import vk_forward_to_student
                    vk_forward_to_student(int(uid), attachments, f"📝 ДЗ #{hid}\n\n{text}")
                    try:
                        from . import homework_v6

                        import vk_adapter.app as vk_app

                        homework_v6.deliver(
                            vk_app,
                            int(hid),
                            int(uid),
                            also_telegram=True,
                        )

                    except Exception as exc:
                        print(
                            "HW6 VK REVIEW DELIVERY:",
                            repr(exc),
                            flush=True,
                        )
                except Exception as exc:
                    print("VK REVIEW HOMEWORK ATTACH ERROR:", repr(exc))
            app.send(
                peer,
                f"✅ ДЗ #{hid} отправлено по темам занятия.\nTelegram: {'да' if delivered['telegram'] else 'нет'} · VK: {'да' if delivered['vk'] else 'нет'}",
                True,
                "teacher",
            )
            return

        if command.startswith("t_finish|"):
            lid = int(command.split("|", 1)[1])
            lesson = database.get_lesson(lid)
            if not lesson:
                app.send(peer, "❌ Занятие не найдено.", True, "teacher")
                return
            try:
                if str(lesson["lesson_status"] or "").upper() == "IN_PROGRESS":
                    result = database.finish_lesson(lid)
                    text = _finish_result_text(result)
                else:
                    text = "✅ Занятие уже завершено.\n\nМожно перейти к итогам занятия 👇"
                st = _start_state(vk_id, lid)
                if post_lesson.review_completed(lid):
                    app.send(peer, "✅ Опрос по этому занятию уже пройден в другом канале.", True, "teacher")
                else:
                    app.send(peer, text, True, "teacher_review_start", {"lesson_id": lid})
            except Exception as exc:
                app.send(peer, f"❌ Не удалось завершить занятие: {exc}", True, "teacher")
            return

        if command.startswith("t_review|"):
            lid = int(command.split("|", 1)[1])
            if post_lesson.review_completed(lid):
                app.send(peer, "✅ Опрос уже пройден. Повторно отмечать темы не нужно.", True, "teacher")
                return
            st = _start_state(vk_id, lid)
            if not st:
                app.send(peer, "❌ Занятие не найдено.", True, "teacher")
                return
            _send_sections(app, peer, st)
            return

        if command.startswith("t_review_more|"):
            lid = int(command.split("|", 1)[1])
            st = _state(vk_id) or _start_state(vk_id, lid)
            if st:
                _send_sections(app, peer, st)
            return

        if command.startswith("t_review_section|"):
            _, lid, idx = command.split("|", 2)
            st = _state(vk_id) or _start_state(vk_id, int(lid))
            if not st:
                return
            idx = int(idx)
            if idx < 0 or idx >= len(st["sections"]):
                return
            subject, section = st["sections"][idx]
            st["topics"] = post_lesson.topics_for_section(st["uid"], st["lesson_id"], subject, section)
            app.send(
                peer,
                f"📚 {subject} • {section}\n\nВыбери тему:",
                True,
                "teacher_review_topics",
                {"lesson_id": st["lesson_id"], "topics": st["topics"], "has_marks": bool(st["marks"])},
            )
            return

        if command.startswith("t_review_topic|"):
            _, lid, idx = command.split("|", 2)
            st = _state(vk_id) or _start_state(vk_id, int(lid))
            idx = int(idx)
            if not st or idx < 0 or idx >= len(st.get("topics") or []):
                return
            st["topic"] = st["topics"][idx]
            app.send(
                peer,
                f"Тема: {st['topic']['topic']}\n\nКак прошла тема?",
                True,
                "teacher_review_level",
                {"lesson_id": st["lesson_id"]},
            )
            return

        if command.startswith("t_review_level|"):
            _, lid, level = command.split("|", 2)
            st = _state(vk_id) or _start_state(vk_id, int(lid))
            if not st or not st.get("topic"):
                return
            topic = st["topic"]
            topic_id = int(topic["topic_id"] if "topic_id" in topic.keys() else topic["id"])
            st["marks"] = post_lesson.upsert_mark(st.get("marks"), topic_id, level, None)
            st["marks"] = post_lesson.save_draft_marks(st["lesson_id"], st["uid"], st["marks"], "VK")
            _send_after_mark(app, peer, st)
            return

        if command.startswith("t_review_confirm|"):
            lid = int(command.split("|", 1)[1])
            st = _state(vk_id) or _start_state(vk_id, lid)
            if not st or not st.get("marks"):
                app.send(peer, "Сначала отметь хотя бы одну тему.", True, "teacher_review_sections", {"lesson_id": lid, "sections": st["sections"] if st else [], "has_marks": False})
                return
            post_lesson.save_review(lid, st["uid"], st["marks"], actor=admin_tid or None, channel="VK")
            app.send(peer, "📚 Темы занятия сохранены.\n\n" + _summary(st) + "\n\nЧто делаем с домашним заданием?", True, "teacher_review_homework", {"lesson_id": lid})
            if admin_tid:
                _notify_tg_done(admin_tid, lid)
            return

        if command.startswith("t_review_empty|"):
            lid = int(command.split("|", 1)[1])
            st = _state(vk_id) or _start_state(vk_id, lid)
            if st:
                post_lesson.save_review(lid, st["uid"], [], actor=admin_tid or None, channel="VK")
                post_lesson.set_homework_status(lid, "SKIPPED")
            app.send(peer, "✅ Опрос завершён без отметок по темам.", True, "teacher")
            if admin_tid:
                _notify_tg_done(admin_tid, lid)
            return

        if command.startswith("t_review_hw|"):
            lid = int(command.split("|", 1)[1])
            lesson = database.get_lesson(lid)
            if not lesson:
                return
            app._PENDING[vk_id] = ("t_hw_review", lid, int(lesson["user_id"]))
            topics = post_lesson.review_summary(lid).get("topics") or []
            topic_text = ", ".join(topics[:4]) if topics else "выбранным темам"
            app.send(peer, f"📝 ДЗ ПО ТЕМАМ ЗАНЯТИЯ\n\nТемы: {topic_text}\n\nПришли следующим сообщением текст ДЗ и/или прикрепи файл.", True, "teacher")
            return

        if command.startswith("t_review_nohw|"):
            lid = int(command.split("|", 1)[1])
            post_lesson.set_homework_status(lid, "SKIPPED")
            _STATE.pop(int(vk_id), None)
            app.send(peer, "✅ Итоги сохранены. Для этого занятия ДЗ не задаём.", True, "teacher")
            return

        return original_handle(peer, vk_id, command, raw, attachments)

    app.keyboard = keyboard
    app._handle_teacher = handle_teacher
    app._teacher_post_lesson_installed = True
    _INSTALLED = True
