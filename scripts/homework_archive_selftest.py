"""Recent completed homework remains retrievable in both chat channels."""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
rows = [
    {"id": 1, "title": "Текущее", "status": "ASSIGNED"},
    {"id": 2, "title": "Прошедшее", "status": "COMPLETED"},
    {"id": 3, "title": "Отменено", "status": "CANCELLED"},
]


def function(path, name, scope):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(x for x in tree.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
                and x.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), scope)
    return scope[name]


def telegram():
    class Button:
        def __init__(self, label, callback_data=None, url=None):
            self.label, self.callback_data = label, callback_data
    class Query:
        data = "homework_archive"
        def __init__(self):
            self.text = ""
            self.buttons = []
        async def answer(self, *args, **kwargs):
            pass
        async def edit_message_text(self, text, reply_markup):
            self.text, self.buttons = text, reply_markup
    ui = SimpleNamespace(
        list_items=lambda uid, limit, include_finished=False: rows if include_finished else rows[:1],
        item_title=lambda row, i: row["title"],
        app_url=lambda: "/app/",
        list_text=lambda uid, limit: "Активные",
    )
    scope = {
        "database": SimpleNamespace(get_user_by_telegram_id=lambda tid: {"id": 5, "active": 1}),
        "homework_channel_ui": ui,
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": lambda buttons: buttons,
        "_status_icon": lambda status: "✅",
    }
    route = function("handlers/homework_channel_handlers.py", "homework_router", scope)
    query = Query()
    asyncio.run(route(SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=42)), None))
    callbacks = [button[0].callback_data for button in query.buttons if button]
    assert "homework_view|2" in callbacks and "homework_view|3" not in callbacks, callbacks
    assert "homework" in callbacks and "АРХИВ" in query.text, query.text


def vk():
    sent = []
    scope = {
        "database": SimpleNamespace(get_student_homework=lambda uid, active_only: rows[:1] if active_only else rows),
        "_button": lambda app, label, command, color=None: (label, command),
        "_send": lambda app, peer, text, buttons: sent.append((text, buttons)),
    }
    menu = function("vk_adapter/homework_v6.py", "menu", scope)
    menu(None, 42, 5, archive=True)
    commands = [button[0][1] for button in sent[0][1]]
    assert "vkhw|2" in commands and "vkhw|3" not in commands, commands
    assert "homework" in commands


def vk_archive_route():
    sent = []
    fake = types.ModuleType("vk_adapter.homework_v6")
    fake.menu = lambda app, peer, uid, archive=False: sent.append((peer, uid, archive))
    scope = {"__package__": "vk_adapter"}
    route = function("vk_adapter/runtime_homework_hook.py", "intercept", scope)
    app = SimpleNamespace(
        _extract_command=lambda message: "homework_archive",
        teacher_service=SimpleNamespace(is_teacher=lambda sender: False),
        service=SimpleNamespace(linked_user=lambda sender: {"id": 5}),
    )
    with patch.dict(sys.modules, {"vk_adapter.homework_v6": fake}):
        assert route(app, {"from_id": 42, "peer_id": 42})
    assert sent == [(42, 5, True)], sent


telegram()
vk()
vk_archive_route()
print("HOMEWORK_ARCHIVE=PASS")
