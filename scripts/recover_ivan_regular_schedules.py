from __future__ import annotations

import argparse
import os
import shutil
from datetime import date, datetime

import database

SCHEDULE_IDS = (9, 10, 11)
EXPECTED_USER_ID = 33
DEFAULT_START_DATE = "2026-09-17"
TARGET_END_DATE = "2026-10-31"


def _rows():
    conn = database.connect()
    try:
        q = ",".join("?" for _ in SCHEDULE_IDS)
        rows = conn.execute(
            f"SELECT * FROM regular_schedules WHERE id IN ({q}) ORDER BY id",
            SCHEDULE_IDS,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _schedule_lesson_ids():
    conn