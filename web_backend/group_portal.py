"""Facade for Group Lessons web/mobile surfaces."""
from __future__ import annotations
from datetime import datetime,timedelta
import database
from web_backend import group_lessons,group_finance,group_runtime_v2,group_trials_and_coaching

def _now():return database.now_iso()
def ensure_schema():
 group_runtime_v2.ensure_schema();group_trials_and_coaching.ensure_schema();c=database.connect();c.executescript("""CREATE TABLE IF NOT EXISTS open_learning_events (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,event_type TEXT NOT NULL DEFAULT 'MOCK_EXAM',subject TEXT,grade_min INTEGER,grade_max INTEGER,starts_at TEXT NOT NULL,ends_at TEXT NOT NULL,price_per_student INTEGER NOT NULL