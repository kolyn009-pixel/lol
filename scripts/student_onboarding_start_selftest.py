"""Regression checks for Telegram /start routing; transport and DB are isolated."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, AsyncMock
import asyncio
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]

class Stop(Exception):
    pass

def load_handler():
    telegram = ModuleType("telegram")
    telegram.InlineKeyboardButton = lambda text, **kwargs: SimpleNamespace(text=text, **kwargs)
    telegram.InlineKeyboardMarkup = lambda rows: rows
    telegram.Update = object
    ext = ModuleType("telegram.ext")
    ext.ApplicationHandlerStop = Stop
    ext.CallbackQueryHandler = ext.CommandHandler = ext.MessageHandler = object
    ext.ContextTypes = SimpleNamespace(DEFAULT_TYPE=object)
    ext.filters = SimpleNamespace(ALL=object())
    db = ModuleType("database")
    db.get_user_by_telegram_id = Mock(return_value=None)
    db.get_parent_by_telegram_id = Mock(return_value=None)
    backend = ModuleType("web_backend")
    backend.student_onboarding = SimpleNamespace(
        pending_for_external=Mock(return_value=None),
        confirm_channel=Mock(return_value={"name": "Test"}),
    )
    backend.public_trial_channel = SimpleNamespace(
        confirm=Mock(side_effect=ValueError("trial_link_not_found")),
        pending_by_external=Mock(return_value=None),
    )
    backend.public_trial = SimpleNamespace(get=Mock(return_value={"id": 1}))
    backend.trial_followup = SimpleNamespace()
    replacements = {"telegram": telegram, "telegram.ext": ext, "database": db, "web_backend": backend}
    previous = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "onboarding_routing_under_test", ROOT / "handlers/student_onboarding_runtime.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    module._show = AsyncMock()
    return module, db, backend

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.handler, self.db, self.backend = load_handler()
        self.user = SimpleNamespace(id=77, username="test", full_name="Test", first_name="Test")
        self.message = SimpleNamespace(text="/start trial_USED", reply_text=AsyncMock())
        self.update = SimpleNamespace(effective_user=self.user, effective_message=self.message)
        self.context = SimpleNamespace(args=["trial_OLD"])

    def run_start(self, stop=True):
        if stop:
            with self.assertRaises(Stop):
                asyncio.run(self.handler.start_join(self.update, self.context))
        else:
            asyncio.run(self.handler.start_join(self.update, self.context))

    def test_consumed_link_opens_only_senders_verified_trial(self):
        trial = {"id": 5}
        self.backend.public_trial_channel.pending_by_external.return_value = trial
        self.run_start()
        self.backend.public_trial_channel.pending_by_external.assert_called_once_with("TELEGRAM", "77")
        self.handler._show.assert_awaited_once_with(self.update, trial)

    def test_expired_unbound_link_offers_new_registration(self):
        self.backend.public_trial_channel.confirm.side_effect = ValueError("trial_link_expired")
        self.run_start()
        self.handler._show.assert_not_awaited()
        rows = self.message.reply_text.await_args.kwargs["reply_markup"]
        self.assertEqual(rows[0][0].url, "https://adeliatutor.ru/onboarding/")

    def test_wrong_identity_is_not_recovered(self):
        self.backend.public_trial_channel.confirm.side_effect = ValueError("trial_identity_locked")
        self.backend.public_trial_channel.pending_by_external.return_value = {"id": 9}
        self.run_start()
        self.handler._show.assert_not_awaited()
        self.backend.public_trial_channel.pending_by_external.assert_not_called()

    def test_active_student_falls_through_to_account_menu(self):
        self.db.get_user_by_telegram_id.return_value = {"active": 1}
        self.run_start(stop=False)
        self.message.reply_text.assert_not_awaited()
        self.handler._show.assert_not_awaited()

    def test_active_parent_falls_through_to_account_menu(self):
        self.db.get_parent_by_telegram_id.return_value = {"active": 1}
        self.run_start(stop=False)
        self.message.reply_text.assert_not_awaited()

    def test_pending_registration_takes_priority_over_trial(self):
        self.backend.student_onboarding.pending_for_external.return_value = {"token": "JOIN-X"}
        self.run_start()
        self.backend.public_trial_channel.pending_by_external.assert_not_called()
        self.assertIn("уже подключён", self.message.reply_text.await_args.args[0])

    def test_plain_start_ignores_cached_deep_link_arguments(self):
        self.message.text = "/start"
        self.run_start(stop=False)
        self.backend.public_trial_channel.confirm.assert_not_called()
        self.message.reply_text.assert_not_awaited()

    def test_addressed_start_without_payload_ignores_cached_arguments(self):
        self.message.text = "/start@AdeliaTutorBot"
        self.run_start(stop=False)
        self.backend.public_trial_channel.confirm.assert_not_called()

    def test_trial_gate_does_not_intercept_start_fallthrough(self):
        self.backend.public_trial_channel.pending_by_external.return_value = {"id": 9}
        self.context.user_data = {}
        asyncio.run(self.handler.trial_gate(self.update, self.context))
        self.backend.public_trial_channel.pending_by_external.assert_not_called()
        self.handler._show.assert_not_awaited()

    def test_new_trial_link_still_confirms(self):
        self.backend.public_trial_channel.confirm.side_effect = None
        self.backend.public_trial_channel.confirm.return_value = {"request_id": 1}
        self.message.text = "/start trial_NEW"
        self.run_start()
        self.backend.public_trial_channel.confirm.assert_called_once_with(
            "NEW", "TELEGRAM", "77", username="test", display_name="Test"
        )
        self.handler._show.assert_awaited_once()

    def test_explicit_permanent_registration_still_confirms(self):
        self.message.text = "/start join_JOIN-NEW"
        self.run_start()
        self.backend.student_onboarding.confirm_channel.assert_called_once_with(
            "JOIN-NEW", "TELEGRAM", "77", username="test", display_name="Test"
        )
        self.backend.public_trial_channel.confirm.assert_not_called()

if __name__ == "__main__":
    unittest.main()
