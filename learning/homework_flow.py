from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, MessageHandler, ContextTypes, filters

import database
from core import admin_roles
from formula_library import FORMULA_LIBRARY
from ai_assistant import client as ai_client

DB = database


def _table_columns(c, table: str) -> set[str]:
    return {r['name'] for r in c.execute(f'PRAGMA table_info({table})').fetchall()}


def _ensure_column(c, table: str, column: str, ddl: str) -> None:
    if column not in _table_columns(c, table):
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}')


def initialize():
    c = DB.connect()
    try:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS homework_drafts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          admin_telegram_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          lesson_id INTEGER,
          description TEXT,
          subject TEXT,
          student_grade INTEGER,
          topic_grade INTEGER,
          topic_subject TEXT,
          topic_key TEXT,
          repeat_topics_json TEXT DEFAULT '[]',
          formula_decision INTEGER,
          formula_topics_json TEXT DEFAULT '[]',
          deadline TEXT,
          review_ready INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'DRAFT',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS homework_attachments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          draft_id INTEGER,
          homework_id INTEGER,
          file_type TEXT NOT NULL,
          file_id TEXT NOT NULL,
          telegram_file_id TEXT,
          file_unique_id TEXT,
          file_name TEXT,
          caption TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS homework_topic_links(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          homework_id INTEGER NOT NULL,
          grade INTEGER NOT NULL,
          subject TEXT NOT NULL,
          topic TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'MAIN'
        );
        CREATE TABLE IF NOT EXISTS homework_formula_links(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          homework_id INTEGER NOT NULL,
          grade INTEGER NOT NULL,
          subject TEXT NOT NULL,
          topic TEXT NOT NULL,
          UNIQUE(homework_id,grade,subject,topic)
        );
        """)

        draft_columns = {
            'lesson_id': 'INTEGER',
            'description': 'TEXT',
            'subject': 'TEXT',
            'student_grade': 'INTEGER',
            'topic_grade': 'INTEGER',
            'topic_subject': 'TEXT',
            'topic_key': 'TEXT',
            'repeat_topics_json': "TEXT DEFAULT '[]'",
            'formula_decision': 'INTEGER',
            'formula_topics_json': "TEXT DEFAULT '[]'",
            'deadline': 'TEXT',
            'review_ready': 'INTEGER NOT NULL DEFAULT 0',
            'status': "TEXT NOT NULL DEFAULT 'DRAFT'",
            'created_at': 'TEXT',
            'updated_at': 'TEXT',
        }
        for name, ddl in draft_columns.items():
            _ensure_column(c, 'homework_drafts', name, ddl)

        attachment_columns = {
            'draft_id': 'INTEGER',
            'homework_id': 'INTEGER',
            'file_id': 'TEXT',
            'telegram_file_id': 'TEXT',
            'file_unique_id': 'TEXT',
            'file_name': 'TEXT',
            'caption': 'TEXT',
            'created_at': 'TEXT',
        }
        for name, ddl in attachment_columns.items():
            _ensure_column(c, 'homework_attachments', name, ddl)

        c.execute("UPDATE homework_drafts SET repeat_topics_json='[]' WHERE repeat_topics_json IS NULL")
        c.execute("UPDATE homework_drafts SET formula_topics_json='[]' WHERE formula_topics_json IS NULL")
        c.execute("UPDATE homework_drafts SET review_ready=0 WHERE review_ready IS NULL")
        c.execute("UPDATE homework_drafts SET status='DRAFT' WHERE status IS NULL OR status=''")
        c.execute("UPDATE homework_drafts SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL")
        c.execute("UPDATE homework_drafts SET updated_at=COALESCE(created_at,CURRENT_TIMESTAMP) WHERE updated_at IS NULL")
        c.execute("UPDATE homework_attachments SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL")
        # Pre-Stage-2 production databases stored Telegram ids in
        # telegram_file_id. Preserve that legacy column and backfill the new
        # canonical file_id additively so old and new code remain compatible.
        attachment_cols = _table_columns(c, 'homework_attachments')
        if 'telegram_file_id' in attachment_cols and 'file_id' in attachment_cols:
            c.execute("""
                UPDATE homework_attachments
                   SET file_id=telegram_file_id
                 WHERE (file_id IS NULL OR file_id='')
                   AND telegram_file_id IS NOT NULL
                   AND telegram_file_id<>''
            """)

        c.execute('CREATE INDEX IF NOT EXISTS idx_hw_drafts_admin ON homework_drafts(admin_telegram_id,status,updated_at)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_hw_attach_draft ON homework_attachments(draft_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_hw_attach_hw ON homework_attachments(homework_id)')
        c.commit()
    finally:
        c.close()


def _is_admin(update: Update) -> bool:
    return bool(update.effective_user and admin_roles.is_admin_id(update.effective_user.id))


def _draft(did: int):
    c=DB.connect()
    try:return c.execute('SELECT * FROM homework_drafts WHERE id=?',(int(did),)).fetchone()
    finally:c.close()


def _active_draft(admin_tid: int):
    c=DB.connect()
    try:return c.execute("SELECT * FROM homework_drafts WHERE admin_telegram_id=? AND status='DRAFT' ORDER BY updated_at DESC LIMIT 1",(int(admin_tid),)).fetchone()
    finally:c.close()


def _attachments(did=None, hid=None):
    c=DB.connect()
    try:
        if did is not None:return c.execute('SELECT * FROM homework_attachments WHERE draft_id=? ORDER BY id',(int(did),)).fetchall()
        return c.execute('SELECT * FROM homework_attachments WHERE homework_id=? ORDER BY id',(int(hid),)).fetchall()
    finally:c.close()


def _touch(did, **fields):
    if not fields:return
    fields['updated_at']=datetime.now().isoformat(timespec='seconds')
    c=DB.connect()
    try:
        c.execute('UPDATE homework_drafts SET '+','.join(f'{k}=?' for k in fields)+' WHERE id=?',(*fields.values(),int(did)))
        c.commit()
    finally:c.close()


def _new_draft(admin_tid, user_id, lesson_id=None):
    u=DB.get_user(int(user_id)); grade=None
    try: grade=int(str(u['grade']).split()[0])
    except Exception: pass
    subj=(u['main_subject'] if 'main_subject' in u.keys() else None) or 'PHYSICS'
    if subj not in ('PHYSICS','CHEMISTRY'): subj='PHYSICS'
    c=DB.connect()
    try:
        c.execute("UPDATE homework_drafts SET status='ABANDONED',updated_at=CURRENT_TIMESTAMP WHERE admin_telegram_id=? AND status='DRAFT'",(int(admin_tid),))
        cur=c.execute('INSERT INTO homework_drafts(admin_telegram_id,user_id,lesson_id,subject,student_grade) VALUES(?,?,?,?,?)',(int(admin_tid),int(user_id),int(lesson_id) if lesson_id else None,subj,grade))
        c.commit(); return cur.lastrowid
    finally:c.close()


def _progress(d):
    content=bool((d['description'] or '').strip() or _attachments(did=d['id']))
    topic=bool(d['topic_key'])
    formula=d['formula_decision'] is not None
    deadline=bool(d['deadline'])
    review=bool(d['review_ready'])
    return sum([content,topic,formula,deadline,review])*20


def _bar(p): return '█'*(p//10)+'░'*(10-p//10)


def _topic_item(g,s,t):
    try:return FORMULA_LIBRARY[int(g)][s][t]
    except Exception:return None


def _topic_title(g,s,t):
    x=_topic_item(g,s,t); return (x or {}).get('title') or t


def _draft_text(d, step):
    u=DB.get_user(d['user_id']); name=(u['name'] if u else 'Ученик')
    p=_progress(d)
    labels=['Задание','Тема','Формулы','Срок','Проверка']
    lines=[f'📝 ДЗ • {name}',f'{_bar(p)} {p}%', '', f'Шаг {step} из 5 • {labels[step-1]}']
    return '\n'.join(lines)


def _step1_markup(did):
    return InlineKeyboardMarkup([
      [InlineKeyboardButton('✍️ Ввести / изменить текст',callback_data=f'hw2_text|{did}')],
      [InlineKeyboardButton('📎 Добавить файл / фото',callback_data=f'hw2_file|{did}')],
      [InlineKeyboardButton('➡️ Далее',callback_data=f'hw2_step2|{did}')],
      [InlineKeyboardButton('❌ Отмена',callback_data=f'hw2_cancel|{did}')],
    ])


async def _show_step1(q,did):
    d=_draft(did); at=_attachments(did=did)
    extra='\n\n'
    if d['description']: extra+=f"✍️ Текст: {d['description'][:350]}\n"
    if at: extra+=f"📎 Вложений: {len(at)}\n"
    if not d['description'] and not at: extra+='Добавьте текст задания, фото или файл. Одного файла достаточно.'
    await q.edit_message_text(_draft_text(d,1)+extra,reply_markup=_step1_markup(did))


def _grade_rows(did, subject):
    grades=sorted(g for g,v in FORMULA_LIBRARY.items() if subject in v)
    rows=[]
    for i in range(0,len(grades),3):
        rows.append([InlineKeyboardButton(f'{g} класс',callback_data=f'hw2_grade|{did}|{subject}|{g}') for g in grades[i:i+3]])
    rows.append([InlineKeyboardButton('⬅️ К заданию',callback_data=f'hw2_step1|{did}')])
    return InlineKeyboardMarkup(rows)


async def _show_step2(q,did):
    d=_draft(did)
    if not ((d['description'] or '').strip() or _attachments(did=did)):
        await q.answer('Сначала добавьте текст, фото или файл.',show_alert=True); return await _show_step1(q,did)
    sg=d['student_grade'] or '—'; subj=d['subject'] or 'PHYSICS'
    text=_draft_text(d,2)+f'\n\nУченик: {sg} класс\nВыберите класс материала. Текущий класс — только рекомендация; можно выбрать прошлые годы.'
    rows=[]
    if d['student_grade'] and int(d['student_grade']) in FORMULA_LIBRARY and subj in FORMULA_LIBRARY[int(d['student_grade'])]:
        rows.append([InlineKeyboardButton(f'🎓 {d["student_grade"]} класс — текущий',callback_data=f'hw2_grade|{did}|{subj}|{d["student_grade"]}')])
    rows += _grade_rows(did,subj).inline_keyboard[:-1]
    rows.append([InlineKeyboardButton('🔎 Найти тему',callback_data=f'hw2_topic_search|{did}')])
    rows.append([InlineKeyboardButton('💜 Определить тему с Аделией',callback_data=f'hw2_ai_topic|{did}')])
    rows.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step1|{did}')])
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(rows))


async def _show_topics(q,did,subject,grade):
    topics=FORMULA_LIBRARY.get(int(grade),{}).get(subject,{})
    rows=[]
    for key,item in topics.items():
        rows.append([InlineKeyboardButton((item.get('title') or key)[:55],callback_data=f'hw2_topic|{did}|{subject}|{grade}|{key}')])
    rows.append([InlineKeyboardButton('⬅️ К классам',callback_data=f'hw2_step2|{did}')])
    await q.edit_message_text(_draft_text(_draft(did),2)+f'\n\n🎓 {grade} класс\nВыберите тему:',reply_markup=InlineKeyboardMarkup(rows))


async def _show_step3(q,did):
    d=_draft(did)
    if not d['topic_key']: return await _show_step2(q,did)
    title=_topic_title(d['topic_grade'],d['topic_subject'],d['topic_key'])
    selected=json.loads(d['formula_topics_json'] or '[]')
    mark='✅' if d['formula_decision']==1 else '⬜'
    text=_draft_text(d,3)+f'\n\n📚 {d["topic_grade"]} класс • {title}\n\nДобавить формулы к этому ДЗ?\nСейчас: {mark} ' + ('добавляем' if d['formula_decision']==1 else 'не выбрано' if d['formula_decision'] is None else 'без формул')
    rows=[
      [InlineKeyboardButton('🔁 Добавить тему на повторение',callback_data=f'hw2_repeat_grades|{did}')],
      [InlineKeyboardButton('✅ Добавить формулы',callback_data=f'hw2_formula_yes|{did}'),InlineKeyboardButton('⬜ Без формул',callback_data=f'hw2_formula_no|{did}')],
    ]
    if d['formula_decision']==1:
        rows.append([InlineKeyboardButton(('☑ ' if selected else '☐ ')+title[:40],callback_data=f'hw2_formula_toggle|{did}|{d["topic_grade"]}|{d["topic_subject"]}|{d["topic_key"]}')])
        rows.append([InlineKeyboardButton('🔎 Найти формулу',callback_data=f'hw2_formula_search|{did}')])
        rows.append([InlineKeyboardButton('🎓 Добавить из другого класса',callback_data=f'hw2_formula_grades|{did}')])
    rows += [[InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step2|{did}'),InlineKeyboardButton('➡️ Далее',callback_data=f'hw2_step4|{did}')]]
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(rows))


async def _show_step4(q,did):
    d=_draft(did)
    if d['formula_decision'] is None:
        await q.answer('Выберите: добавить формулы или без формул.',show_alert=True); return await _show_step3(q,did)
    rows=[
      [InlineKeyboardButton('📅 До следующего занятия',callback_data=f'hw2_deadline|{did}|next')],
      [InlineKeyboardButton('Завтра',callback_data=f'hw2_deadline|{did}|1'),InlineKeyboardButton('Через 3 дня',callback_data=f'hw2_deadline|{did}|3')],
      [InlineKeyboardButton('Без срока',callback_data=f'hw2_deadline|{did}|none')],
      [InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step3|{did}')],
    ]
    current=d['deadline'] or 'не выбран'
    await q.edit_message_text(_draft_text(d,4)+f'\n\nТекущий срок: {current}\n\nВыберите срок:',reply_markup=InlineKeyboardMarkup(rows))


def _next_lesson_deadline(user_id, lesson_id=None):
    c=DB.connect()
    try:
        params=[int(user_id),datetime.now().isoformat()]
        sql="SELECT start_time FROM lessons WHERE user_id=? AND start_time>? AND lesson_status NOT IN ('CANCELLED','COMPLETED')"
        if lesson_id:
            sql+=' AND id<>?';params.append(int(lesson_id))
        row=c.execute(sql+' ORDER BY start_time LIMIT 1',params).fetchone()
        return row['start_time'] if row else None
    finally:c.close()


async def _show_review(q,did):
    d=_draft(did); _touch(did,review_ready=1); d=_draft(did)
    u=DB.get_user(d['user_id']); at=_attachments(did=did); formulas=json.loads(d['formula_topics_json'] or '[]')
    title=_topic_title(d['topic_grade'],d['topic_subject'],d['topic_key']) if d['topic_key'] else '—'; repeats=json.loads(d['repeat_topics_json'] or '[]')
    lines=[_draft_text(d,5),'','━━━━━━━━━━━━',f'👤 {u["name"] if u else "Ученик"}',f'📚 Тема: {d["topic_grade"]} класс • {title}',f'🔁 Тем на повторение: {len(repeats)}',f'📝 Задание: {(d["description"] or "только вложение")[:500]}',f'📎 Вложений: {len(at)}',f'🧮 Формулы: {len(formulas) if d["formula_decision"] else 0}',f'📅 Срок: {"без срока" if d["deadline"]=="NO_DEADLINE" else (d["deadline"] or "не выбран")}','━━━━━━━━━━━━']
    rows=[[InlineKeyboardButton('✅ Отправить ученику',callback_data=f'hw2_send|{did}')],[InlineKeyboardButton('✏️ Задание',callback_data=f'hw2_step1|{did}'),InlineKeyboardButton('📚 Тема',callback_data=f'hw2_step2|{did}')],[InlineKeyboardButton('🧮 Формулы',callback_data=f'hw2_step3|{did}'),InlineKeyboardButton('📅 Срок',callback_data=f'hw2_step4|{did}')],[InlineKeyboardButton('❌ Отмена',callback_data=f'hw2_cancel|{did}')]]
    await q.edit_message_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup(rows))


async def callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; data=q.data or ''
    await q.answer()
    if data.startswith('homework_view|'):
        hid=int(data.split('|')[1]); return await _student_homework_panel(q,hid)
    if data.startswith('admin_homework|') or data.startswith('admin_homework_create|'):
        if not _is_admin(update): return
        lesson_id=int(data.split('|')[1]); lesson=DB.get_lesson(lesson_id)
        if not lesson: return await q.answer('Занятие не найдено',show_alert=True)
        did=_new_draft(update.effective_user.id,lesson['user_id'],lesson_id)
        return await _show_step1(q,did)
    if not data.startswith('hw2_'): return
    if data.startswith('hw2_do|'):
        hid=int(data.split('|')[1]); hw=DB.get_homework(hid); user=DB.get_user_by_telegram_id(update.effective_user.id) if update.effective_user else None
        if not hw or not user or int(hw['user_id'])!=int(user['id']): return
        at=_attachments(hid=hid)
        if at:
            a=at[0]
            if a['file_type']=='photo': await context.bot.send_photo(update.effective_chat.id,a['file_id'],caption=a['file_name'] or '📎 Задание')
            else: await context.bot.send_document(update.effective_chat.id,a['file_id'],caption=a['file_name'] or '📎 Задание')
            return await _student_controls(context,update.effective_chat.id,hid)
        return await _student_formula_panel(q,hid)
    if data.startswith('hw2_openfile|'):
        parts=data.split('|'); hid=int(parts[1]); aid=int(parts[2]); hw=DB.get_homework(hid)
        user=DB.get_user_by_telegram_id(update.effective_user.id) if update.effective_user else None
        if not hw or not user or int(hw['user_id'])!=int(user['id']): return
        c=DB.connect(); a=c.execute('SELECT * FROM homework_attachments WHERE id=? AND homework_id=?',(aid,hid)).fetchone();c.close()
        if not a:return
        if a['file_type']=='photo': await context.bot.send_photo(update.effective_chat.id,a['file_id'],caption=a['file_name'] or '📎 Задание')
        else: await context.bot.send_document(update.effective_chat.id,a['file_id'],caption=a['file_name'] or '📎 Задание')
        return await _student_controls(context,update.effective_chat.id,hid)
    if data.startswith('hw2_student_formula|'):
        hid=int(data.split('|')[1]); return await _student_formula_panel(q,hid)
    if data.startswith('hw2_student_formula_card|'):
        _,hid,g,s,t=data.split('|',4); return await _student_formula_card(q,int(hid),int(g),s,t)
    if data.startswith('hw2_student_formula_hide|'):
        hid=int(data.split('|')[1]); return await _student_homework_panel(q,hid)
    if not _is_admin(update): return
    parts=data.split('|'); action=parts[0]; did=int(parts[1]) if len(parts)>1 and parts[1].isdigit() else None
    if did and (not _draft(did) or int(_draft(did)['admin_telegram_id'])!=update.effective_user.id): return
    if action=='hw2_step1': return await _show_step1(q,did)
    if action=='hw2_text': context.user_data['hw2_wait']={'draft':did,'kind':'text'}; return await q.edit_message_text(_draft_text(_draft(did),1)+'\n\n✍️ Отправьте текст задания одним сообщением.\n\n[Черновик уже сохранён автоматически.]')
    if action=='hw2_file': context.user_data['hw2_wait']={'draft':did,'kind':'file'}; return await q.edit_message_text(_draft_text(_draft(did),1)+'\n\n📎 Отправьте документ или фото. Можно отправить несколько по одному. После каждого файла вернёмся сюда.')
    if action=='hw2_step2': return await _show_step2(q,did)
    if action=='hw2_grade': return await _show_topics(q,did,parts[2],int(parts[3]))
    if action=='hw2_topic':
        _,_,s,g,t=parts; _touch(did,topic_grade=int(g),topic_subject=s,topic_key=t,formula_topics_json='[]',formula_decision=None); return await _show_step3(q,did)
    if action=='hw2_repeat_grades': return await q.edit_message_text('🔁 ТЕМА НА ПОВТОРЕНИЕ\n\nВыберите класс материала.',reply_markup=_repeat_grade_markup(did))
    if action=='hw2_rgrade': return await _repeat_topic_picker(q,did,int(parts[2]),_draft(did)['subject'])
    if action=='hw2_rtopic':
        _,_,g,s,t=parts; d=_draft(did); arr=json.loads(d['repeat_topics_json'] or '[]'); key=f'{g}|{s}|{t}';
        if key not in arr: arr.append(key)
        _touch(did,repeat_topics_json=json.dumps(arr,ensure_ascii=False)); return await _show_step3(q,did)
    if action=='hw2_topic_search': context.user_data['hw2_wait']={'draft':did,'kind':'topic_search'}; return await q.edit_message_text('🔎 ПОИСК ТЕМЫ\n\nНапишите название: например «закон Ома» или «термодинамика».')
    if action=='hw2_formula_search': context.user_data['hw2_wait']={'draft':did,'kind':'formula_search'}; return await q.edit_message_text('🔎 ПОИСК ФОРМУЛЫ\n\nНапишите название, величину или формулу, например I = U/R.')
    if action=='hw2_formula_yes': _touch(did,formula_decision=1); return await _show_step3(q,did)
    if action=='hw2_formula_no': _touch(did,formula_decision=0,formula_topics_json='[]'); return await _show_step3(q,did)
    if action=='hw2_formula_toggle':
        _,_,g,s,t=parts; d=_draft(did); arr=json.loads(d['formula_topics_json'] or '[]'); key=f'{g}|{s}|{t}'; arr.remove(key) if key in arr else arr.append(key); _touch(did,formula_decision=1,formula_topics_json=json.dumps(arr,ensure_ascii=False)); return await _show_step3(q,did)
    if action=='hw2_formula_grades': return await q.edit_message_text('🧮 ФОРМУЛЫ • ВЫБЕРИТЕ КЛАСС\n\nМожно прикрепить формулу прошлых лет.',reply_markup=_formula_grade_markup(did))
    if action=='hw2_fgrade': return await _formula_topic_picker(q,did,int(parts[2]),_draft(did)['subject'])
    if action=='hw2_ftopic':
        _,_,g,s,t=parts; d=_draft(did);arr=json.loads(d['formula_topics_json'] or '[]');key=f'{g}|{s}|{t}';
        if key not in arr:arr.append(key)
        _touch(did,formula_decision=1,formula_topics_json=json.dumps(arr,ensure_ascii=False));return await _show_step3(q,did)
    if action=='hw2_step4': return await _show_step4(q,did)
    if action=='hw2_deadline':
        choice=parts[2]; d=_draft(did)
        if choice=='next': val=_next_lesson_deadline(d['user_id'],d['lesson_id']) or (datetime.now()+timedelta(days=7)).isoformat(timespec='minutes')
        elif choice=='none': val='NO_DEADLINE'
        else: val=(datetime.now()+timedelta(days=int(choice))).replace(hour=20,minute=0,second=0,microsecond=0).isoformat()
        _touch(did,deadline=val); return await _show_review(q,did)
    if action=='hw2_review': return await _show_review(q,did)
    if action=='hw2_ai_topic': return await _ai_topic(q,did,context)
    if action=='hw2_ai_use':
        _,_,g,s,t=parts;_touch(did,topic_grade=int(g),topic_subject=s,topic_key=t,formula_decision=None,formula_topics_json='[]');return await _show_step3(q,did)
    if action=='hw2_send': return await _finalize(q,did,context)
    if action=='hw2_cancel': _touch(did,status='CANCELLED'); return await q.edit_message_text('❌ Черновик ДЗ отменён.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏠 Главная',callback_data='admin_main')]]))


def _repeat_grade_markup(did):
    rows=[]
    for i in range(7,12,3): rows.append([InlineKeyboardButton(f'{g} класс',callback_data=f'hw2_rgrade|{did}|{g}') for g in range(i,min(i+3,12))])
    rows.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step3|{did}')]); return InlineKeyboardMarkup(rows)

async def _repeat_topic_picker(q,did,g,s):
    topics=FORMULA_LIBRARY.get(g,{}).get(s,{})
    rows=[[InlineKeyboardButton((v.get('title') or k)[:55],callback_data=f'hw2_rtopic|{did}|{g}|{s}|{k}')] for k,v in topics.items()]
    rows.append([InlineKeyboardButton('⬅️ К классам',callback_data=f'hw2_repeat_grades|{did}')])
    await q.edit_message_text(f'🔁 ПОВТОРЕНИЕ • {g} КЛАСС\n\nВыберите тему:',reply_markup=InlineKeyboardMarkup(rows))

def _search_topics(query, subject=None, limit=12):
    q=(query or '').lower().replace('ё','е'); out=[]
    for g,subs in FORMULA_LIBRARY.items():
        for s,topics in subs.items():
            if subject and s!=subject: continue
            for t,item in topics.items():
                hay=((item.get('title') or '')+' '+(item.get('text') or '')).lower().replace('ё','е')
                score=sum(1 for token in q.split() if token in hay)
                if q in hay: score+=5
                if score: out.append((score,g,s,t,item.get('title') or t))
    return sorted(out,reverse=True)[:limit]

def _formula_grade_markup(did):
    rows=[]
    for i in range(7,12,3): rows.append([InlineKeyboardButton(f'{g} класс',callback_data=f'hw2_fgrade|{did}|{g}') for g in range(i,min(i+3,12))])
    rows.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step3|{did}')]);return InlineKeyboardMarkup(rows)


async def _formula_topic_picker(q,did,g,s):
    topics=FORMULA_LIBRARY.get(g,{}).get(s,{})
    rows=[[InlineKeyboardButton((v.get('title') or k)[:55],callback_data=f'hw2_ftopic|{did}|{g}|{s}|{k}')] for k,v in topics.items()]
    rows.append([InlineKeyboardButton('⬅️ К классам',callback_data=f'hw2_formula_grades|{did}')])
    await q.edit_message_text(f'🧮 ФОРМУЛЫ • {g} КЛАСС\n\nВыберите раздел формул:',reply_markup=InlineKeyboardMarkup(rows))


async def message(update:Update,context:ContextTypes.DEFAULT_TYPE):
    wait=(context.user_data or {}).get('hw2_wait')
    if not wait or not _is_admin(update): return
    did=int(wait['draft']); d=_draft(did)
    if not d:return
    if wait['kind'] in ('topic_search','formula_search') and update.message.text:
        results=_search_topics(update.message.text,_draft(did)['subject'])
        context.user_data.pop('hw2_wait',None)
        if not results: return await update.message.reply_text('Ничего не нашла. Попробуйте другое название.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('⬅️ Вернуться',callback_data=f'hw2_step2|{did}')]]))
        rows=[]
        for _,g,s,t,title in results:
            cb=f'hw2_topic|{did}|{s}|{g}|{t}' if wait['kind']=='topic_search' else f'hw2_ftopic|{did}|{g}|{s}|{t}'
            rows.append([InlineKeyboardButton(f'{g} кл. • {title}'[:58],callback_data=cb)])
        rows.append([InlineKeyboardButton('⬅️ Назад',callback_data=f'hw2_step2|{did}' if wait['kind']=='topic_search' else f'hw2_step3|{did}')])
        return await update.message.reply_text('🔎 НАЙДЕНО:',reply_markup=InlineKeyboardMarkup(rows))
    if wait['kind']=='text' and update.message.text:
        _touch(did,description=update.message.text.strip()); context.user_data.pop('hw2_wait',None)
        return await update.message.reply_text('💾 Текст сохранён.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Продолжить ДЗ',callback_data=f'hw2_step1|{did}')]]))
    if wait['kind']=='file':
        m=update.message; ftype=None; fid=None; uid=None; name=None
        if m.document: ftype='document';fid=m.document.file_id;uid=m.document.file_unique_id;name=m.document.file_name
        elif m.photo: ftype='photo';fid=m.photo[-1].file_id;uid=m.photo[-1].file_unique_id;name='Фото задания'
        if not fid:return await m.reply_text('Пришлите документ или фото.')
        c=DB.connect();c.execute('INSERT INTO homework_attachments(draft_id,file_type,file_id,telegram_file_id,file_unique_id,file_name,caption) VALUES(?,?,?,?,?,?,?)',(did,ftype,fid,fid,uid,name,m.caption));c.commit();c.close();context.user_data.pop('hw2_wait',None)
        return await m.reply_text('💾 Файл добавлен в черновик ДЗ.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('➕ Ещё файл',callback_data=f'hw2_file|{did}')],[InlineKeyboardButton('▶️ Продолжить',callback_data=f'hw2_step1|{did}')]]))


async def _ai_topic(q,did,context):
    d=_draft(did); at=_attachments(did=did); evidence=(d['description'] or '')+'\n'+'\n'.join((a['file_name'] or '')+' '+(a['caption'] or '') for a in at)
    # Extract text from PDFs when Telegram lets us download them. This is optional;
    # failure simply falls back to the assignment text/file name.
    for a in at[:2]:
        if a['file_type']=='document' and (a['file_name'] or '').lower().endswith('.pdf'):
            try:
                tg=await context.bot.get_file(a['file_id'])
                with NamedTemporaryFile(suffix='.pdf',delete=True) as tmp:
                    await tg.download_to_drive(tmp.name)
                    from pypdf import PdfReader
                    evidence+='\n'+'\n'.join((p.extract_text() or '') for p in PdfReader(tmp.name).pages[:5])[:8000]
            except Exception: pass
    if not evidence.strip(): return await q.edit_message_text('💜 Я не смогла получить текст из этого задания. Выберите тему вручную.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📚 Выбрать вручную',callback_data=f'hw2_step2|{did}')]]))
    candidates=[]
    for g,subs in FORMULA_LIBRARY.items():
        for s,topics in subs.items():
            for t,item in topics.items(): candidates.append(f'{g}|{s}|{t}|{item.get("title",t)}')
    prompt='Определи наиболее подходящую тему школьного ДЗ. Верни ровно одну строку из списка кандидатов, без пояснений.\nКАНДИДАТЫ:\n'+'\n'.join(candidates)+'\n\nДЗ:\n'+evidence[:9000]
    try:
        ans=await ai_client._chat_final([{'role':'system','content':'Ты классифицируешь ДЗ по школьной физике/химии. Не выдумывай тему.'},{'role':'user','content':prompt}],temperature=0,max_tokens=80)
        line=ans.strip().splitlines()[0].strip()
        match=next((x for x in candidates if x==line or x in ans),None)
        if not match: raise ValueError('no topic')
        g,s,t,title=match.split('|',3)
        return await q.edit_message_text(f'💜 Я думаю, это:\n\n📘 {"Физика" if s=="PHYSICS" else "Химия"}\n🎓 Материал: {g} класс\n📚 Тема: {title}\n\nЭто подсказка — тему подтверждаете вы.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Использовать',callback_data=f'hw2_ai_use|{did}|{g}|{s}|{t}')],[InlineKeyboardButton('✏️ Выбрать другую',callback_data=f'hw2_step2|{did}')]]))
    except Exception:
        return await q.edit_message_text('💜 Сейчас я не смогла уверенно определить тему. ДЗ сохранено — выберите тему вручную.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('📚 Выбрать тему',callback_data=f'hw2_step2|{did}')]]))


async def _finalize(q,did,context):
    d=_draft(did)
    if _progress(d)<100:return await _show_review(q,did)
    deadline=None if d['deadline']=='NO_DEADLINE' else d['deadline']
    u=DB.get_user(d['user_id']); subj=d['topic_subject'] or d['subject'] or 'PHYSICS'
    hid=DB.create_homework(d['user_id'],u['study_goal'] or 'GENERAL',subj,d['description'] or 'Задание во вложении',title=f'ДЗ • {_topic_title(d["topic_grade"],subj,d["topic_key"])}',lesson_id=d['lesson_id'],deadline=deadline)
    c=DB.connect()
    try:
        c.execute('UPDATE homework_attachments SET homework_id=?,draft_id=NULL WHERE draft_id=?',(hid,did))
        c.execute('INSERT INTO homework_topic_links(homework_id,grade,subject,topic,role) VALUES(?,?,?,?,?)',(hid,d['topic_grade'],subj,d['topic_key'],'MAIN'))
        for key in json.loads(d['repeat_topics_json'] or '[]'):
            g,rs,rt=key.split('|',2); c.execute('INSERT INTO homework_topic_links(homework_id,grade,subject,topic,role) VALUES(?,?,?,?,?)',(hid,int(g),rs,rt,'REVIEW'))
        for key in json.loads(d['formula_topics_json'] or '[]'):
            g,s,t=key.split('|',2);c.execute('INSERT OR IGNORE INTO homework_formula_links(homework_id,grade,subject,topic) VALUES(?,?,?,?)',(hid,int(g),s,t))
        c.execute("UPDATE homework_drafts SET status='SENT',updated_at=CURRENT_TIMESTAMP WHERE id=?",(did,));c.commit()
    finally:c.close()
    try:
        student=DB.get_user(d['user_id']); chat=student['telegram_id']
        await context.bot.send_message(chat,f'📝 НОВОЕ ДОМАШНЕЕ ЗАДАНИЕ\n\n📚 {_topic_title(d["topic_grade"],subj,d["topic_key"])}\n📅 Срок: {deadline or "без срока"}',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Открыть ДЗ',callback_data=f'homework_view|{hid}')]]))
    except Exception: pass
    await q.edit_message_text('✅ ДЗ отправлено ученику.\n\nЧерновик сохранён в истории, занятие отмечено как ДЗ задано.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('👤 Карточка ученика',callback_data=f'admin_student|{d["user_id"]}')],[InlineKeyboardButton('🏠 Главная',callback_data='admin_main')]]))


def _hw_links(hid):
    c=DB.connect()
    try:return c.execute('SELECT * FROM homework_formula_links WHERE homework_id=? ORDER BY id',(int(hid),)).fetchall()
    finally:c.close()


async def _student_homework_panel(q,hid):
    hw=DB.get_homework(hid); user=DB.get_user_by_telegram_id(q.from_user.id)
    if not hw or not user or int(hw['user_id'])!=int(user['id']):return
    at=_attachments(hid=hid); links=_hw_links(hid)
    lines=['📝 ДОМАШНЕЕ ЗАДАНИЕ','',hw['description'] or 'Задание во вложении']
    if hw['deadline']:lines+=['',f'⏰ Срок: {hw["deadline"]}']
    if at:lines+=['',f'📎 Файлов: {len(at)}']
    rows=[[InlineKeyboardButton('▶️ Делать ДЗ',callback_data=f'hw2_do|{hid}')]]
    for a in at:rows.append([InlineKeyboardButton(f'📂 Открыть {a["file_name"] or "файл"}'[:55],callback_data=f'hw2_openfile|{hid}|{a["id"]}')])
    rows.append([InlineKeyboardButton(f'🧮 Открыть формулы'+(f' ({len(links)})' if links else ''),callback_data=f'hw2_student_formula|{hid}')])
    rows.append([InlineKeyboardButton('⬅️ К ДЗ',callback_data='homework'),InlineKeyboardButton('🏠 Главная',callback_data='main')])
    await q.edit_message_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup(rows))


async def _student_controls(context,chat_id,hid):
    links=_hw_links(hid)
    rows=[[InlineKeyboardButton(f'🧮 Открыть формулы'+(f' ({len(links)})' if links else ''),callback_data=f'hw2_student_formula|{hid}')],[InlineKeyboardButton('📝 Вернуться к ДЗ',callback_data=f'homework_view|{hid}')]]
    await context.bot.send_message(chat_id,'📝 Задание открыто. Формулы доступны прямо здесь, под файлом.',reply_markup=InlineKeyboardMarkup(rows))


async def _student_formula_panel(q,hid):
    hw=DB.get_homework(hid); user=DB.get_user_by_telegram_id(q.from_user.id)
    if not hw or not user or int(hw['user_id'])!=int(user['id']):return
    links=_hw_links(hid); rows=[]; lines=['📝 ДОМАШНЕЕ ЗАДАНИЕ','',hw['description'] or 'Задание во вложении','','━━━━━━━━━━━━','🧮 ФОРМУЛЫ']
    if links:
        for x in links:
            title=_topic_title(x['grade'],x['subject'],x['topic']);lines.append(f'• {x["grade"]} класс • {title}');rows.append([InlineKeyboardButton(f'📖 {title}'[:55],callback_data=f'hw2_student_formula_card|{hid}|{x["grade"]}|{x["subject"]}|{x["topic"]}')])
    else: lines.append('Преподаватель не прикрепил отдельные формулы. Можно открыть общую библиотеку.')
    rows.append([InlineKeyboardButton('🔎 Найти любую формулу',callback_data='fh_search'),InlineKeyboardButton('🎓 По классам',callback_data='fh_home')])
    rows.append([InlineKeyboardButton('🔼 Скрыть формулы',callback_data=f'hw2_student_formula_hide|{hid}')])
    await q.edit_message_text('\n'.join(lines),reply_markup=InlineKeyboardMarkup(rows))


async def _student_formula_card(q,hid,g,s,t):
    item=_topic_item(g,s,t) or {}; text=item.get('text') or '—'; title=item.get('title') or t
    await q.edit_message_text(f'📝 ДЗ • ФОРМУЛА\n\n🧮 {title}\n🎓 {g} класс\n\n{text[:2800]}',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('◀️ К формулам ДЗ',callback_data=f'hw2_student_formula|{hid}')],[InlineKeyboardButton('📝 Вернуться к ДЗ',callback_data=f'homework_view|{hid}')]]))


def handlers():
    initialize()
    return [
      CallbackQueryHandler(callback,pattern=r'^(?:admin_homework\||admin_homework_create\||hw2_)'),
      MessageHandler((filters.TEXT|filters.Document.ALL|filters.PHOTO)&~filters.COMMAND,message),
    ]
