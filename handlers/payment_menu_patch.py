"""Install payment hub buttons into canonical TutorBot menus without duplicating menus."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

_installed = False


def _rewrite_parent(markup):
    if not markup:
        return markup
    rows=[]
    for row in markup.inline_keyboard:
        new=[]
        for button in row:
            if getattr(button,"text","") == "💳 Оплата":
                new.append(InlineKeyboardButton("💳 Оплата", callback_data="parent_payment_hub"))
            else:
                new.append(button)
        rows.append(new)
    return InlineKeyboardMarkup(rows)


def _rewrite_student(markup):
    if not markup:
        return markup
    rows=[list(r) for r in markup.inline_keyboard]
    exists=any(getattr(b,"callback_data",None)=="student_payment_hub" for r in rows for b in r)
    if not exists:
        # Keep payment visible on the home screen rather than hiding it under More.
        insert_at=min(2,len(rows))
        rows.insert(insert_at,[InlineKeyboardButton("💳 Оплата",callback_data="student_payment_hub")])
    return InlineKeyboardMarkup(rows)


def install():
    global _installed
    if _installed:
        return
    import bot
    original_parent=bot.parent_menu
    original_student=bot.student_menu

    def parent_menu(*args,**kwargs):
        return _rewrite_parent(original_parent(*args,**kwargs))

    def student_menu(*args,**kwargs):
        return _rewrite_student(original_student(*args,**kwargs))

    bot.parent_menu=parent_menu
    bot.student_menu=student_menu
    _installed=True
