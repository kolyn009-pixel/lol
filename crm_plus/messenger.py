from __future__ import annotations

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from core import admin_roles
from automation import messaging
from . import service, schema


def _stamp(value):
    try:
        dt=datetime.fromisoformat(str(value))
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return str(value or '—')


def student_reply_markup(student_id:int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('↩️ Ответить преподавателю', callback_data=f'student_reply|{int(student_id)}')],
        [InlineKeyboardButton('💬 Открыть диалог', callback_data='student_chat')],
    ])


def admin_reply_markup(student_id:int, inbox_id:int|None=None):
    rows=[
        [InlineKeyboardButton('↩️ Ответить', callback_data=f'msg_reply|{int(student_id)}'),
         InlineKeyboardButton('👤 Карточка', callback_data=f'student_view|{int(student_id)}')],
        [InlineKeyboardButton('📅 Записать', callback_data=f'admin_manual_for|{int(student_id)}'),
         InlineKeyboardButton('📝 ДЗ', callback_data=f'student_homeworks|{int(student_id)}')],
    ]
    if inbox_id:
        rows.append([InlineKeyboardButton('✅ Отметить прочитанным',callback_data=f'msg_read|{int(student_id)}|{int(inbox_id)}')])
    return InlineKeyboardMarkup(rows)


def _mirror_vk(student_id:int, text:str):
    try:
        from vk_adapter.channel_delivery import send_vk
        return bool(send_vk(int(student_id), text))
    except Exception as exc:
        print('CRM VK MIRROR ERROR:',repr(exc))
        return False


async def notify_admins(context, student_id:int, body:str, created_at:str, inbox_id:int|None=None, delayed:bool=False):
    user=database.get_user(int(student_id))
    name=user['name'] if user else f'Ученик #{student_id}'
    prefix='💬 Новое сообщение' if not delayed else '💬 Отложенное сообщение'
    when=f"\n🕘 Написано: {_stamp(created_at)}" if delayed else ''
    text=f"{prefix} от {name}{when}\n\n{body}"
    for a in admin_roles.list_admins():
        if not a['active'] or not a['telegram_id']:
            continue
        try:
            await context.bot.send_message(int(a['telegram_id']), text, reply_markup=admin_reply_markup(student_id,inbox_id))
        except Exception:
            pass


def _notify_vk_teacher(student_id:int, body:str, delayed=False):
    try:
        from vk_adapter import app as vk_app, schema as vk_schema
        user=database.get_user(int(student_id))
        name=user['name'] if user else f'Ученик #{student_id}'
        prefix='💬 Новое сообщение' if not delayed else '💬 Отложенное сообщение'
        text=f"{prefix} от {name}\n\n{body}\n\nОткрой «💬 Сообщения» в меню преподавателя."
        for peer in vk_schema.get_admin_external_ids('VK'):
            vk_app.send(int(peer),text,linked=True,mode='teacher')
    except Exception as exc:
        print('CRM VK TEACHER NOTIFY ERROR:',repr(exc))


async def send_teacher_message(context, student_id:int, text:str, admin_id:int|None=None, target:str='STUDENT', force_now:bool=False):
    """Send or queue a teacher message. Returns a status dict."""
    schema.initialize()
    uid=int(student_id)
    target=target or 'STUDENT'
    quiet, send_at = service.quiet_state()
    if quiet and not force_now:
        mid=service.log_message(uid,'OUT',text,admin_id,target,'QUEUED',send_at.isoformat(timespec='seconds'))
        return {'status':'QUEUED','message_id':mid,'send_at':send_at,'sent':0}

    user=database.get_user(uid)
    sent=0
    student_text=f"👨‍🏫 Сообщение от преподавателя\n\n{text}"
    if target in ('STUDENT','ALL'):
        if user and user['telegram_id']:
            try:
                await context.bot.send_message(
                    int(user['telegram_id']),
                    student_text,
                    reply_markup=student_reply_markup(uid),
                )
                sent+=1
            except Exception:
                pass
        if _mirror_vk(uid,student_text):
            sent+=1
    if target in ('PARENTS','ALL'):
        for tid in service.parent_ids(uid):
            try:
                await context.bot.send_message(int(tid),f"👨‍🏫 Сообщение преподавателя\n\n{text}")
                sent+=1
            except Exception:
                pass
    mid=service.log_message(uid,'OUT',text,admin_id,target,'SENT' if sent else 'FAILED')
    return {'status':'SENT' if sent else 'FAILED','message_id':mid,'sent':sent,'send_at':None}


async def delivery_job(context):
    """Deliver queued inbound messages at reception hours and queued outbound messages after quiet hours."""
    schema.initialize()
    now=service.now().isoformat(timespec='seconds')
    conn=database.connect()
    try:
        inbound=conn.execute("SELECT * FROM crm_student_messages WHERE direction='IN' AND status='QUEUED' AND scheduled_for IS NOT NULL AND scheduled_for<=? ORDER BY created_at",(now,)).fetchall()
        outbound=conn.execute("SELECT * FROM crm_student_messages WHERE direction='OUT' AND status='QUEUED' AND scheduled_for IS NOT NULL AND scheduled_for<=? ORDER BY created_at",(now,)).fetchall()
    finally:
        conn.close()

    delivered_inbound=[]
    for row in inbound:
        accepting,next_at=service.inbound_delivery_state()
        if not accepting:
            conn=database.connect()
            try:
                conn.execute("UPDATE crm_student_messages SET scheduled_for=? WHERE id=?",(next_at.isoformat(timespec='seconds'),row['id']));conn.commit()
            finally:conn.close()
            continue
        inbox_id=row['inbox_id'] if 'inbox_id' in row.keys() else None
        conn=database.connect()
        try:
            conn.execute("UPDATE crm_student_messages SET status='DELIVERED', delivered_at=? WHERE id=?",(now,row['id']))
            if inbox_id:
                conn.execute("UPDATE teacher_inbox SET status='OPEN' WHERE id=?",(int(inbox_id),))
            conn.commit()
        finally:
            conn.close()
        delivered_inbound.append(row)

    if delivered_inbound:
        lines=['🔔 ПОКА ВЫ БЫЛИ ЗАНЯТЫ','',f'💬 Новых сообщений: {len(delivered_inbound)}','']
        for row in delivered_inbound[:8]:
            u=database.get_user(int(row['student_id'])); name=u['name'] if u else f"Ученик #{row['student_id']}"
            lines.append(f"• {name} · написано {_stamp(row['created_at'])}")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('💬 Открыть сообщения',callback_data='admin_student_messages')]])
        for a in admin_roles.list_admins():
            if not a['active'] or not a['telegram_id']:continue
            try: await context.bot.send_message(int(a['telegram_id']),'\n'.join(lines),reply_markup=kb)
            except Exception: pass
        for row in delivered_inbound:
            _notify_vk_teacher(int(row['student_id']),str(row['body']),delayed=True)

    for row in outbound:
        uid=int(row['student_id']); user=database.get_user(uid); sent=0; target=row['target'] or 'STUDENT'
        student_text=f"👨‍🏫 Сообщение от преподавателя\n\n{row['body']}"
        if target in ('STUDENT','ALL'):
            if user and user['telegram_id']:
                try:
                    await context.bot.send_message(int(user['telegram_id']),student_text,reply_markup=student_reply_markup(uid)); sent+=1
                except Exception: pass
            if _mirror_vk(uid,student_text): sent+=1
        if target in ('PARENTS','ALL'):
            for tid in service.parent_ids(uid):
                try: await context.bot.send_message(int(tid),f"👨‍🏫 Сообщение преподавателя\n\n{row['body']}"); sent+=1
                except Exception: pass
        conn=database.connect()
        try:
            conn.execute("UPDATE crm_student_messages SET status=?, sent_at=?, delivered_at=? WHERE id=?",('SENT' if sent else 'FAILED',now,now if sent else None,row['id']))
            conn.commit()
        finally: conn.close()
