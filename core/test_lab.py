from __future__ import annotations
import os, sqlite3
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler
import database
from . import admin_roles

CHECKS = [
    ('registration','Регистрация ученика'), ('parent','Родитель'), ('messages','Сообщения'),
    ('booking','Запись'), ('reschedule','Перенос / обмен'), ('minutes','Минуты / оплата'),
    ('homework','Домашнее задание'), ('mock','Пробники'), ('navigation','Навигация / Главное меню'),
]
SCENARIOS = [
    'Новый ученик → регистрация → покупка минут → запись на занятие.',
    'Ученик пишет вне часов приёма → сообщение приходит позже с исходным временем.',
    'Перенос на занятый слот → обмен → подтверждение преподавателя.',
    'Во время занятия сообщения копятся → после урока приходит единый дайджест.',
    'Родитель смотрит прогресс → пишет преподавателю → получает ответ через TutorBot.',
]

def _prod():
    return database.connect_prod() if hasattr(database, 'connect_prod') else database.connect()

def ensure_schema():
    c=_prod(); c.executescript('''
    CREATE TABLE IF NOT EXISTS test_lab_sessions(
      telegram_id INTEGER PRIMARY KEY, active INTEGER NOT NULL DEFAULT 0,
      started_at TEXT, ended_at TEXT, last_role TEXT DEFAULT 'STUDENT'
    );
    CREATE TABLE IF NOT EXISTS test_lab_checks(
      code TEXT PRIMARY KEY, ok INTEGER NOT NULL DEFAULT 0, checked_at TEXT, checked_by INTEGER
    );
    CREATE TABLE IF NOT EXISTS test_lab_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, event_type TEXT,
      details TEXT, created_at TEXT NOT NULL
    );
    '''); c.commit(); c.close()

def _is_tester_prod(tid):
    c=_prod(); r=c.execute("SELECT 1 FROM admin_accounts WHERE telegram_id=? AND active=1 AND role='TESTER'",(int(tid),)).fetchone(); c.close(); return bool(r)

def active(tid):
    ensure_schema(); c=_prod(); r=c.execute('SELECT active FROM test_lab_sessions WHERE telegram_id=?',(int(tid),)).fetchone(); c.close(); return bool(r and r['active'])

def activate(tid):
    ensure_schema(); now=datetime.now().isoformat(timespec='seconds'); c=_prod()
    c.execute("INSERT INTO test_lab_sessions(telegram_id,active,started_at,last_role) VALUES(?,1,?,'STUDENT') ON CONFLICT(telegram_id) DO UPDATE SET active=1,started_at=excluded.started_at,ended_at=NULL",(int(tid),now)); c.commit(); c.close()
    log(tid,'START')

def deactivate(tid):
    ensure_schema(); c=_prod(); c.execute('UPDATE test_lab_sessions SET active=0,ended_at=? WHERE telegram_id=?',(datetime.now().isoformat(timespec='seconds'),int(tid))); c.commit(); c.close(); log(tid,'STOP')

def log(tid,kind,details=''):
    ensure_schema(); c=_prod(); c.execute('INSERT INTO test_lab_events(telegram_id,event_type,details,created_at) VALUES(?,?,?,?)',(int(tid) if tid else None,kind,details,datetime.now().isoformat(timespec='seconds'))); c.commit(); c.close()

def ensure_test_db():
    """Create *or upgrade* the persistent test sandbox to the current schema.

    The sandbox survives releases, so returning merely because tutor_test.db exists
    leaves it on an old schema.  Always run idempotent schema initializers while the
    database ContextVar points at TEST_DB_NAME.
    """
    os.makedirs(database.TEST_DATA_DIR, exist_ok=True)
    token = database._TEST_MODE.set(True)
    try:
        database.create_tables()
        from core import schema as core_schema
        from learning import schema as learning_schema
        from learning import formula_study, homework_flow
        from automation import schema as automation_schema
        from final_features import schema as final_schema
        from crm_plus import schema as crm_schema
        from ux_final import schema as ux_schema

        initializers = (
            core_schema.ensure_schema,
            learning_schema.initialize,
            formula_study.initialize,
            homework_flow.initialize,
            automation_schema.initialize,
            final_schema.initialize,
            crm_schema.initialize,
            ux_schema.initialize,
        )
        for fn in initializers:
            fn()

        # Seed defaults only when absent; do not overwrite a saved demo profile.
        if not database.get_setting('teacher_name', None):
            database.set_setting('teacher_name','Преподаватель')
        if not database.get_setting('teacher_description', None):
            database.set_setting('teacher_description','Тестовая область TutorBot')
    finally:
        database._TEST_MODE.reset(token)

def reset_sandbox():
    for suffix in ('','-wal','-shm'):
        path=database.TEST_DB_NAME+suffix
        try:
            if os.path.exists(path): os.remove(path)
        except OSError: pass
    ensure_test_db()

def sandbox_stats():
    ensure_test_db(); c=sqlite3.connect(database.TEST_DB_NAME); c.row_factory=sqlite3.Row
    def count(table):
        try: return int(c.execute(f'SELECT COUNT(*) n FROM {table}').fetchone()['n'])
        except Exception: return 0
    out={'users':count('users'),'parents':count('parents'),'lessons':count('lessons'),'messages':count('crm_student_messages')}; c.close(); return out

async def route_update(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tid=update.effective_user.id if update.effective_user else None
    use=bool(
        tid
        and active(tid)
        and (
            _is_tester_prod(tid)
            or admin_roles.is_owner(tid)
        )
    )
    database.set_test_mode(use)
    if use: ensure_test_db()

async def route_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await route_update(update,context)


def set_test_role(tid, role):
    role = str(role).upper()

    if role not in ("TEACHER", "STUDENT", "PARENT"):
        raise ValueError("Unknown test role")

    ensure_schema()
    c = _prod()

    c.execute(
        """
        INSERT INTO test_lab_sessions(
            telegram_id,
            active,
            started_at,
            last_role
        )
        VALUES(?,1,?,?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            active=1,
            last_role=excluded.last_role
        """,
        (
            int(tid),
            datetime.now().isoformat(timespec="seconds"),
            role,
        ),
    )

    c.commit()
    c.close()

    log(tid, "ROLE_CHANGE", role)


def get_test_role(tid):
    ensure_schema()
    c = _prod()

    row = c.execute(
        """
        SELECT last_role
        FROM test_lab_sessions
        WHERE telegram_id=?
        """,
        (int(tid),),
    ).fetchone()

    c.close()

    return (
        str(row["last_role"]).upper()
        if row and row["last_role"]
        else "STUDENT"
    )


def role_name(role):
    return {
        "TEACHER": "👨‍🏫 Как преподаватель",
        "STUDENT": "🎓 Как ученик",
        "PARENT": "👨‍👩‍👧 Как родитель",
    }.get(str(role).upper(), str(role))


def lab_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "👨‍🏫 Как преподаватель",
                callback_data="testlab_role_teacher"
            ),
            InlineKeyboardButton(
                "🎓 Как ученик",
                callback_data="testlab_role_student"
            ),
        ],
        [
            InlineKeyboardButton(
                "👨‍👩‍👧 Как родитель",
                callback_data="testlab_role_parent"
            ),
            InlineKeyboardButton(
                "👥 Тестировщики",
                callback_data="testlab_testers"
            ),
        ],
        [
            InlineKeyboardButton(
                "🟢 Активные сессии",
                callback_data="testlab_sessions"
            ),
            InlineKeyboardButton(
                "📋 Чек-лист релиза",
                callback_data="testlab_checks"
            ),
        ],
        [
            InlineKeyboardButton(
                "🎭 Сценарий дня",
                callback_data="testlab_scenario"
            ),
            InlineKeyboardButton(
                "📊 Тестовые данные",
                callback_data="testlab_stats"
            ),
        ],
        [
            InlineKeyboardButton(
                "🩺 Здоровье",
                callback_data="testlab_health"
            ),
            InlineKeyboardButton(
                "♻️ Сбросить песочницу",
                callback_data="testlab_reset_warn"
            ),
        ],
        [
            InlineKeyboardButton(
                "⬅️ Система",
                callback_data="core_main"
            ),
            InlineKeyboardButton(
                "🏠 Главное меню",
                callback_data="admin_main"
            ),
        ],
    ])


async def show_lab(q):
    st=sandbox_stats()
    tid = q.from_user.id
    role = get_test_role(tid) if active(tid) else None
    await q.edit_message_text(
        '🧪 ТЕСТОВЫЙ РЕЖИМ • ГАЙД\n\n'
        + (f'Текущий режим: {role_name(role)}\n\n' if role else '')
        + 'Все назначенные тестировщики работают в одной изолированной песочнице.\n'
        f"Тестовые ученики: {st['users']} · родители: {st['parents']} · занятия: {st['lessons']}\n\n"
        'Тестовые данные сохраняются между обновлениями и не попадают в production.', reply_markup=lab_menu())

async def _draw_checks(q):
    ensure_schema(); c=_prod(); state={r['code']:int(r['ok']) for r in c.execute('SELECT code,ok FROM test_lab_checks')}; c.close()
    done=sum(state.get(code,0) for code,_ in CHECKS); kb=[[InlineKeyboardButton(('✅ ' if state.get(code) else '⬜ ')+label,callback_data=f'testlab_check|{code}')] for code,label in CHECKS]
    kb.append([InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')])
    await q.edit_message_text(f'📋 ЧЕК-ЛИСТ РЕЛИЗА\n\nГотовность: {round(done/len(CHECKS)*100)}% · {done}/{len(CHECKS)}\n\nОтмечайте только реально пройденные сценарии.',reply_markup=InlineKeyboardMarkup(kb))

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; d=q.data or ''; tid=q.from_user.id
    database.set_test_mode(False)
    if not (admin_roles.is_admin_id(tid) or _is_tester_prod(tid)):
        await q.answer('Нет доступа',show_alert=True); return ConversationHandler.END
    await q.answer()
    if d=='testlab_main': await show_lab(q); return ConversationHandler.END
    if d=='testlab_role_teacher':
        if not (
            admin_roles.is_owner(tid)
            or _is_tester_prod(tid)
        ):
            await q.answer(
                'Нет доступа',
                show_alert=True
            )
            return ConversationHandler.END

        ensure_test_db()
        activate(tid)
        set_test_role(tid, 'TEACHER')
        database.set_test_mode(True)

        if admin_roles.is_owner(tid):
            try:
                await context.bot.send_message(
                    admin_roles.OWNER_ID,
                    "🧪 Тестовая сессия\n\n"
                    "Режим: 👨‍🏫 Преподаватель\n"
                    f"Время: {datetime.now().strftime('%d.%m %H:%M')}"
                )
            except Exception:
                pass

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👨‍🏫 Открыть админку",
                    callback_data="admin_main"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Сменить роль",
                    callback_data="testlab_main"
                ),
                InlineKeyboardButton(
                    "🚪 Завершить тест",
                    callback_data="testlab_exit"
                ),
            ],
        ])

        await q.edit_message_text(
            "🧪 ТЕСТОВАЯ ОБЛАСТЬ\n"
            "👨‍🏫 Режим: ПРЕПОДАВАТЕЛЬ\n\n"
            "База: TEST ✅\n"
            "Production: изолирован 🔒\n\n"
            "Теперь откройте тестовую админку.",
            reply_markup=kb
        )
        return ConversationHandler.END

    if d=='testlab_role_student':
        if not (
            admin_roles.is_owner(tid)
            or _is_tester_prod(tid)
        ):
            await q.answer('Нет доступа', show_alert=True)
            return ConversationHandler.END

        ensure_test_db()
        activate(tid)
        set_test_role(tid, 'STUDENT')
        database.set_test_mode(True)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👨‍🎓 Войти как ученик",
                    callback_data="global_home"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Сменить роль",
                    callback_data="testlab_main"
                ),
                InlineKeyboardButton(
                    "🚪 Завершить тест",
                    callback_data="testlab_exit"
                ),
            ],
        ])

        await q.edit_message_text(
            "🧪 ТЕСТОВАЯ ОБЛАСТЬ\n"
            "👨‍🎓 Режим: УЧЕНИК\n\n"
            "Если тестовый профиль уже создан — "
            "откроется его меню.\n"
            "Если профиля нет — отправьте /start "
            "и пройдите регистрацию как новый ученик.",
            reply_markup=kb
        )
        return ConversationHandler.END

    if d=='testlab_role_parent':
        if not (
            admin_roles.is_owner(tid)
            or _is_tester_prod(tid)
        ):
            await q.answer('Нет доступа', show_alert=True)
            return ConversationHandler.END

        ensure_test_db()
        activate(tid)
        set_test_role(tid, 'PARENT')
        database.set_test_mode(True)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "👨‍👩‍👧 Открыть тестовый профиль",
                    callback_data="global_home"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔄 Сменить роль",
                    callback_data="testlab_main"
                ),
                InlineKeyboardButton(
                    "🚪 Завершить тест",
                    callback_data="testlab_exit"
                ),
            ],
        ])

        await q.edit_message_text(
            "🧪 ТЕСТОВАЯ ОБЛАСТЬ\n"
            "👨‍👩‍👧 Режим: РОДИТЕЛЬ\n\n"
            "Если тестовый родитель ещё не зарегистрирован, "
            "отправьте /start и пройдите регистрацию.",
            reply_markup=kb
        )
        return ConversationHandler.END

    if d=='testlab_begin':
        if not _is_tester_prod(tid): await q.answer('Тестовый доступ не назначен владельцем.',show_alert=True); return ConversationHandler.END
        ensure_test_db(); activate(tid)
        if admin_roles.OWNER_ID:
            try: await context.bot.send_message(admin_roles.OWNER_ID,f'🧪 Начато тестирование\n\nТестировщик: {q.from_user.full_name}\nID: {tid}\nВремя: {datetime.now().strftime("%d.%m %H:%M")}\n\nОткрыть область: /testlab')
            except Exception: pass
        await q.edit_message_text('🧪 ТЕСТОВАЯ СЕССИЯ АКТИВНА\n\nТеперь нажмите /start. Вы увидите сохранённый тестовый профиль либо обычную регистрацию нового пользователя.\n\nВсе тестировщики используют одну общую песочницу.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🚪 Завершить тестирование',callback_data='testlab_exit')]])); return ConversationHandler.END
    if d=='testlab_exit':
        deactivate(tid); database.set_test_mode(False); await q.edit_message_text('✅ Тестовая сессия завершена. Профиль сохранён для будущих обновлений.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏠 Админка',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_testers':
        c=_prod(); rows=c.execute("SELECT telegram_id,display_name FROM admin_accounts WHERE role='TESTER' AND active=1 ORDER BY display_name").fetchall(); c.close()
        text='👥 ТЕСТИРОВЩИКИ\n\n'+('\n'.join(f"🧪 {r['display_name'] or r['telegram_id']} · {r['telegram_id']}" for r in rows) if rows else 'Тестировщики не назначены.')+'\n\nНазначить: /addtester TELEGRAM_ID Имя\nОтозвать: /deltester TELEGRAM_ID'
        await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_sessions':
        c=_prod(); rows=c.execute("SELECT s.*,a.display_name FROM test_lab_sessions s LEFT JOIN admin_accounts a ON a.telegram_id=s.telegram_id WHERE s.active=1 ORDER BY s.started_at DESC").fetchall(); c.close()
        text='🟢 АКТИВНЫЕ СЕССИИ\n\n'+('\n'.join(f"• {r['display_name'] or r['telegram_id']} · с {str(r['started_at'])[11:16]}" for r in rows) if rows else 'Сейчас никто не тестирует.')
        await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_checks': await _draw_checks(q); return ConversationHandler.END
    if d.startswith('testlab_check|'):
        code=d.split('|',1)[1]; c=_prod(); r=c.execute('SELECT ok FROM test_lab_checks WHERE code=?',(code,)).fetchone(); new=0 if r and r['ok'] else 1
        c.execute('INSERT INTO test_lab_checks(code,ok,checked_at,checked_by) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET ok=excluded.ok,checked_at=excluded.checked_at,checked_by=excluded.checked_by',(code,new,datetime.now().isoformat(timespec='seconds'),tid)); c.commit(); c.close(); await _draw_checks(q); return ConversationHandler.END
    if d=='testlab_scenario':
        text='🎭 СЦЕНАРИЙ ДНЯ\n\n'+SCENARIOS[datetime.now().toordinal()%len(SCENARIOS)]+'\n\nОтыграйтесь разными тестировщиками в общей песочнице.'
        await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📋 Чек-лист',callback_data='testlab_checks')],[InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_stats':
        st=sandbox_stats(); await q.edit_message_text(f"📊 ТЕСТОВЫЕ ДАННЫЕ\n\nУченики: {st['users']}\nРодители: {st['parents']}\nЗанятия: {st['lessons']}\nСообщения: {st['messages']}\n\nОбласть общая для всех тестировщиков и сохраняется между релизами.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_health':
        v=os.statvfs(database.TEST_DATA_DIR); free=v.f_bavail*v.f_frsize; total=v.f_blocks*v.f_frsize
        try:
            c=sqlite3.connect(database.TEST_DB_NAME); integrity=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close()
        except Exception as exc: integrity=repr(exc)
        await q.edit_message_text(f'🩺 ЗДОРОВЬЕ ТЕСТОВОЙ ОБЛАСТИ\n\nБаза: {integrity}\nДиск: {(total-free)/1024**3:.1f}/{total/1024**3:.1f} ГБ\nСвободно: {free/1024**3:.1f} ГБ',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='testlab_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])); return ConversationHandler.END
    if d=='testlab_reset_warn':
        if not admin_roles.is_owner(tid): await q.answer('Только владелец.',show_alert=True); return ConversationHandler.END
        await q.edit_message_text('⚠️ Сбросить всю общую тестовую область?\n\nВсе тестовые профили и данные будут удалены. Production не затрагивается.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🗑 Сбросить',callback_data='testlab_reset_apply')],[InlineKeyboardButton('❌ Отмена',callback_data='testlab_main')]])); return ConversationHandler.END
    if d=='testlab_reset_apply':
        if admin_roles.is_owner(tid): reset_sandbox(); log(tid,'RESET_SANDBOX')
        await show_lab(q); return ConversationHandler.END
    return ConversationHandler.END

async def cmd_test(update:Update,context:ContextTypes.DEFAULT_TYPE):
    database.set_test_mode(False); tid=update.effective_user.id
    if not _is_tester_prod(tid):
        if admin_roles.is_admin_id(tid): await update.message.reply_text('🧪 Тестовый доступ не назначен владельцем.')
        return
    await update.message.reply_text('🧪 ТЕСТИРОВЩИК\n\nВаш тестовый профиль сохраняется между обновлениями. Все тестировщики работают в одной общей области.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🧪 Начать / продолжить',callback_data='testlab_begin')],[InlineKeyboardButton('🏠 Админка',callback_data='admin_main')]]))

async def cmd_lab(update:Update,context:ContextTypes.DEFAULT_TYPE):
    database.set_test_mode(False)
    if admin_roles.is_admin_id(update.effective_user.id):
        st=sandbox_stats(); await update.message.reply_text(f"🧪 ОБЩАЯ ТЕСТОВАЯ ОБЛАСТЬ\n\nТестовые ученики: {st['users']} · родители: {st['parents']} · занятия: {st['lessons']}",reply_markup=lab_menu())

async def addtester(update:Update,context:ContextTypes.DEFAULT_TYPE):
    database.set_test_mode(False); uid=update.effective_user.id
    if not admin_roles.is_owner(uid): await update.message.reply_text('🔒 Только владелец назначает тестировщиков.'); return
    if not context.args: await update.message.reply_text('Использование: /addtester TELEGRAM_ID Имя'); return
    try: target=int(context.args[0])
    except ValueError: await update.message.reply_text('Telegram ID должен быть числом.'); return
    name=' '.join(context.args[1:]) or f'Тестировщик {target}'; admin_roles.make_tester(target,name,uid); ensure_schema(); await update.message.reply_text(f'✅ {name} назначен администратором-тестировщиком.\nКоманда для него: /test')

async def deltester(update:Update,context:ContextTypes.DEFAULT_TYPE):
    database.set_test_mode(False); uid=update.effective_user.id
    if not admin_roles.is_owner(uid) or not context.args: return
    try:
        target=int(context.args[0]); deactivate(target); admin_roles.make_admin(target,uid); await update.message.reply_text('✅ Тестовый доступ отозван. Пользователь снова обычный администратор.')
    except Exception as exc: await update.message.reply_text(f'Не удалось: {exc}')

def management_handlers():
    return [CommandHandler('test',cmd_test),CommandHandler('testlab',cmd_lab),CommandHandler('addtester',addtester),CommandHandler('deltester',deltester),CallbackQueryHandler(callbacks,pattern=r'^testlab_')]
