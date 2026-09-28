"""Offline checks for repeat Telegram homework file delivery."""
from __future__ import annotations

import asyncio
import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class InputFile:
    def __init__(self, stream, filename):
        self.data = stream.read()
        self.filename = filename


class Button:
    def __init__(self, label, callback_data):
        self.label = label
        self.callback_data = callback_data


class FileDeliveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = {
            "id": 9, "homework_id": 3, "filename": "Задачи.pdf",
            "content_blob": b"%PDF-1.4 persisted", "telegram_file_id": "stale-id",
        }
        cls.pdf = types.ModuleType("homework_pdf_runtime")
        cls.pdf.attachment_filename = lambda row: row["filename"]
        cls.pdf.telegram_file_id = lambda row: row.get("telegram_file_id")
        cls.pdf.attachment = lambda hid, aid: cls.row if (int(hid), int(aid)) == (3, 9) else None
        cls.storage = types.ModuleType("homework_attachments")
        cls.storage._ensure_content_blob = lambda row: row["content_blob"]
        telegram = types.ModuleType("telegram")
        telegram.InputFile = InputFile
        telegram.InlineKeyboardButton = Button
        cls.patcher = patch.dict(sys.modules, {
            "telegram": telegram,
            "homework_pdf_runtime": cls.pdf,
            "homework_attachments": cls.storage,
        })
        cls.patcher.start()
        spec = importlib.util.spec_from_file_location(
            "telegram_homework_files", ROOT / "handlers/homework_file_delivery.py"
        )
        cls.delivery = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.delivery)

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()

    def test_first_open_prefers_server_copy(self):
        media = self.delivery.primary_media(self.row)
        self.assertEqual(media.data, b"%PDF-1.4 persisted")
        self.assertEqual(media.filename, "Задачи.pdf")

    def test_button_resends_server_copy(self):
        class Bot:
            async def send_document(_, chat_id, **kwargs):
                self.assertEqual(chat_id, 42)
                self.assertEqual(kwargs["document"].data, b"%PDF-1.4 persisted")
                return True
        self.assertTrue(asyncio.run(self.delivery.send(Bot(), 42, 3, 9)))
        button = self.delivery.buttons(3, [self.row])[0][0]
        self.assertEqual(button.callback_data, "hw6_file|3|9")

    def test_attachment_must_belong_to_homework(self):
        with self.assertRaises(FileNotFoundError):
            asyncio.run(self.delivery.send(object(), 42, 4, 9))

    def test_callback_denies_other_student_and_group_chat(self):
        tree = ast.parse((ROOT / "handlers/homework_v6.py").read_text(encoding="utf-8"))
        fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "callback")
        class Stop(Exception):
            pass
        scope = {"ApplicationHandlerStop": Stop, "_owns": lambda tid, hid: False}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<callback>", "exec"), scope)
        class Query:
            data = "hw6_file|3|9"
            from_user = types.SimpleNamespace(id=42)
            message = types.SimpleNamespace(chat_id=42)
            def __init__(self):
                self.answers = []
            async def answer(self, text=None, **kwargs):
                self.answers.append(text)
        q = Query()
        with self.assertRaises(Stop):
            asyncio.run(scope["callback"](types.SimpleNamespace(callback_query=q), object()))
        self.assertIn("ДЗ не найдено", q.answers[0])
        q = Query()
        q.message = types.SimpleNamespace(chat_id=-123)
        with self.assertRaises(Stop):
            asyncio.run(scope["callback"](types.SimpleNamespace(callback_query=q), object()))
        self.assertIn("личном чате", q.answers[0])

    def test_callback_sends_authorized_file(self):
        tree = ast.parse((ROOT / "handlers/homework_v6.py").read_text(encoding="utf-8"))
        fn = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "callback")
        class Stop(Exception):
            pass
        calls = []
        async def send(bot, chat_id, hid, aid):
            calls.append((chat_id, hid, aid))
        scope = {
            "ApplicationHandlerStop": Stop,
            "_owns": lambda tid, hid: tid == 42 and hid == 3,
            "FILES": types.SimpleNamespace(send=send),
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<callback>", "exec"), scope)
        class Query:
            data = "hw6_file|3|9"
            from_user = types.SimpleNamespace(id=42)
            message = types.SimpleNamespace(chat_id=42)
            async def answer(self, *args, **kwargs):
                pass
        with self.assertRaises(Stop):
            asyncio.run(scope["callback"](
                types.SimpleNamespace(callback_query=Query()),
                types.SimpleNamespace(bot=object())))
        self.assertEqual(calls, [(42, 3, 9)])


if __name__ == "__main__":
    unittest.main()
