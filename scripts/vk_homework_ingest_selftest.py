"""Focused offline test for the VK teacher file persistence boundary."""
from __future__ import annotations

import importlib
import ast
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module(name, **attrs):
    value = types.ModuleType(name)
    value.__dict__.update(attrs)
    return value


class IngestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake_db = module("database")
        fake_store = module("homework_attachments")
        bridge = module("vk_adapter.attachment_bridge")
        delivery = module("vk_adapter.channel_delivery")
        teacher = module("vk_adapter.teacher_service")
        cls.modules = {
            "database": fake_db,
            "homework_attachments": fake_store,
            "vk_adapter.attachment_bridge": bridge,
            "vk_adapter.channel_delivery": delivery,
            "vk_adapter.teacher_service": teacher,
        }
        cls.patcher = patch.dict(sys.modules, cls.modules)
        cls.patcher.start()
        cls.ingest = importlib.import_module("vk_adapter.homework_ingest")

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        sys.modules.pop("vk_adapter.homework_ingest", None)

    def setUp(self):
        self.calls = []
        self.app = types.SimpleNamespace(
            _PENDING={42: ("t_hw", 7)},
            send=lambda *a: self.calls.append(("teacher_reply", a)),
        )
        db, store, bridge = (
            self.modules[x] for x in
            ("database", "homework_attachments", "vk_adapter.attachment_bridge")
        )
        db.get_user = lambda uid: {"id": uid, "study_goal": "SCHOOL", "main_subject": "PHYSICS"}
        db.create_homework = lambda **kw: self.calls.append(("create", kw)) or 100
        self.modules["vk_adapter.teacher_service"].student_programs = lambda uid: []
        store.initialize = lambda: None
        store.save_reference = lambda hid, **kw: self.calls.append(("save", hid, kw))
        store.resend_to_student = lambda hid, caption: self.calls.append(("deliver", hid, caption)) or {"count": 1, "vk": 1, "telegram": 0}
        bridge.vk_attachment_descriptor = lambda item: item
        self.modules["vk_adapter.channel_delivery"].send_student = lambda uid, text: {"vk": True, "telegram": False}
        self.file = {"kind": "document", "url": "https://example.userapi.com/file",
                     "filename": "Задачи.pdf", "content_type": "application/pdf", "vk_key": "doc1_2"}

    def test_persist_before_delivery_and_no_repeat_network_dependency(self):
        with patch.object(self.ingest, "_download", return_value=b"%PDF-1.7 body"):
            handled, ok = self.ingest.handle_teacher_assignment(
                self.app, 42, 42, 7, "Решить задачи", [self.file])
        self.assertEqual((handled, ok), (True, True))
        self.assertEqual([x[0] for x in self.calls[:3]], ["create", "save", "deliver"])
        self.assertEqual(self.calls[1][2]["content"], b"%PDF-1.7 body")
        self.assertEqual(self.calls[1][2]["source_channel"], "VK")
        self.assertNotIn(42, self.app._PENDING)

    def test_bad_file_does_not_create_homework_and_keeps_pending(self):
        with patch.object(self.ingest, "_download", return_value=b"not-a-pdf"):
            handled, ok = self.ingest.handle_teacher_assignment(
                self.app, 42, 42, 7, "", [self.file])
        self.assertEqual((handled, ok), (True, False))
        self.assertFalse(any(x[0] == "create" for x in self.calls))
        self.assertIn(42, self.app._PENDING)

    def test_failed_save_cancels_created_homework(self):
        db, store = self.modules["database"], self.modules["homework_attachments"]
        class Connection:
            def execute(_, sql, args):
                self.calls.append(("sql", sql, args))
            def commit(_):
                self.calls.append(("commit",))
            def close(_):
                pass
        db.connect = lambda: Connection()
        store.save_reference = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full"))
        with patch.object(self.ingest, "_download", return_value=b"%PDF-1.7 body"):
            handled, ok = self.ingest.handle_teacher_assignment(
                self.app, 42, 42, 7, "Задачи", [self.file])
        self.assertEqual((handled, ok), (True, False))
        self.assertTrue(any("status='CANCELLED'" in x[1] for x in self.calls if x[0] == "sql"))
        self.assertFalse(any(x[0] == "deliver" for x in self.calls))
        self.assertIn(42, self.app._PENDING)

    def test_rejects_untrusted_download_host(self):
        with self.assertRaises(ValueError):
            self.ingest._valid_url("https://userapi.com.evil.example/private")
        with self.assertRaises(ValueError):
            self.ingest._valid_url("http://example.userapi.com/file")

    def test_navigation_does_not_create_assignment(self):
        from vk_adapter import runtime_homework_hook
        router = types.SimpleNamespace(
            _PENDING={42: ("t_hw", 7)},
            teacher_service=types.SimpleNamespace(is_teacher=lambda vk_id: True),
            _extract_command=lambda msg: "t_hw_user|8",
            send=lambda *args: self.fail("unexpected confirmation"),
        )
        self.assertFalse(runtime_homework_hook.intercept(
            router, {"from_id": 42, "peer_id": 42, "text": "Выбрать другого"}))
        self.assertNotIn(42, router._PENDING)

    def test_pdf_source_prefers_persisted_blob(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "homework_pdf_runtime.py").read_text(encoding="utf-8"))
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_download_source")
        scope = {"MAX_PDF_BYTES": 20 * 1024 * 1024}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "<pdf source>", "exec"), scope)
        row = {"content_blob": b"%PDF-1.4 stored"}
        self.assertEqual(scope["_download_source"](row), b"%PDF-1.4 stored")


if __name__ == "__main__":
    unittest.main()
