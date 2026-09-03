from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from core import admin_roles
from ai_assistant import client as adelia_ai

CHANNEL_IDEA = 9811
BROADCAST_IDEA = 9812


def _admin(uid: int | None) -> bool:
    return bool(uid and admin_roles.is_admin_id(uid))


def _segment_label(seg: str) -> str:
    labels = {
        'ALL': 'все активные ученики',
        'EGE': 'ученики ЕГЭ',
        'OGE': 'ученики ОГЭ',
        'PHYSICS': 'ученики по физике',
        'CHEMISTRY': 'ученики по химии',
    }
    if seg.startswith('GRADE:'):
        return f"{seg.split(':', 1)[1]} класс"
    return labels.get(seg, seg)


def _segment_recipients(seg: str) -> list[int]:
    c = database.connect()
    try:
        if seg == 'ALL':
            rows = c.execute(
                "SELECT DISTINCT telegram_id FROM users WHERE active=1 AND telegram_id IS NOT NULL"
            ).fetchall()
        elif seg in ('EGE', 'OGE'):
            rows = c.execute(
                """SELECT DISTINCT u.telegram_id
                   FROM users u JOIN student_programs p ON p.user_id=u.id
                   WHERE u.active=1 AND u.telegram_id IS NOT NULL AND p.active=1 AND p.study_goal=?""",
                (seg,),
            ).fetchall()
        elif seg in ('PHYSICS', 'CHEMISTRY'):
            rows = c.execute(
                """SELECT DISTINCT u.telegram_id
                   FROM users u JOIN student_programs p ON p.user_id=u.id
                   WHERE u.active=1 AND u.telegram_id IS NOT NULL AND p.active=1 AND p.subject=?""",
                (seg,),
            ).fetchall()
        elif seg.startswith('GRADE:'):
            grade = int(seg.split(':', 1)[1])
            rows = c.execute(
                "SELECT DISTINCT telegram_id FROM users WHERE active=1 AND telegram_id IS NOT NULL AND grade=?",
                (grade,),
            ).fetchall()
        else:
            rows = []
        return [int(r['telegram_id']) for r in rows if r['telegram_id']]
    finally:
        c.close()


def _broadcast_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton('👥 Всем ученикам', callback_data='ac_bseg|ALL')],
        [InlineKeyboardButton('🎓 ЕГЭ', callback_data='ac_bseg|EGE'), InlineKeyboardButton('🎯 ОГЭ', callback_data='ac_bseg|OGE')],
        [InlineKeyboardButton('⚛️ Физика', callback_data='ac_bseg|PHYSICS'), InlineKeyboardButton('🧪 Химия', callback_data='ac_bseg|CHEMISTRY')],
    ]
    for a, b in ((5, 6), (7, 8), (9, 10)):
        rows.append([
            InlineKeyboardButton(f'{a} класс', callback_data=f'ac_bseg|GRADE:{a}'),
            InlineKeyboardButton(f'{b} класс', callback_data=f'ac_bseg|GRADE:{b}'),
        ])
    rows.append([InlineKeyboardButton('11 класс', callback_data='ac_bseg|GRADE:11')])
    rows.append([InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')])
    return InlineKeyboardMarkup(rows)


def _channel_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📤 Опубликовать в канал', callback_data='ac_channel_publish')],
        [InlineKeyboardButton('🔄 Другой вариант', callback_data='ac_channel_retry')],
        [InlineKeyboardButton('✏️ Новая идея', callback_data='ac_channel_start')],
        [InlineKeyboardButton('❌ Отмена', callback_data='admin_main')],
    ])


def _broadcast_preview_keyboard(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f'📨 Отправить ({count})', callback_data='ac_broadcast_send')],
        [InlineKeyboardButton('🔄 Другой вариант', callback_data='ac_broadcast_retry')],
        [InlineKeyboardButton('👥 Выбрать другую группу', callback_data='ac_broadcast_start')],
        [InlineKeyboardButton('❌ Отмена', callback_data='admin_main')],
    ])


async def _channel_preview(message, context, instruction: str) -> None:
    if str(database.get_setting('ai_channel_posts_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
        await message.reply_text(
            '⚠️ OpenRouter сейчас не подключён. Обычная публикация канала продолжает работать.',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📢 Открыть канал', callback_data='admin_free_windows')]]),
        )
        return
    try:
        draft = await adelia_ai.draft_channel_post(instruction=instruction)
    except Exception as exc:
        print('ADELIA CHANNEL DRAFT ERROR:', repr(exc))
        await message.reply_text('⚠️ Аделия сейчас не смогла подготовить пост. Попробуйте ещё раз позже.')
        return
    context.user_data['ac_channel'] = {'instruction': instruction, 'draft': draft}
    await message.reply_text(
        f'💜 АДЕЛИЯ • ЧЕРНОВИК ПОСТА\n\n{draft}\n\nНичего ещё не опубликовано.',
        reply_markup=_channel_preview_keyboard(),
    )


async def _broadcast_preview(message, context, instruction: str, seg: str) -> None:
    tids = _segment_recipients(seg)
    label = _segment_label(seg)
    if not tids:
        await message.reply_text(
            f'⚠️ В группе «{label}» сейчас нет активных получателей.',
            reply_markup=_broadcast_menu(),
        )
        return
    if str(database.get_setting('ai_broadcast_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
        await message.reply_text('⚠️ OpenRouter сейчас не подключён. Обычная адресная рассылка остаётся доступна.')
        return
    try:
        draft = await adelia_ai.draft_broadcast(instruction=instruction, audience=label)
    except Exception as exc:
        print('ADELIA BROADCAST DRAFT ERROR:', repr(exc))
        await message.reply_text('⚠️ Аделия сейчас не смогла подготовить рассылку. Попробуйте ещё раз позже.')
        return
    context.user_data['ac_broadcast'] = {
        'instruction': instruction,
        'draft': draft,
        'segment': seg,
        'recipients': tids,
    }
    await message.reply_text(
        f'💜 АДЕЛИЯ • РАССЫЛКА\n\nАудитория: {label}\nПолучателей: {len(tids)}\n\n{draft}\n\nНичего ещё не отправлено.',
        reply_markup=_broadcast_preview_keyboard(len(tids)),
    )


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data.startswith('ac_'):
        return
    if not _admin(q.from_user.id):
        await q.answer('Нет доступа', show_alert=True)
        return ConversationHandler.END
    await q.answer()
    d = q.data

    if d == 'ac_channel_start':
        await q.edit_message_text(
            '💜 АДЕЛИЯ • ПОСТ В КАНАЛ\n\n'
            'Опишите обычными словами, что хотите сообщить.\n\n'
            'Например:\n'
            '• напиши тёплый пост о наборе на сентябрь\n'
            '• сообщи, что появились свободные места, без давления\n'
            '• сделай короткий полезный пост для родителей\n\n'
            'Я подготовлю черновик. Без подтверждения ничего в канал не уйдёт.'
        )
        return CHANNEL_IDEA

    if d == 'ac_channel_publish':
        if context.user_data.get('ac_channel_sending'):
            await q.answer('Уже отправляю…',show_alert=False); return ConversationHandler.END
        context.user_data['ac_channel_sending']=True
        payload = context.user_data.get('ac_channel') or {}
        draft = (payload.get('draft') or '').strip()
        if not draft:
            context.user_data.pop('ac_channel_sending',None)
            await q.answer('Черновик уже недоступен.', show_alert=True)
            return ConversationHandler.END
        from channel_admin import get_channel_id
        channel_id = get_channel_id()
        if not channel_id:
            context.user_data.pop('ac_channel_sending',None)
            await q.edit_message_text(
                '⚠️ Канал пока не настроен.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📍 Настроить канал', callback_data='channel_set')]]),
            )
            return ConversationHandler.END
        try:
            sent = await context.bot.send_message(chat_id=channel_id, text=draft)
            context.user_data.pop('ac_channel', None)
            await q.edit_message_text(
                f'✅ Опубликовано в канал.\n\nСообщение #{sent.message_id}',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📢 К каналу', callback_data='admin_free_windows')]]),
            )
        except Exception as exc:
            context.user_data.pop('ac_channel_sending',None)
            print('ADELIA CHANNEL PUBLISH ERROR:', repr(exc))
            await q.edit_message_text('❌ Не удалось опубликовать пост. Черновик сохранён — попробуйте ещё раз.', reply_markup=_channel_preview_keyboard())
        return ConversationHandler.END

    if d == 'ac_channel_retry':
        payload = context.user_data.get('ac_channel') or {}
        instruction = payload.get('instruction')
        if not instruction:
            await q.edit_message_text('Черновик уже недоступен. Опишите идею заново.')
            return CHANNEL_IDEA
        await q.edit_message_text('💜 Готовлю другой вариант…')
        await _channel_preview(q.message, context, instruction)
        return ConversationHandler.END

    if d == 'ac_broadcast_start':
        await q.edit_message_text(
            '📣 РАССЫЛКА С АДЕЛИЕЙ\n\nВыберите, кому хотите написать. После выбора вы просто опишете смысл сообщения.',
            reply_markup=_broadcast_menu(),
        )
        return ConversationHandler.END

    if d.startswith('ac_bseg|'):
        seg = d.split('|', 1)[1]
        context.user_data['ac_broadcast_segment'] = seg
        await q.edit_message_text(
            f'💜 АДЕЛИЯ • {_segment_label(seg).upper()}\n\n'
            'Напишите смысл сообщения обычными словами.\n\n'
            'Например: «напомни всем про домашнее задание, дружелюбно» или «сообщи девятиклассникам, что появились дополнительные места».\n\n'
            'Сначала я покажу черновик и количество получателей.'
        )
        return BROADCAST_IDEA

    if d == 'ac_broadcast_send':
        if context.user_data.get('ac_broadcast_sending'):
            await q.answer('Рассылка уже выполняется…',show_alert=False); return ConversationHandler.END
        context.user_data['ac_broadcast_sending']=True
        payload = context.user_data.get('ac_broadcast') or {}
        draft = (payload.get('draft') or '').strip()
        tids = list(payload.get('recipients') or [])
        if not draft or not tids:
            context.user_data.pop('ac_broadcast_sending',None)
            await q.answer('Черновик уже недоступен.', show_alert=True)
            return ConversationHandler.END
        sent = 0
        failed = 0
        blocked = []

        for tid in tids:
            try:
                await context.bot.send_message(chat_id=int(tid), text=draft)
                sent += 1

            except Forbidden:
                user = database.get_user_by_telegram_id(int(tid))

                if user is not None:
                    name = str(user["name"] or "Без имени")
                    username = str(user["telegram_username"] or "").strip().lstrip("@")

                    blocked.append(
                        f"• {name} — @{username}"
                        if username
                        else f"• {name} — ник не указан"
                    )

                    database.set_user_active(user["id"], False)
                else:
                    blocked.append(
                        f"• Telegram ID {tid} — нет записи в users"
                    )

            except Exception as exc:
                failed += 1
                print("ADELIA BROADCAST SEND ERROR:", tid, repr(exc))

        context.user_data.pop('ac_broadcast', None)
        context.user_data.pop('ac_broadcast_sending', None)

        report = (
            "💜 АДЕЛИЯ • РАССЫЛКА ЗАВЕРШЕНА\n\n"
            f"✅ Отправлено: {sent}\n"
            f"🚫 Заблокировали бота: {len(blocked)}\n"
            f"❌ Другие ошибки: {failed}"
        )

        if blocked:
            report += (
                "\n\n🚫 Убраны из активных учеников:\n"
                + "\n".join(blocked)
            )

        await q.edit_message_text(
            report,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    '⬅️ Админка',
                    callback_data='admin_main'
                )]
            ]),
        )
        return ConversationHandler.END

    if d == 'ac_broadcast_retry':
        payload = context.user_data.get('ac_broadcast') or {}
        instruction = payload.get('instruction')
        seg = payload.get('segment')
        if not instruction or not seg:
            await q.edit_message_text('Черновик уже недоступен.', reply_markup=_broadcast_menu())
            return ConversationHandler.END
        await q.edit_message_text('💜 Готовлю другой вариант…')
        await _broadcast_preview(q.message, context, instruction, seg)
        return ConversationHandler.END

    return ConversationHandler.END


async def channel_idea_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    instruction = (update.message.text or '').strip()
    if not instruction:
        await update.message.reply_text('Напишите хотя бы пару слов о том, какой пост нужен.')
        return CHANNEL_IDEA
    await _channel_preview(update.message, context, instruction)
    return ConversationHandler.END


async def broadcast_idea_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    seg = context.user_data.get('ac_broadcast_segment')
    if not seg:
        await update.message.reply_text('Сначала выберите группу.', reply_markup=_broadcast_menu())
        return ConversationHandler.END
    instruction = (update.message.text or '').strip()
    if not instruction:
        await update.message.reply_text('Напишите, что хотите сообщить.')
        return BROADCAST_IDEA
    await _broadcast_preview(update.message, context, instruction, seg)
    return ConversationHandler.END


def handlers():
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(callbacks, pattern=r'^ac_channel_start$'),
            CallbackQueryHandler(callbacks, pattern=r'^ac_bseg\|'),
        ],
        states={
            CHANNEL_IDEA: [MessageHandler(filters.TEXT & ~filters.COMMAND, channel_idea_text)],
            BROADCAST_IDEA: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_idea_text)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    direct = CallbackQueryHandler(callbacks, pattern=r'^ac_')
    return [conv, direct]
