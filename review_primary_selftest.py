from __future__ import annotations

import asyncio

from handlers import pricing_ux_patch, review_v2


class DummyApp:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))


def main():
    app = DummyApp()
    pricing_ux_patch.install(app)

    routes = [
        (group, getattr(handler, "pattern", None))
        for group, handler in app.handlers
    ]
    assert any(group == -100 for group, _ in routes), routes

    # The sequential review must retain the controls that define the workflow.
    sample = {
        "kind": "PAYMENT_NEXT",
        "user_id": 1,
        "name": "Тест",
        "grade": 10,
        "lesson_id": 1,
        "start_time": "2026-09-04T12:00:00",
        "price": 1500,
        "stored_price": 2000,
        "remaining": 4,
        "key": "pay:1",
    }
    kb = review_v2._case_keyboard(sample, 0)
    labels = [button.text for row in kb.inline_keyboard for button in row]
    assert "✅ Решено" in labels, labels
    assert "📅 Отложить до…" in labels, labels
    assert "➡️ Следующий" in labels, labels

    defer_kb = review_v2._defer_keyboard(0)
    defer_labels = [button.text for row in defer_kb.inline_keyboard for button in row]
    assert any(label.startswith("📅 ") for label in defer_labels), defer_labels
    assert "⬅️ Назад" in defer_labels, defer_labels

    print("✅ primary route has priority")
    print("✅ one-case review controls present")
    print("✅ defer-to-specific-day menu present")


if __name__ == "__main__":
    main()
