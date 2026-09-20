from __future__ import annotations

import os
import sqlite3
import tempfile

import database
from handlers import calendar_runtime


root = tempfile.mkdtemp(prefix="adelia_rc_calendar_legacy_")
db_path = os.path.join(root, "calendar_legacy.db")
original_connect = database.connect


def test_connect():
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


try:
    # Reproduce the production-era schema that triggered:
    # NOT NULL constraint failed: calendar_lesson_state.updated_at
    conn = test_connect()
    conn.execute(
        """
        CREATE TABLE calendar_lesson_state (
            lesson_id INTEGER PRIMARY KEY,
            state_key TEXT NOT NULL,
            synced_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    database.connect = test_connect

    calendar_runtime._init_state_tables()
    calendar_runtime._save_state(101, "legacy-first")

    conn = test_connect()
    row = conn.execute(
        """
        SELECT lesson_id,state_key,synced_at,updated_at
        FROM calendar_lesson_state
        WHERE lesson_id=101
        """
    ).fetchone()
    conn.close()

    assert row is not None
    assert int(row["lesson_id"]) == 101
    assert row["state_key"] == "legacy-first"
    assert str(row["synced_at"] or "").strip()
    assert str(row["updated_at"] or "").strip()

    first_synced = row["synced_at"]
    first_updated = row["updated_at"]

    # UPSERT must remain compatible with the same legacy NOT NULL column.
    calendar_runtime._save_state(101, "legacy-second")

    conn = test_connect()
    row = conn.execute(
        """
        SELECT state_key,synced_at,updated_at
        FROM calendar_lesson_state
        WHERE lesson_id=101
        """
    ).fetchone()
    conn.close()

    assert row["state_key"] == "legacy-second"
    assert str(row["synced_at"] or "").strip()
    assert str(row["updated_at"] or "").strip()
    assert row["synced_at"] >= first_synced
    assert row["updated_at"] >= first_updated

    print("RC CALENDAR LEGACY SELFTEST: OK")
    print(
        "lesson_id=101",
        "state_key=" + row["state_key"],
        "synced_at=present",
        "updated_at=present",
    )
finally:
    database.connect = original_connect
    try:
        os.remove(db_path)
    except OSError:
        pass
    try:
        os.rmdir(root)
    except OSError:
        pass
