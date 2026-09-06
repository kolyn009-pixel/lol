from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ContextTypes

import database
from core import admin_roles, post_lesson


def _admin(uid):
    return admin_roles.is_admin_id(uid)


def pending_rows(limit=50):
    post_lesson.initialize()
    c = database.connect()
    try:
        rows = c.execute(
            """
            SELECT l.id AS lesson_id,l.user_id,l.finished_at,u.name,
                   s.homework_status,s.homework_id,s.selected_json
            FROM lessons l
            JOIN users u ON u.id=l.user_id
            LEFT JOIN post_lesson_review_sync s ON s.lesson_id=l.id
            WHERE l.finished_at IS NOT NULL
              AND l.cancelled_at IS NULL
            ORDER BY datetime(l.finished_at) DESC,l.id DESC
            LIMIT 120
            """
        ).fetchall()
        result = []
        for row in rows:
            lid = int(row['lesson_id'])
            existing = c.execute("SELECT id FROM homeworks WHERE lesson_id=? LIMIT 1", (lid,)).fetchone()
            if existing:
                continue
            status = str(row['homework_status'] or 'PENDING').upper()
            if status in ('SKIPPED', 'SENT'):
                continue
            draft = c.execute(
                "SELECT id,status FROM homework_drafts WHERE lesson_id=? AND status='DRAFT' ORDER BY updated_at DESC LIMIT 1",
                (lid,),
            ).fetchone()
            summary = post_lesson.review_summary(lid)
            topics = list(summary.get('topics') or [])
            result.append({
                'lesson_id': lid,
                'user_id': int(row['user_id']),
                'name': row['name'],
                'finished_at': row['finished_at'],
                'draft_id': int(draft['id']) if draft else None,
                'topics': topics[:4],
            })
            if len(result) >= int(limit):
                break
        return result
    finally:
        c.close()


def count_pending():
    try:
        return len(pending_rows(100))
    except Exception:
        return 0


def _fmt(raw):
    if not raw:
        return '—'
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(raw)).strftime('%d.%m %H:%M')
    except Exception:
        return str(raw)


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not _admin(q.from_user.id):
        return
    await q.answer()
    rows = pending_rows()
    lines = [
        '📝 ДЗ • ТРЕБУЕТ ВНИМАНИЯ',
        '',
        f'Не закрыто: {len(rows)}',
        '',
        'Здесь собраны занятия, где ДЗ ещё не отправлено. Отдельными сообщениями я больше не спамлю.',
    ]
    kb = []
    for item in rows[:30]:
        topics = ', '.join(item['topics']) if item['topics'] else 'темы не отмечены'
        lines.append(f"\n• {item['name']} · {_fmt(item['finished_at'])}\n  {topics}")
        if item['draft_id']:
            label = f"▶️ Продолжить ДЗ · {item['name']}"
            cb = f"hw2_step1|{item['draft_id']}"
        else:
            label = f"📝 Задать ДЗ · {item['name']}"
            cb = f"admin_homework_create|{item['lesson_id']}"
        kb.append([InlineKeyboardButton(label[:60], callback_data=cb)])
        kb.append([InlineKeyboardButton('🧠 Итоги занятия', callback_data=f"ff_review_start|{item['lesson_id']}|{item['user_id']}")])
    if not rows:
        lines += ['', '✅ Все домашние задания закрыты.']
    kb.extend([
        [InlineKeyboardButton('🔄 Обновить', callback_data='homework_attention')],
        [InlineKeyboardButton('🏠 Админка', callback_data='admin_main')],
    ])
    await q.edit_message_text('\n'.join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))


def handlers():
    return [CallbackQueryHandler(show, pattern=r'^homework_attention$')]
