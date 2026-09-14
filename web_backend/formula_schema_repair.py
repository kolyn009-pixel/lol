"""Compatibility repair for legacy formula_book schemas."""
from __future__ import annotations

from database import connect


def ensure_schema():
    conn = connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS formula_book(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          subject TEXT NOT NULL,
          section TEXT,
          topic TEXT,
          title TEXT NOT NULL,
          formula_latex TEXT NOT NULL,
          formula_plain TEXT,
          description TEXT,
          variables_json TEXT NOT NULL DEFAULT '[]',
          conditions TEXT,
          units TEXT,
          derivation TEXT,
          example TEXT,
          exam_note TEXT,
          grade_min INTEGER,
          grade_max INTEGER,
          education_level TEXT NOT NULL DEFAULT 'ALL',
          course_min INTEGER,
          course_max INTEGER,
          study_goal TEXT,
          tags_json TEXT NOT NULL DEFAULT '[]',
          sort_order INTEGER NOT NULL DEFAULT 100,
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL DEFAULT '',
          updated_at TEXT
        )
        """
    )
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(formula_book)")}
    additions = {
        "section": "TEXT",
        "topic": "TEXT",
        "formula_plain": "TEXT",
        "description": "TEXT",
        "variables_json": "TEXT NOT NULL DEFAULT '[]'",
        "conditions": "TEXT",
        "units": "TEXT",
        "derivation": "TEXT",
        "example": "TEXT",
        "exam_note": "TEXT",
        "grade_min": "INTEGER",
        "grade_max": "INTEGER",
        "education_level": "TEXT NOT NULL DEFAULT 'ALL'",
        "course_min": "INTEGER",
        "course_max": "INTEGER",
        "study_goal": "TEXT",
        "tags_json": "TEXT NOT NULL DEFAULT '[]'",
        "sort_order": "INTEGER NOT NULL DEFAULT 100",
        "active": "INTEGER NOT NULL DEFAULT 1",
        "created_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE formula_book ADD COLUMN {name} {ddl}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS formula_favorites(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          formula_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(formula_id,user_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_formula_filter "
        "ON formula_book(subject,education_level,section,topic,active,sort_order)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_formula_favorites_user "
        "ON formula_favorites(user_id,formula_id)"
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
