from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("TUTORBOT_TEST_DB", os.path.join(tempfile.gettempdir(), "tutorbot_vk_notifications_selftest.db"))

import database
from vk_adapter import schema, notification_sync


def main():
    database.set_test_mode(True)
    database.create_tables()
    schema.initialize()
    notification_sync.initialize()

    c = database.connect()
    try:
        tables = {
            r[0]
            for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "channel_identities" in tables
        assert "channel_delivery_log" in tables
    finally:
        c.close()

    now = datetime.now(notification_sync._tz())
    assert notification_sync._due(now + timedelta(hours=2), timedelta(hours=2), now)
    assert not notification_sync._due(now + timedelta(hours=3), timedelta(hours=2), now)

    print("✅ VK notification schema")
    print("✅ reminder due calculation")
    print("✅ notification selftest OK")


if __name__ == "__main__":
    main()
