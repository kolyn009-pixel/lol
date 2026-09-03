from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, ConversationHandler, MessageHandler, ContextTypes, filters

import database
from core import admin_roles
from crm_plus import service, messenger
from ai_assistant import client as adelia_ai
from ai_assistant import context as ai_context

ASK = 9911
WRITE_MANUAL = 9912
WRITE_AI = 9913
STUDENT_ASK = 9914
EDIT_DRAFT = 9915


def _admin(uid):
    return admin_roles.is_admin_id(uid)


def _kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')]])


async def _edit(q, text, kb=None):
    try:
        await q.edit_message_text(text[:3900], reply_markup=kb)
    except Exception as exc:
        if 'Message is not modified' not in str(exc):
            raise


def _attention():
    return service.today_dashboard()['attention']


def _debts(limit=40):
    conn = database.connect()
    try:
        return conn.execute(
            """SELECT u.id,u.name,COUNT(l.id) cnt,COALESCE(SUM(l.price),0) amount,MIN(l.start_time) since
               FROM lessons l JOIN users u ON u.id=l.user_id
               WHERE l.lesson_status='CONFIRMED' AND l.payment_status='AWAITING_PAYMENT'
               GROUP BY u.id,u.name ORDER BY datetime(since) LIMIT ?""",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def _history(uid, limit=25):
    conn = database.connect()
    try:
        lessons = conn.execute(
            "SELECT start_time,lesson_status,payment_status,price FROM lessons WHERE user_id=? ORDER BY datetime(start_time) DESC LIMIT ?",
            (uid, limit),
        ).fetchall()
        try:
            msgs = conn.execute(
                "SELECT created_at,direction,body FROM crm_student_messages WHERE student_id=? ORDER BY datetime(created_at) DESC LIMIT 8",
                (uid,),
            ).fetchall()
        except Exception:
            msgs = []
        return lessons, msgs
    finally:
        conn.close()


def _student(uid):
    try:
        return database.get_user(int(uid))
    except Exception:
        return None


def _parent_count(uid):
    try:
        return len(database.get_student_parents(int(uid)) or [])
    except Exception:
        return 0


def _recipient_label(target):
    return 'родителям' if target == 'PARENTS' else 'ученику'


def _draft_keyboard(uid):
    draft = None
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📨 Отправить', callback_data=f'mh_senddraft|{uid}')],
        [
            InlineKeyboardButton('🙂 Мягче', callback_data=f'mh_tone|{uid}|soft'),
            InlineKeyboardButton('✂️ Короче', callback_data=f'mh_tone|{uid}|short'),
        ],
        [
            InlineKeyboardButton('👔 Официальнее', callback_data=f'mh_tone|{uid}|formal'),
            InlineKeyboardButton('🔄 Другой вариант', callback_data=f'mh_tone|{uid}|variant'),
        ],
        [InlineKeyboardButton('✏️ Сказать, что изменить', callback_data=f'mh_editdraft|{uid}')],
        [InlineKeyboardButton('⬅️ К ученику', callback_data=f'admin_student|{uid}')],
    ])


async def _show_draft(q, context, uid, draft_text, target='STUDENT', source='AI'):
    user = _student(uid)
    name = user['name'] if user else f'#{uid}'
    context.user_data['mh_ai_draft'] = {
        'uid': int(uid),
        'text': draft_text.strip(),
        'target': target,
        'source': source,
    }
    recipient = 'родителям' if target == 'PARENTS' else name
    text = (
        f"💜 АДЕЛИЯ • ЧЕРНОВИК\n\n"
        f"Получатель: {recipient}\n\n"
        f"{draft_text.strip()}\n\n"
        "Ничего ещё не отправлено."
    )
    await _edit(q, text, _draft_keyboard(uid))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q or not q.data.startswith('mh_'):
        return
    if not _admin(q.from_user.id):
        await q.answer('Только для администратора.', show_alert=True)
        return ConversationHandler.END

    await q.answer()
    d = q.data

    if d == 'mh_blocked_students':
        users = [u for u in database.get_all_users(active_only=False) if not u['active']]
        kb = [[InlineKeyboardButton(f"🚫 {u['name']}", callback_data=f"admin_student|{u['id']}")] for u in users]
        kb.append([InlineKeyboardButton('⬅️ К классам', callback_data='admin_students')])
        await _edit(q, f"🚫 ЗАБЛОКИРОВАННЫЕ УЧЕНИКИ\n\nВсего: {len(users)}", InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if d == 'mh_attention':
        rows = _attention()
        lines = ['⚠️ ТРЕБУЕТ ВНИМАНИЯ', '', 'Я собрала учеников, по которым сейчас лучше принять решение.', '']
        kb = []
        for uid, name, reasons in rows[:30]:
            lines.append(f"• {name}: {', '.join(reasons)}")
            kb.append([InlineKeyboardButton(f'👤 {name}', callback_data=f'admin_student|{uid}')])
        if not rows:
            lines.append('✅ Сейчас ничего срочного.')
        kb.append([InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')])
        await _edit(q, '\n'.join(lines), InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if d == 'mh_debts':
        rows = _debts()
        lines = ['💸 ДОЛГИ И ОПЛАТЫ', '', 'Я собрала неоплаченные подтверждённые занятия.', '']
        kb, total = [], 0
        for r in rows:
            total += int(r['amount'] or 0)
            lines.append(f"• {r['name']} — {r['cnt']} зан. · {int(r['amount'] or 0):,} ₽".replace(',', ' '))
            kb.append([InlineKeyboardButton(f"💳 {r['name']}", callback_data=f"admin_student|{r['id']}")])
        if rows:
            lines += ['', f"Итого по списку: {total:,} ₽".replace(',', ' ')]
        else:
            lines.append('✅ Неоплаченных подтверждённых занятий нет.')
        kb.append([InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')])
        await _edit(q, '\n'.join(lines), InlineKeyboardMarkup(kb))
        return ConversationHandler.END

    if d == 'mh_ask':
        context.user_data['mh_ask'] = True
        await _edit(
            q,
            '💜 СПРОСИТЬ АДЕЛИЮ\n\nНапишите обычным текстом, например:\n'
            '• Кто мне должен?\n• У кого нет следующего занятия?\n• Что требует внимания?\n'
            '• Что завтра?\n• Найди Иван\n• Напиши Ивану про оплату мягко\n\n'
            'Я проверю данные TutorBot и сначала покажу результат.',
            _kb_back(),
        )
        return ASK

    if d.startswith('mh_write|'):
        uid = int(d.split('|')[1])
        user = _student(uid)
        if not user:
            await q.answer('Ученик не найден.', show_alert=True)
            return ConversationHandler.END
        kb = [
            [InlineKeyboardButton('✍️ Написать самому', callback_data=f'mh_write_manual|{uid}')],
            [InlineKeyboardButton('💜 Подготовить с Аделией', callback_data=f'mh_write_ai|{uid}')],
        ]
        if _parent_count(uid):
            kb.append([InlineKeyboardButton('👨‍👩‍👧 Родителям с Аделией', callback_data=f'mh_write_parent_ai|{uid}')])
        kb.extend([
            [InlineKeyboardButton('📜 История переписки', callback_data=f'mh_history|{uid}')],
            [InlineKeyboardButton('⬅️ К ученику', callback_data=f'admin_student|{uid}')],
        ])
        await _edit(
            q,
            f"💬 СООБЩЕНИЕ • {user['name']}\n\n"
            "Можно написать самому или одной фразой объяснить Аделии, что нужно сказать.\n\n"
            "Перед отправкой я всегда покажу черновик.",
            InlineKeyboardMarkup(kb),
        )
        return ConversationHandler.END

    if d.startswith('mh_write_manual|'):
        uid = int(d.split('|')[1])
        user = _student(uid)
        context.user_data['mh_compose'] = {'uid': uid, 'target': 'STUDENT'}
        await _edit(q, f"✍️ СООБЩЕНИЕ • {user['name'] if user else uid}\n\nНапишите текст сообщения. Я покажу предпросмотр перед отправкой.", InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data=f'mh_write|{uid}')]]))
        return WRITE_MANUAL

    if d.startswith('mh_write_ai|') or d.startswith('mh_write_parent_ai|'):
        uid = int(d.split('|')[1])
        target = 'PARENTS' if d.startswith('mh_write_parent_ai|') else 'STUDENT'
        user = _student(uid)
        context.user_data['mh_compose'] = {'uid': uid, 'target': target}
        examples = (
            'Например:\n• мягко напомни про оплату\n• спроси, сможет ли завтра в 18:00\n'
            '• похвали за сегодняшний урок и напомни про ДЗ\n• скажи короче и без эмодзи'
        )
        await _edit(q, f"💜 АДЕЛИЯ • {user['name'] if user else uid}\n\nНапишите мне смысл сообщения обычными словами.\n\n{examples}\n\nЯ использую только факты из TutorBot и сначала покажу черновик.", InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад', callback_data=f'mh_write|{uid}')]]))
        return WRITE_AI

    if d.startswith('mh_student_ask|'):
        uid = int(d.split('|')[1])
        user = _student(uid)
        context.user_data['mh_student_context'] = uid
        await _edit(
            q,
            f"💜 АДЕЛИЯ • {user['name'] if user else uid}\n\n"
            "Спросите что угодно об этом ученике обычными словами. Например:\n"
            "• когда следующее занятие?\n• сколько осталось минут?\n• есть ли долг?\n"
            "• почему требует внимания?\n• что было в последних сообщениях?\n"
            "• подготовь ему сообщение про оплату\n\n"
            "Факты я беру из TutorBot, а не придумываю.",
            InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К ученику', callback_data=f'admin_student|{uid}')]]),
        )
        return STUDENT_ASK

    if d.startswith('mh_editdraft|'):
        uid = int(d.split('|')[1])
        draft = context.user_data.get('mh_ai_draft') or {}
        if int(draft.get('uid') or 0) != uid:
            await q.answer('Черновик устарел.', show_alert=True)
            return ConversationHandler.END
        context.user_data['mh_edit_uid'] = uid
        await _edit(q, '✏️ ЧТО ИЗМЕНИТЬ?\n\nНапишите обычными словами, например:\n• короче\n• без эмодзи\n• убери последнее предложение\n• мягче, но без извинений', InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ К черновику', callback_data=f'mh_showdraft|{uid}')]]))
        return EDIT_DRAFT

    if d.startswith('mh_showdraft|'):
        uid = int(d.split('|')[1])
        draft = context.user_data.get('mh_ai_draft') or {}
        if int(draft.get('uid') or 0) != uid or not draft.get('text'):
            await q.answer('Черновик устарел.', show_alert=True)
            return ConversationHandler.END
        await _show_draft(q, context, uid, draft['text'], draft.get('target', 'STUDENT'), draft.get('source', 'AI'))
        return ConversationHandler.END

    if d.startswith('mh_tone|'):
        _, uid_s, mode = d.split('|', 2)
        uid = int(uid_s)
        draft = context.user_data.get('mh_ai_draft') or {}
        if int(draft.get('uid') or 0) != uid or not draft.get('text'):
            await q.answer('Черновик устарел.', show_alert=True)
            return ConversationHandler.END
        if str(database.get_setting('ai_student_drafts_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
            await q.answer('ИИ сейчас не подключён.', show_alert=True)
            return ConversationHandler.END
        instruction = {
            'soft': 'Сделай сообщение мягче и доброжелательнее, не меняя факты.',
            'short': 'Сделай сообщение заметно короче, сохранив смысл и факты.',
            'formal': 'Сделай сообщение немного официальнее и спокойнее.',
            'variant': 'Дай другой естественный вариант с тем же смыслом и фактами.',
        }.get(mode, 'Перепиши сообщение аккуратнее.')
        facts = ai_context.student_facts(uid)
        try:
            text = await adelia_ai.rewrite_message(
                draft=draft['text'], instruction=instruction,
                recipient_type='родитель' if draft.get('target') == 'PARENTS' else 'ученик',
                facts=facts,
            )
        except Exception:
            await q.answer('Не удалось переделать черновик. Попробуйте ещё раз.', show_alert=True)
            return ConversationHandler.END
        await _show_draft(q, context, uid, text, draft.get('target', 'STUDENT'), 'AI')
        return ConversationHandler.END

    if d.startswith('mh_senddraft|'):
        uid = int(d.split('|')[1])
        draft = context.user_data.get('mh_ai_draft') or {}
        if int(draft.get('uid') or 0) != uid or not draft.get('text'):
            await q.answer('Черновик устарел. Подготовьте его заново.', show_alert=True)
            return ConversationHandler.END
        target = draft.get('target', 'STUDENT')
        result = await messenger.send_teacher_message(context, uid, draft['text'], q.from_user.id, target)
        context.user_data.pop('mh_ai_draft', None)
        if result.get('status') == 'QUEUED':
            text = '🌙 Сообщение поставлено в очередь до часов приёма.'
        elif result.get('sent'):
            text = f"✅ Я отправила сообщение {_recipient_label(target)}."
        else:
            text = '⚠️ Telegram не подтвердил доставку сообщения.'
        await _edit(q, text, InlineKeyboardMarkup([
            [InlineKeyboardButton('👤 К ученику', callback_data=f'admin_student|{uid}')],
            [InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')],
        ]))
        return ConversationHandler.END

    if d.startswith('mh_history|'):
        uid = int(d.split('|')[1])
        user = _student(uid)
        lessons, msgs = _history(uid)
        lines = [f"📜 ИСТОРИЯ • {user['name'] if user else uid}", '', 'Последние занятия:']
        for r in lessons[:12]:
            lines.append(f"• {str(r['start_time'])[:16].replace('T', ' ')} · {r['lesson_status']} · {r['payment_status']}")
        if not lessons:
            lines.append('• Пока нет занятий.')
        if msgs:
            lines += ['', 'Последние сообщения:'] + [
                f"• {'←' if r['direction']=='IN' else '→'} {str(r['created_at'])[5:16]} · {str(r['body'])[:100]}" for r in msgs
            ]
        await _edit(q, '\n'.join(lines), InlineKeyboardMarkup([
            [InlineKeyboardButton('💬 Написать', callback_data=f'mh_write|{uid}')],
            [InlineKeyboardButton('👤 К ученику', callback_data=f'admin_student|{uid}')],
        ]))
        return ConversationHandler.END

    return ConversationHandler.END


async def _ai_route(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if str(database.get_setting('ai_student_drafts_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
        return False
    try:
        intent = await adelia_ai.interpret_admin_text(text)
    except Exception:
        return False

    kind = intent.get('intent', 'unknown')
    lines = ['💜 АДЕЛИЯ', '']
    kb = []

    if kind == 'show_debts':
        rows = _debts(20)
        lines.append('Вот кто сейчас требует внимания по оплате:')
        for r in rows:
            lines.append(f"• {r['name']} — {r['cnt']} зан. · {int(r['amount'] or 0):,} ₽".replace(',', ' '))
            kb.append([InlineKeyboardButton(r['name'], callback_data=f"admin_student|{r['id']}")])
        if not rows:
            lines.append('✅ Долгов по подтверждённым занятиям нет.')
    elif kind in ('show_attention', 'no_next_lesson'):
        rows = _attention()
        if kind == 'no_next_lesson':
            rows = [x for x in rows if any('Нет следующего' in r for r in x[2])]
        lines.append('Вот что я нашла:')
        for uid, name, reasons in rows[:25]:
            lines.append(f"• {name}: {', '.join(reasons)}")
            kb.append([InlineKeyboardButton(f'👤 {name}', callback_data=f'admin_student|{uid}')])
        if not rows:
            lines.append('✅ По этому запросу сейчас ничего нет.')
    elif kind in ('show_today', 'show_tomorrow'):
        if kind == 'show_today':
            dash = service.today_dashboard()
            rows, title = dash['lessons'], 'Сегодня'
        else:
            conn = database.connect()
            try:
                rows = conn.execute(
                    """SELECT l.start_time,u.name FROM lessons l JOIN users u ON u.id=l.user_id
                       WHERE date(l.start_time)=date('now','localtime','+1 day')
                       AND l.lesson_status NOT IN ('CANCELLED') ORDER BY datetime(l.start_time)"""
                ).fetchall()
            finally:
                conn.close()
            title = 'Завтра'
        lines.append(f'{title} занятий: {len(rows)}')
        lines += [f"• {str(r['start_time'])[11:16]} — {r['name']}" for r in rows]
    elif kind in ('search_student', 'student_status'):
        term = intent.get('query') or intent.get('student_name') or ''
        rows = ai_context.find_students(term)
        if not rows:
            lines.append(f'Не нашла ученика по запросу «{term}».')
        elif kind == 'student_status' and len(rows) == 1:
            uid = int(rows[0]['id'])
            lines += ai_context.student_facts(uid).splitlines()
            kb.append([InlineKeyboardButton('👤 Открыть карточку', callback_data=f'admin_student|{uid}')])
        else:
            lines.append(f'Нашла по запросу «{term}»:')
            for r in rows:
                lines.append('• ' + r['name'])
                kb.append([InlineKeyboardButton(f"👤 {r['name']}", callback_data=f"admin_student|{r['id']}")])
    elif kind.startswith('draft_'):
        term = (intent.get('student_name') or '').strip()
        rows = ai_context.find_students(term)
        if not term:
            lines.append('Поняла, что нужно подготовить сообщение, но не поняла, кому. Укажите имя ученика.')
        elif len(rows) != 1:
            lines.append(f'Нашла {len(rows)} вариантов по имени «{term}».' if rows else f'Не нашла ученика «{term}».')
            for r in rows:
                kb.append([InlineKeyboardButton(f"👤 {r['name']}", callback_data=f"admin_student|{r['id']}")])
        else:
            uid = int(rows[0]['id'])
            name = rows[0]['name']
            facts = ai_context.student_facts(uid)
            history = ai_context.recent_messages(uid)
            target = 'PARENTS' if intent.get('recipient') == 'parent' else 'STUDENT'
            try:
                draft = await adelia_ai.draft_message(
                    instruction=intent.get('instruction') or text,
                    recipient_name=name,
                    recipient_type='родитель' if target == 'PARENTS' else 'ученик',
                    facts=facts,
                    recent_messages=history,
                    tone=intent.get('tone') or 'friendly',
                )
            except Exception:
                lines.append('Не удалось подготовить черновик через ИИ. Попробуйте чуть позже.')
            else:
                context.user_data['mh_ai_draft'] = {'uid': uid, 'text': draft, 'target': target, 'source': 'AI'}
                lines += [f'Черновик для {name}:', '', draft, '', 'Ничего ещё не отправлено.']
                kb.append([InlineKeyboardButton('📨 Отправить', callback_data=f'mh_senddraft|{uid}')])
                kb.append([InlineKeyboardButton('✏️ Изменить', callback_data=f'mh_editdraft|{uid}')])
                kb.append([InlineKeyboardButton('👤 Открыть карточку', callback_data=f'admin_student|{uid}')])
    else:
        return False

    kb.append([InlineKeyboardButton('💜 Спросить ещё', callback_data='mh_ask')])
    kb.append([InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')])
    await update.message.reply_text('\n'.join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))
    return True


async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    text = (update.message.text or '').strip()
    low = text.lower()
    if await _ai_route(update, context, text):
        return ConversationHandler.END

    lines = ['💜 АДЕЛИЯ', '']
    kb = []
    if any(x in low for x in ('долж', 'долг', 'не оплат')):
        rows = _debts(20)
        lines.append('Вот кто сейчас требует внимания по оплате:')
        for r in rows:
            lines.append(f"• {r['name']} — {r['cnt']} зан. · {int(r['amount'] or 0):,} ₽".replace(',', ' '))
            kb.append([InlineKeyboardButton(r['name'], callback_data=f"admin_student|{r['id']}")])
        if not rows:
            lines.append('✅ Долгов по подтверждённым занятиям нет.')
    elif any(x in low for x in ('нет следующ', 'без следующ', 'не записан')):
        rows = [x for x in _attention() if any('Нет следующего' in r for r in x[2])]
        lines.append('Ученики без следующего занятия:')
        for uid, name, _ in rows:
            lines.append('• ' + name)
            kb.append([InlineKeyboardButton(f'📅 {name}', callback_data=f'admin_manual_for|{uid}')])
        if not rows:
            lines.append('✅ У активных учеников следующий урок назначен.')
    elif any(x in low for x in ('вниман', 'важн', 'проблем')):
        dash = service.today_dashboard()
        lines += [f"⚠️ Требуют внимания: {len(dash['attention'])}", f"💬 Сообщений: {dash['open_messages']}", f"💳 Неоплаченных: {dash['unpaid']}"]
        kb.append([InlineKeyboardButton('⚠️ Открыть список', callback_data='mh_attention')])
    elif 'завтра' in low:
        conn = database.connect()
        try:
            rows = conn.execute(
                """SELECT l.start_time,u.name FROM lessons l JOIN users u ON u.id=l.user_id
                   WHERE date(l.start_time)=date('now','localtime','+1 day')
                   AND l.lesson_status NOT IN ('CANCELLED') ORDER BY datetime(l.start_time)"""
            ).fetchall()
        finally:
            conn.close()
        lines.append(f'Завтра занятий: {len(rows)}')
        lines += [f"• {str(r['start_time'])[11:16]} — {r['name']}" for r in rows]
    elif any(x in low for x in ('сегодня', 'занят')):
        dash = service.today_dashboard()
        lines.append(f"Сегодня занятий: {len(dash['lessons'])}")
        lines += [f"• {str(r['start_time'])[11:16]} — {r['name']}" for r in dash['lessons']]
        kb.append([InlineKeyboardButton('🌅 Что важно сегодня', callback_data='crm_today')])
    elif low.startswith('найди ') or low.startswith('найти '):
        term = text.split(' ', 1)[1].strip()
        rows = ai_context.find_students(term, 15)
        lines.append(f'Нашла по запросу «{term}»:')
        for r in rows:
            lines.append('• ' + r['name'])
            kb.append([InlineKeyboardButton(f"👤 {r['name']}", callback_data=f"admin_student|{r['id']}")])
        if not rows:
            lines.append('Ничего не нашла.')
    else:
        lines += ['ИИ сейчас не ответил, но основные команды работают локально.', '', 'Попробуйте: «кто должен», «что сегодня», «что завтра», «у кого нет следующего занятия», «найди Иван».']
    kb.append([InlineKeyboardButton('💜 Спросить ещё', callback_data='mh_ask')])
    kb.append([InlineKeyboardButton('⬅️ Админка', callback_data='admin_main')])
    await update.message.reply_text('\n'.join(lines)[:3900], reply_markup=InlineKeyboardMarkup(kb))
    return ConversationHandler.END


async def manual_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    compose = context.user_data.get('mh_compose') or {}
    uid = int(compose.get('uid') or 0)
    if not uid:
        return ConversationHandler.END
    text = (update.message.text or '').strip()
    context.user_data['mh_ai_draft'] = {'uid': uid, 'text': text, 'target': compose.get('target', 'STUDENT'), 'source': 'MANUAL'}
    user = _student(uid)
    await update.message.reply_text(
        f"✍️ ПРЕДПРОСМОТР • {user['name'] if user else uid}\n\n{text}\n\nНичего ещё не отправлено.",
        reply_markup=_draft_keyboard(uid),
    )
    return ConversationHandler.END


async def ai_compose_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    compose = context.user_data.get('mh_compose') or {}
    uid = int(compose.get('uid') or 0)
    target = compose.get('target', 'STUDENT')
    user = _student(uid)
    if not uid or not user:
        return ConversationHandler.END
    instruction = (update.message.text or '').strip()
    facts = ai_context.student_facts(uid)
    history = ai_context.recent_messages(uid)
    if str(database.get_setting('ai_student_drafts_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
        await update.message.reply_text('⚠️ OpenRouter сейчас не подключён. Можно написать сообщение вручную.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✍️ Написать самому', callback_data=f'mh_write_manual|{uid}')], [InlineKeyboardButton('⬅️ К ученику', callback_data=f'admin_student|{uid}')]]))
        return ConversationHandler.END
    try:
        draft = await adelia_ai.draft_message(
            instruction=instruction,
            recipient_name=user['name'],
            recipient_type='родитель' if target == 'PARENTS' else 'ученик',
            facts=facts,
            recent_messages=history,
            tone='friendly',
        )
    except Exception as exc:
        await update.message.reply_text('⚠️ Аделия сейчас не смогла получить ответ от ИИ. Обычные функции бота продолжают работать.', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✍️ Написать самому', callback_data=f'mh_write_manual|{uid}')], [InlineKeyboardButton('⬅️ К ученику', callback_data=f'admin_student|{uid}')]]))
        return ConversationHandler.END
    context.user_data['mh_ai_draft'] = {'uid': uid, 'text': draft, 'target': target, 'source': 'AI'}
    await update.message.reply_text(
        f"💜 АДЕЛИЯ • ЧЕРНОВИК\n\n{draft}\n\nНичего ещё не отправлено.",
        reply_markup=_draft_keyboard(uid),
    )
    return ConversationHandler.END


async def student_ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    uid = int(context.user_data.get('mh_student_context') or 0)
    user = _student(uid)
    if not uid or not user:
        return ConversationHandler.END
    question = (update.message.text or '').strip()
    facts = ai_context.student_facts(uid)
    history = ai_context.recent_messages(uid)

    # If the request clearly asks to write a message, reuse the same safe drafting path.
    low = question.lower()
    if any(x in low for x in ('напиши', 'сообщени', 'скажи ему', 'скажи ей', 'напомни', 'подготовь')):
        target = 'PARENTS' if any(x in low for x in ('мам', 'пап', 'родител')) else 'STUDENT'
        if str(database.get_setting('ai_student_drafts_enabled','1')).lower() not in ('0','false','off','no') and adelia_ai.is_enabled():
            try:
                draft = await adelia_ai.draft_message(
                    instruction=question,
                    recipient_name=user['name'],
                    recipient_type='родитель' if target == 'PARENTS' else 'ученик',
                    facts=facts,
                    recent_messages=history,
                    tone='friendly',
                )
            except Exception:
                draft = None
            if draft:
                context.user_data['mh_ai_draft'] = {'uid': uid, 'text': draft, 'target': target, 'source': 'AI'}
                await update.message.reply_text(f"💜 АДЕЛИЯ • ЧЕРНОВИК\n\n{draft}\n\nНичего ещё не отправлено.", reply_markup=_draft_keyboard(uid))
                return ConversationHandler.END

    if str(database.get_setting('ai_student_drafts_enabled','1')).lower() not in ('0','false','off','no') and adelia_ai.is_enabled():
        try:
            answer = await adelia_ai.answer_student_question(
                question=question,
                recipient_name=user['name'],
                facts=facts,
                recent_messages=history,
            )
        except Exception:
            answer = None
    else:
        answer = None
    if not answer:
        answer = 'Вот проверенные данные из TutorBot:\n\n' + facts
    await update.message.reply_text(
        f"💜 АДЕЛИЯ • {user['name']}\n\n{answer}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton('💬 Написать', callback_data=f'mh_write|{uid}')],
            [InlineKeyboardButton('💜 Спросить ещё', callback_data=f'mh_student_ask|{uid}')],
            [InlineKeyboardButton('👤 К ученику', callback_data=f'admin_student|{uid}')],
        ]),
    )
    return ConversationHandler.END


async def edit_draft_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _admin(update.effective_user.id):
        return ConversationHandler.END
    uid = int(context.user_data.get('mh_edit_uid') or 0)
    draft = context.user_data.get('mh_ai_draft') or {}
    if not uid or int(draft.get('uid') or 0) != uid:
        return ConversationHandler.END
    instruction = (update.message.text or '').strip()
    facts = ai_context.student_facts(uid)
    if str(database.get_setting('ai_student_drafts_enabled','1')).lower() in ('0','false','off','no') or not adelia_ai.is_enabled():
        await update.message.reply_text('⚠️ ИИ сейчас не подключён. Исходный черновик сохранён.', reply_markup=_draft_keyboard(uid))
        return ConversationHandler.END
    try:
        text = await adelia_ai.rewrite_message(
            draft=draft['text'],
            instruction=instruction,
            recipient_type='родитель' if draft.get('target') == 'PARENTS' else 'ученик',
            facts=facts,
        )
    except Exception:
        await update.message.reply_text('⚠️ Не удалось изменить черновик. Исходный вариант сохранён.', reply_markup=_draft_keyboard(uid))
        return ConversationHandler.END
    context.user_data['mh_ai_draft'] = {'uid': uid, 'text': text, 'target': draft.get('target', 'STUDENT'), 'source': 'AI'}
    await update.message.reply_text(f"💜 АДЕЛИЯ • НОВЫЙ ЧЕРНОВИК\n\n{text}\n\nНичего ещё не отправлено.", reply_markup=_draft_keyboard(uid))
    return ConversationHandler.END


def handlers():
    entry_pattern = r'^(?:mh_ask|mh_write\|\d+|mh_write_manual\|\d+|mh_write_ai\|\d+|mh_write_parent_ai\|\d+|mh_student_ask\|\d+|mh_editdraft\|\d+)$'
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(callbacks, pattern=entry_pattern)],
        states={
            ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_text)],
            WRITE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_text)],
            WRITE_AI: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_compose_text)],
            STUDENT_ASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, student_ask_text)],
            EDIT_DRAFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_draft_text)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    return [conv, CallbackQueryHandler(callbacks, pattern=r'^mh_')]
