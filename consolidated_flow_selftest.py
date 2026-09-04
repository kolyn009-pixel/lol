from __future__ import annotations

from handlers import pricing_ux_patch, review_v2
from vk_adapter import app as vk_app, notification_sync, lesson_link_bridge


class DummyApp:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))


def main():
    app = DummyApp()
    pricing_ux_patch.install(app)

    groups = [group for group, _ in app.handlers]
    assert -100 in groups, groups
    assert -90 in groups, groups

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
    for required in (
        "✅ Отметить оплату",
        "✅ Решено",
        "📅 Отложить до…",
        "➡️ Следующий",
    ):
        assert required in labels, (required, labels)

    pay_kb = pricing_ux_patch._payment_count_keyboard(0, 1, 4)
    pay_labels = [button.text for row in pay_kb.inline_keyboard for button in row]
    assert "✅ 1 занятие" in pay_labels, pay_labels
    assert "✅ 2 занятия" in pay_labels, pay_labels
    assert "✅ 3 занятия" in pay_labels, pay_labels
    assert "✏️ Указать количество" in pay_labels, pay_labels

    assert callable(vk_app.send)
    assert callable(notification_sync.tick)
    assert callable(lesson_link_bridge.install)

    print("✅ primary sequential review route")
    print("✅ defer-to-date controls")
    print("✅ manual 1/2/3/custom payment controls")
    print("✅ VK long-poll delivery available")
    print("✅ VK notification sync available")
    print("✅ Telegram lesson-link bridge to VK available")


if __name__ == "__main__":
    main()
