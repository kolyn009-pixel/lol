from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes
from . import admin_roles, audit_log, analytics, backup_manager, diagnostics, event_center, maintenance, exporter, financial_ledger
import database



def _registered_people():
    conn = database.connect()
    rows = conn.execute("""
        SELECT id, name, telegram_id
        FROM users
        WHERE active=1
          AND telegram_id IS NOT NULL
        ORDER BY name COLLATE NOCASE
    """).fetchall()
    conn.close()
    return rows


def _role_text(tid):
    tid = int(tid)

    if admin_roles.is_owner(tid):
        return "👑 Владелец"

    if admin_roles.is_tester(tid):
        return "🧪 Администратор-тестировщик"

    if admin_roles.is_admin_id(tid):
        return "🛡 Администратор"

    return "👤 Пользователь"


def _admins_screen():
    rows = admin_roles.list_admins()

    admins = [
        r for r in rows
        if r["role"] == "ADMIN"
    ]

    testers = [
        r for r in rows
        if r["role"] == "TESTER"
    ]

    owner = next(
        (
            r["display_name"] or str(r["telegram_id"])
            for r in rows
            if r["role"] == "OWNER"
        ),
        "Владелец"
    )

    text = (
        "👥 АДМИНИСТРАТОРЫ\n\n"
        f"👑 Владелец: {owner}\n"
        f"🛡 Администраторов: {len(admins)}\n"
        f"🧪 Тестировщиков: {len(testers)}\n\n"
        "Выберите действие."
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➕ Назначить",
                callback_data="core_admin_add"
            ),
            InlineKeyboardButton(
                "📋 Управление",
                callback_data="core_admin_manage"
            ),
        ],
        [
            InlineKeyboardButton(
                "🧪 Тестировщики",
                callback_data="core_admin_testers"
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

    return text, kb


def _people_menu(mode):
    rows = _registered_people()
    kb = []

    for r in rows[:50]:
        tid = int(r["telegram_id"])
        name = r["name"] or f"Пользователь #{r['id']}"

        if mode == "add":
            if (
                admin_roles.is_owner(tid)
                or admin_roles.is_admin_id(tid)
                or admin_roles.is_tester(tid)
            ):
                continue

            label = f"👤 {name}"

        else:
            label = f"{_role_text(tid)} · {name}"

        kb.append([
            InlineKeyboardButton(
                label[:60],
                callback_data=f"core_admin_person|{tid}"
            )
        ])

    if not kb:
        kb.append([
            InlineKeyboardButton(
                "— Подходящих пользователей нет —",
                callback_data="core_admins"
            )
        ])

    kb.append([
        InlineKeyboardButton(
            "⬅️ Администраторы",
            callback_data="core_admins"
        ),
        InlineKeyboardButton(
            "🏠 Главное меню",
            callback_data="admin_main"
        ),
    ])

    return InlineKeyboardMarkup(kb)


def menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('📥 Входящие',callback_data='core_events'), InlineKeyboardButton('💰 Финансы',callback_data='core_finance')],
        [InlineKeyboardButton('🧪 Диагностика',callback_data='core_diag'), InlineKeyboardButton('💾 Backup',callback_data='core_backup')],
        [InlineKeyboardButton('👥 Администраторы',callback_data='core_admins'), InlineKeyboardButton('🚧 Техработы',callback_data='core_maintenance')],
        [InlineKeyboardButton('📤 Excel-экспорт',callback_data='core_export'), InlineKeyboardButton('📜 Журнал',callback_data='core_audit')],
        [InlineKeyboardButton('🧪 Проверка интерфейса',callback_data='ux_ui_audit'), InlineKeyboardButton('🛠 Обслуживание',callback_data='core_service_tools')],
        [InlineKeyboardButton('🚀 Центр управления',callback_data='ff_main')],
        [InlineKeyboardButton('⬅️ Админка',callback_data='admin_main')],
    ])

async def command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not admin_roles.is_admin_id(update.effective_user.id): return
    admin_roles.touch(update.effective_user.id); await update.message.reply_text('🛡 СИСТЕМА И НАДЁЖНОСТЬ',reply_markup=menu())

async def callbacks(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; uid=update.effective_user.id
    if not admin_roles.is_admin_id(uid): await q.answer('Нет доступа',show_alert=True); return
    await q.answer(); admin_roles.touch(uid); data=q.data
    if data=='core_main': await q.edit_message_text('🛡 СИСТЕМА И НАДЁЖНОСТЬ',reply_markup=menu()); return
    back=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Назад',callback_data='core_main')]])
    if data=='core_events':
        event_center.refresh_automatic(); rows=event_center.open_events(); icons={'CRITICAL':'🔴','ACTION':'🟠','ATTENTION':'🟡','INFO':'🔵'}
        text='📥 ВХОДЯЩИЕ\n\n'+('\n\n'.join(f"{icons.get(r['priority'],'🔵')} {r['title']}\n{r['body'] or ''}" for r in rows[:20]) if rows else 'Ничего не требует внимания.')
        await q.edit_message_text(text[:3900],reply_markup=back); return
    if data.startswith('core_finance'):
        period=data.split('|')[1] if '|' in data else 'month'; s,e=analytics.period_bounds(period); st=analytics.financial_stats(s.isoformat(timespec='seconds') if s else None,e.isoformat(timespec='seconds') if e else None)
        text=(f"💰 ФИНАНСОВАЯ СТАТИСТИКА\n\n💳 Получено: {st['received']:,} ₽\n💰 Заработано: {st['earned']:,} ₽\n📦 Предоплачено, не отработано: {st['prepaid']:,} ₽\n\n✅ Проведено: {st['completed']}\n⏱ Минут: {st['minutes']}\n👥 Активных учеников: {st['active_users']}").replace(',',' ')
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('День',callback_data='core_finance|day'),InlineKeyboardButton('Неделя',callback_data='core_finance|week'),InlineKeyboardButton('Месяц',callback_data='core_finance|month')],[InlineKeyboardButton('Всё время',callback_data='core_finance|all')],[InlineKeyboardButton('⬅️ Назад',callback_data='core_main')]])
        try:
            await q.edit_message_text(text,reply_markup=kb)
        except BadRequest as exc:
            if "Message is not modified" not in str(exc):
                raise
        return
    if data=='core_diag':
        rows=diagnostics.run_checks(); text='🧪 ДИАГНОСТИКА\n\n'+'\n'.join(('✅' if ok else ('🔴' if sev=='CRITICAL' else '⚠️'))+f' {name}: {details}' for name,sev,ok,details in rows); audit_log.log('RUN_DIAGNOSTICS',uid,details={'problems':sum(not x[2] for x in rows)}); await q.edit_message_text(text[:3900],reply_markup=back); return
    if data=='core_backup':
        path=backup_manager.create_backup('manual',uid); backup_manager.prune(); audit_log.log('CREATE_BACKUP',uid,'backup',path); await context.bot.send_document(chat_id=uid,document=open(path,'rb'),caption='💾 Резервная копия tutor.db'); await q.edit_message_text('✅ Резервная копия создана и отправлена.',reply_markup=back); return
    if data=='core_export':
        path=exporter.create_excel(); audit_log.log('EXPORT_EXCEL',uid); await context.bot.send_document(chat_id=uid,document=open(path,'rb'),caption='📤 Экспорт TutorBot'); await q.edit_message_text('✅ Excel сформирован.',reply_markup=back); return
    if data=='core_maintenance':
        state=maintenance.enabled(); kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔴 Выключить' if state else '🟢 Включить',callback_data=f"core_maintenance_confirm|{0 if state else 1}")],[InlineKeyboardButton('⬅️ Назад',callback_data='core_main')]]); await q.edit_message_text(f"🚧 ТЕХНИЧЕСКИЕ РАБОТЫ\n\nСтатус: {'ВКЛЮЧЕНЫ' if state else 'выключены'}",reply_markup=kb); return
    if data.startswith('core_maintenance_confirm|'):
        new = data.split('|',1)[1] == '1'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Подтвердить',callback_data=f'core_maintenance_apply|{1 if new else 0}')],[InlineKeyboardButton('❌ Отмена',callback_data='core_maintenance')]])
        await q.edit_message_text(f"⚠️ {'Включить' if new else 'Выключить'} режим технических работ?",reply_markup=kb); return
    if data.startswith('core_maintenance_apply|'):
        new=data.split('|',1)[1]=='1'; maintenance.set_enabled(new); audit_log.log('MAINTENANCE_TOGGLE',uid,details={'enabled':new}); await q.edit_message_text(f"✅ Режим техработ {'включён' if new else 'выключен'}.",reply_markup=back); return
    if data=='core_service_tools':
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🧪 Тестовая область',callback_data='testlab_main'),InlineKeyboardButton('🚧 Техработы',callback_data='core_maintenance')],[InlineKeyboardButton('🧪 UI-проверка',callback_data='ux_ui_audit')],[InlineKeyboardButton('⬅️ Система',callback_data='core_main'),InlineKeyboardButton('🏠 Главное меню',callback_data='admin_main')]])
        await q.edit_message_text('🛠 ОБСЛУЖИВАНИЕ\n\nСлужебные инструменты владельца и администраторов.',reply_markup=kb);return
    if data=='core_admins':
        text, kb = _admins_screen()
        await q.edit_message_text(
            text,
            reply_markup=kb
        )
        return

    if data=='core_admin_add':
        if not admin_roles.is_owner(uid):
            await q.answer(
                '🔒 Только владелец может назначать администраторов.',
                show_alert=True
            )
            return

        await q.edit_message_text(
            '➕ НАЗНАЧИТЬ АДМИНИСТРАТОРА\n\n'
            'Выберите зарегистрированного пользователя:',
            reply_markup=_people_menu('add')
        )
        return

    if data=='core_admin_manage':
        if not admin_roles.is_owner(uid):
            await q.answer(
                '🔒 Только владелец управляет ролями.',
                show_alert=True
            )
            return

        await q.edit_message_text(
            '📋 УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ\n\n'
            'Выберите человека:',
            reply_markup=_people_menu('manage')
        )
        return

    if data=='core_admin_testers':
        if not admin_roles.is_owner(uid):
            await q.answer(
                '🔒 Только владелец управляет тестировщиками.',
                show_alert=True
            )
            return

        rows = admin_roles.list_admins()
        kb = []

        for r in rows:
            if r['role'] == 'OWNER':
                continue

            tid = int(r['telegram_id'])
            name = r['display_name'] or str(tid)

            icon = '🧪' if r['role'] == 'TESTER' else '🛡'

            kb.append([
                InlineKeyboardButton(
                    f"{icon} {name}"[:60],
                    callback_data=f"core_admin_person|{tid}"
                )
            ])

        if not kb:
            kb.append([
                InlineKeyboardButton(
                    '— Администраторов пока нет —',
                    callback_data='core_admins'
                )
            ])

        kb.append([
            InlineKeyboardButton(
                '⬅️ Администраторы',
                callback_data='core_admins'
            ),
            InlineKeyboardButton(
                '🏠 Главное меню',
                callback_data='admin_main'
            ),
        ])

        await q.edit_message_text(
            '🧪 ТЕСТИРОВЩИКИ\n\n'
            'Выберите администратора, которому нужно '
            'выдать или изменить тестовый доступ:',
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith('core_admin_person|'):
        if not admin_roles.is_owner(uid):
            await q.answer(
                '🔒 Только владелец управляет ролями.',
                show_alert=True
            )
            return

        tid = int(data.split('|', 1)[1])

        conn = database.connect()
        person = conn.execute(
            """
            SELECT id,name,telegram_id
            FROM users
            WHERE telegram_id=?
            LIMIT 1
            """,
            (tid,)
        ).fetchone()
        conn.close()

        if person:
            name = person['name'] or f"Пользователь #{person['id']}"
        else:
            # Админ может существовать ещё до регистрации как ученик.
            admin_row = next(
                (
                    r for r in admin_roles.list_admins()
                    if int(r['telegram_id']) == tid
                ),
                None
            )
            name = (
                admin_row['display_name']
                if admin_row and admin_row['display_name']
                else str(tid)
            )

        role = _role_text(tid)

        text = (
            f"👤 {name}\n\n"
            f"Текущая роль: {role}\n\n"
            "Выберите действие:"
        )

        kb = []

        if admin_roles.is_owner(tid):

            kb.append([
                InlineKeyboardButton(
                    '👑 Владелец — роль защищена',
                    callback_data='core_admins'
                )
            ])

        elif admin_roles.is_tester(tid):

            kb.append([
                InlineKeyboardButton(
                    '🛡 Оставить только администратором',
                    callback_data=f'core_admin_to_admin|{tid}'
                )
            ])

            kb.append([
                InlineKeyboardButton(
                    '🚫 Снять административный доступ',
                    callback_data=f'core_admin_revoke|{tid}'
                )
            ])

        elif admin_roles.is_admin_id(tid):

            kb.append([
                InlineKeyboardButton(
                    '🧪 Разрешить тестирование',
                    callback_data=f'core_admin_to_tester|{tid}'
                )
            ])

            kb.append([
                InlineKeyboardButton(
                    '🚫 Снять администратора',
                    callback_data=f'core_admin_revoke|{tid}'
                )
            ])

        else:

            kb.append([
                InlineKeyboardButton(
                    '🛡 Сделать администратором',
                    callback_data=f'core_admin_create|{tid}'
                )
            ])

            kb.append([
                InlineKeyboardButton(
                    '🧪 Администратор + тестировщик',
                    callback_data=f'core_admin_create_tester|{tid}'
                )
            ])

        kb.append([
            InlineKeyboardButton(
                '⬅️ Назад',
                callback_data='core_admins'
            ),
            InlineKeyboardButton(
                '🏠 Главное меню',
                callback_data='admin_main'
            ),
        ])

        await q.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    if data.startswith('core_admin_create|'):
        if not admin_roles.is_owner(uid):
            await q.answer('🔒 Только владелец.', show_alert=True)
            return

        tid = int(data.split('|', 1)[1])

        conn = database.connect()
        person = conn.execute(
            'SELECT name FROM users WHERE telegram_id=? LIMIT 1',
            (tid,)
        ).fetchone()
        conn.close()

        name = (
            person['name']
            if person and person['name']
            else f"Администратор {tid}"
        )

        admin_roles.add_admin(
            tid,
            name,
            uid
        )

        audit_log.log(
            'ADD_ADMIN',
            uid,
            'admin',
            tid,
            {'name': name}
        )

        await q.answer('✅ Администратор назначен.')
        text, kb = _admins_screen()
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith('core_admin_create_tester|'):
        if not admin_roles.is_owner(uid):
            await q.answer('🔒 Только владелец.', show_alert=True)
            return

        tid = int(data.split('|', 1)[1])

        conn = database.connect()
        person = conn.execute(
            'SELECT name FROM users WHERE telegram_id=? LIMIT 1',
            (tid,)
        ).fetchone()
        conn.close()

        name = (
            person['name']
            if person and person['name']
            else f"Тестировщик {tid}"
        )

        admin_roles.make_tester(
            tid,
            name,
            uid
        )

        audit_log.log(
            'ADD_TESTER',
            uid,
            'admin',
            tid,
            {'name': name}
        )

        try:
            await context.bot.send_message(
                tid,
                '🧪 Вам предоставлен доступ '
                'администратора-тестировщика TutorBot.\n\n'
                'Для входа в тестовую область используйте /test.'
            )
        except Exception:
            pass

        await q.answer('🧪 Администратор-тестировщик назначен.')

        text, kb = _admins_screen()
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith('core_admin_to_tester|'):
        if not admin_roles.is_owner(uid):
            await q.answer('🔒 Только владелец.', show_alert=True)
            return

        tid = int(data.split('|', 1)[1])

        conn = database.connect()
        person = conn.execute(
            'SELECT name FROM users WHERE telegram_id=? LIMIT 1',
            (tid,)
        ).fetchone()
        conn.close()

        name = (
            person['name']
            if person and person['name']
            else f"Тестировщик {tid}"
        )

        admin_roles.make_tester(
            tid,
            name,
            uid
        )

        audit_log.log(
            'ENABLE_TESTER',
            uid,
            'admin',
            tid,
            {}
        )

        try:
            await context.bot.send_message(
                tid,
                '🧪 Вам открыт доступ к общей тестовой области TutorBot.\n'
                'Используйте /test.'
            )
        except Exception:
            pass

        await q.answer('🧪 Тестовый доступ включён.')

        text, kb = _admins_screen()
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith('core_admin_to_admin|'):
        if not admin_roles.is_owner(uid):
            await q.answer('🔒 Только владелец.', show_alert=True)
            return

        tid = int(data.split('|', 1)[1])

        admin_roles.make_admin(
            tid,
            uid
        )

        audit_log.log(
            'DISABLE_TESTER',
            uid,
            'admin',
            tid,
            {}
        )

        await q.answer(
            '✅ Тестовый доступ отключён. '
            'Администраторский доступ сохранён.'
        )

        text, kb = _admins_screen()
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data.startswith('core_admin_revoke|'):
        if not admin_roles.is_owner(uid):
            await q.answer('🔒 Только владелец.', show_alert=True)
            return

        tid = int(data.split('|', 1)[1])

        if admin_roles.is_owner(tid):
            await q.answer(
                '👑 Владельца снять нельзя.',
                show_alert=True
            )
            return

        admin_roles.revoke_admin(
            tid,
            uid
        )

        audit_log.log(
            'REVOKE_ADMIN',
            uid,
            'admin',
            tid,
            {}
        )

        await q.answer('✅ Административный доступ отозван.')

        text, kb = _admins_screen()
        await q.edit_message_text(text, reply_markup=kb)
        return

    if data=='core_audit':
        rows=audit_log.recent(20); text='📜 ЖУРНАЛ ДЕЙСТВИЙ\n\n'+('\n'.join(f"{r['created_at'][5:16]} · {r['actor_role'] or 'SYSTEM'} · {r['action']}" for r in rows) if rows else 'Журнал пуст.'); await q.edit_message_text(text[:3900],reply_markup=back); return

async def addadmin(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not admin_roles.is_owner(uid): await update.message.reply_text('🔒 Только владелец может добавлять администраторов.'); return
    if not context.args: await update.message.reply_text('Использование: /addadmin TELEGRAM_ID Имя'); return
    try: target=int(context.args[0])
    except ValueError: await update.message.reply_text('Telegram ID должен быть числом.'); return
    name=' '.join(context.args[1:]) or f'Администратор {target}'; admin_roles.add_admin(target,name,uid); audit_log.log('ADD_ADMIN',uid,'admin',target,{'name':name}); await update.message.reply_text(f'✅ {name} добавлен как администратор.')

async def deladmin(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if not admin_roles.is_owner(uid): await update.message.reply_text('🔒 Только владелец может удалять администраторов.'); return
    if not context.args: await update.message.reply_text('Использование: /deladmin TELEGRAM_ID'); return
    try: target=int(context.args[0]); admin_roles.revoke_admin(target,uid)
    except Exception as e: await update.message.reply_text(f'Не удалось: {e}'); return
    audit_log.log('REVOKE_ADMIN',uid,'admin',target); await update.message.reply_text('✅ Доступ администратора отозван.')

def handlers():
    return [CommandHandler('system',command),CommandHandler('addadmin',addadmin),CommandHandler('deladmin',deladmin),CallbackQueryHandler(callbacks,pattern=r'^core_')]
