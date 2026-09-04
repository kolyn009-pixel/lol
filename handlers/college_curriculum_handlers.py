from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler

import database
import education_profile
import college_curriculum


def _is_college_user(update):
    tg=getattr(update,"effective_user",None)
    if not tg:return None
    user=database.get_user_by_telegram_id(int(tg.id))
    if not user:return None
    return user if education_profile.get(user)["type"]=="COLLEGE" else None


async def course(update,context):
    q=update.callback_query
    user=_is_college_user(update)
    if not q or not user:return
    await q.answer()
    c=int(q.data.split("|")[1])
    rows=[[InlineKeyboardButton(f"📖 {label}",callback_data=f"college_formula_subject|{c}|{key}")] for key,label in college_curriculum.subjects(c)]
    rows.append([InlineKeyboardButton("⬅️ К курсам",callback_data="formulas")])
    rows.append([InlineKeyboardButton("🏠 Главная",callback_data="main")])
    await q.edit_message_text(f"🎓 {college_curriculum.course_label(c)}\n\nВыбери предмет:",reply_markup=InlineKeyboardMarkup(rows))


async def subject(update,context):
    q=update.callback_query
    user=_is_college_user(update)
    if not q or not user:return
    await q.answer()
    _,c,s=q.data.split("|",2);c=int(c)
    rows=[[InlineKeyboardButton(title[:55],callback_data=f"college_formula_topic|{c}|{s}|{key}")] for key,title in college_curriculum.topics(c,s)]
    rows.append([InlineKeyboardButton("⬅️ К предметам",callback_data=f"college_formula_course|{c}")])
    rows.append([InlineKeyboardButton("🏠 Главная",callback_data="main")])
    await q.edit_message_text(f"🎓 {college_curriculum.course_label(c)} · {college_curriculum.SUBJECT_NAMES.get(s,s)}\n\nВыбери тему:",reply_markup=InlineKeyboardMarkup(rows))


async def topic(update,context):
    q=update.callback_query
    user=_is_college_user(update)
    if not q or not user:return
    await q.answer()
    _,c,s,t=q.data.split("|",3);c=int(c)
    text=college_curriculum.topic(c,s,t) or "Тема не найдена."
    rows=[[InlineKeyboardButton("⬅️ К темам",callback_data=f"college_formula_subject|{c}|{s}")],[InlineKeyboardButton("🏠 Главная",callback_data="main")]]
    await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup(rows))


def install(application):
    import __main__ as bot
    original=getattr(bot,"show_formula_grades",None)
    if callable(original) and not getattr(original,"_college_runtime",False):
        async def show_formula_grades(query,user):
            profile=education_profile.get(user)
            if profile["type"]!="COLLEGE":
                return await original(query,user)
            current=int(profile["level"] or 1)
            rows=[[InlineKeyboardButton(f"🎓 {college_curriculum.course_label(c)}",callback_data=f"college_formula_course|{c}")] for c in college_curriculum.courses(current)]
            rows.append([InlineKeyboardButton("⬅️ Главное меню",callback_data="main")])
            await query.edit_message_text(f"🧮 ФОРМУЛЫ И ТЕМЫ КОЛЛЕДЖА\n\n🎓 {profile['label']}\n\nТвой курс показан первым. Выбери курс:",reply_markup=InlineKeyboardMarkup(rows))
        show_formula_grades._college_runtime=True
        bot.show_formula_grades=show_formula_grades
    application.add_handler(CallbackQueryHandler(course,pattern=r"^college_formula_course\|"),group=-168)
    application.add_handler(CallbackQueryHandler(subject,pattern=r"^college_formula_subject\|"),group=-168)
    application.add_handler(CallbackQueryHandler(topic,pattern=r"^college_formula_topic\|"),group=-168)
