from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def install(application=None):
    import admin as admin_module
    from handlers import homework_attention

    if getattr(admin_module, "_admin_home_v2_installed", False):
        return

    original_snapshot = admin_module._admin_home_snapshot
    original_menu = admin_module.admin_menu
    original_text = admin_module.admin_home_text

    def snapshot_v2():
        snap = dict(original_snapshot())
        try:
            snap["homework"] = int(homework_attention.count_pending())
        except Exception:
            snap["homework"] = 0
        return snap

    def menu_v2():
        # Rebuild from the canonical layout so the homework counter has a
        # stable dedicated place instead of being hidden in generic tasks.
        s = snapshot_v2()
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            import database
            tz_name = database.get_setting("bot_timezone", "Europe/Samara") or "Europe/Samara"
            hour = datetime.now(ZoneInfo(tz_name)).hour
        except Exception:
            from datetime import datetime
            hour = datetime.now().hour

        review_label = f"▶️ Разобрать всё • {s['review_total']}" if s.get("review_total") else "▶️ Разобрать всё"
        suffix = f" • {s['review_total']}" if s.get("review_total") else ""
        day_label = (
            f"🌅 Подготовить день{suffix}" if hour < 12
            else (f"🌙 Закрыть день{suffix}" if hour >= 18 else review_label)
        )
        homework_label = f"📝 ДЗ • {int(s.get('homework') or 0)}"

        keyboard = [
            [InlineKeyboardButton(day_label, callback_data="ux_review_start")],
            [InlineKeyboardButton("📅 Сегодня", callback_data="crm_today"),
             InlineKeyboardButton("👥 Ученики", callback_data="admin_students")],
            [InlineKeyboardButton("⚙️ Моё расписание", callback_data="admin_schedule")],
            [InlineKeyboardButton(f"📌 Мои задачи • {s.get('tasks',0)}", callback_data="task_home"),
             InlineKeyboardButton(homework_label, callback_data="homework_attention")],
            [InlineKeyboardButton(f"💬 Сообщения • {s.get('messages',0)}", callback_data="admin_student_messages"),
             InlineKeyboardButton("➕ Записать", callback_data="admin_manual_lesson")],
            [InlineKeyboardButton(f"💳 Оплаты • {s.get('unpaid',0)}", callback_data="mh_debts"),
             InlineKeyboardButton("🔎 Найти", callback_data="crm_search")],
            [InlineKeyboardButton("📢 Канал", callback_data="admin_free_windows"),
             InlineKeyboardButton("👨‍👩‍👧 Родители", callback_data="admin_parents")],
            [InlineKeyboardButton("💜 Спросить Аделию", callback_data="mh_ask")],
            [InlineKeyboardButton("••• Ещё", callback_data="ux_all"),
             InlineKeyboardButton("⚙️ Настройки", callback_data="ux_settings")],
        ]
        return InlineKeyboardMarkup(keyboard)

    def text_v2():
        text = original_text()
        s = snapshot_v2()
        marker = "\n📌 Рабочих задач:"
        if marker in text:
            text = text.replace(
                marker,
                f"\n📝 ДЗ требуют внимания: {int(s.get('homework') or 0)}" + marker,
                1,
            )
        return text

    admin_module._admin_home_snapshot = snapshot_v2
    admin_module.admin_menu = menu_v2
    admin_module.admin_home_text = text_v2
    admin_module._admin_home_v2_installed = True
