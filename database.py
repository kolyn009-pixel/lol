import os
import sqlite3
import secrets
import contextvars

from datetime import (
    datetime,
    timedelta,
    date,
)


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_NAME = os.path.join(
    BASE_DIR,
    "tutor.db"
)

TEST_DATA_DIR = os.environ.get(
    "TUTORBOT_TEST_DATA_DIR",
    os.path.join(os.path.dirname(BASE_DIR), "tutorbot_data"),
)
TEST_DB_NAME = os.environ.get(
    "TUTORBOT_TEST_DB",
    os.path.join(TEST_DATA_DIR, "tutor_test.db"),
)
_TEST_MODE = contextvars.ContextVar("tutorbot_test_mode", default=False)

def set_test_mode(value: bool):
    _TEST_MODE.set(bool(value))

def in_test_mode():
    return bool(_TEST_MODE.get())

def current_db_name():
    return TEST_DB_NAME if in_test_mode() else DB_NAME

def _open_db(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def connect_prod():
    return _open_db(DB_NAME)


# ============================================================
# CONNECTION
# ============================================================

def connect():
    return _open_db(current_db_name())


def now_iso():

    return (
        datetime.now()
        .isoformat(
            timespec="seconds"
        )
    )


# ============================================================
# CHANNEL MEMBER EVENTS
# ============================================================

def record_channel_member_event(
    channel_id,
    telegram_id,
    username,
    full_name,
    event_type,
    happened_at=None,
    telegram_update_id=None,
):

    event_type = str(event_type or "").strip().upper()
    if event_type not in {"JOIN", "LEAVE"}:
        raise ValueError("event_type must be JOIN or LEAVE")

    conn = connect()
    conn.execute(
        """
        INSERT OR IGNORE INTO channel_member_events (
            channel_id,
            telegram_id,
            username,
            full_name,
            event_type,
            happened_at,
            telegram_update_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(channel_id),
            int(telegram_id) if telegram_id is not None else None,
            normalize_username(username),
            (str(full_name).strip() if full_name else None),
            event_type,
            happened_at or now_iso(),
            int(telegram_update_id) if telegram_update_id is not None else None,
        ),
    )
    conn.commit()
    conn.close()


def get_channel_member_stats(channel_id, start_at, end_at):

    conn = connect()
    rows = conn.execute(
        """
        SELECT
            event_type,
            COUNT(*) AS total
        FROM channel_member_events
        WHERE channel_id = ?
          AND happened_at >= ?
          AND happened_at < ?
        GROUP BY event_type
        """,
        (str(channel_id), str(start_at), str(end_at)),
    ).fetchall()
    conn.close()

    result = {"JOIN": 0, "LEAVE": 0}
    for row in rows:
        result[str(row["event_type"])] = int(row["total"] or 0)

    return result


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_username(
    username
):

    if not username:
        return None

    return (
        str(username)
        .strip()
        .lstrip("@")
        .lower()
    )


def normalize_promo_code(
    code
):

    if not code:
        return None

    return (
        str(code)
        .strip()
        .upper()
        .replace(" ", "")
    )


# ============================================================
# MIGRATION HELPERS
# ============================================================

def table_exists(
    conn,
    table_name
):

    row = conn.execute("""
        SELECT name
        FROM sqlite_master

        WHERE
            type = 'table'
            AND name = ?
    """, (
        table_name,
    )).fetchone()

    return (
        row is not None
    )


def table_columns(
    conn,
    table_name
):

    if not table_exists(
        conn,
        table_name
    ):

        return set()

    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row["name"]
        for row in rows
    }


def add_column_if_missing(
    conn,
    table_name,
    column_name,
    definition
):

    columns = table_columns(
        conn,
        table_name
    )

    if column_name in columns:
        return

    conn.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN {column_name} {definition}
        """
    )


# ============================================================
# CREATE / MIGRATE DATABASE
# ============================================================

def create_tables():

    conn = connect()
    cursor = conn.cursor()


    # ========================================================
    # USERS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            telegram_id INTEGER UNIQUE,
            telegram_username TEXT,

            name TEXT NOT NULL,

            grade INTEGER NOT NULL,

            phone TEXT,

            study_goal TEXT NOT NULL,
            main_subject TEXT NOT NULL,

            education_type TEXT DEFAULT 'SCHOOL',
            education_level INTEGER,

            trial_used INTEGER DEFAULT 0,

            ege_physics_rate INTEGER,

            oge_physics_rate INTEGER,
            oge_chemistry_rate INTEGER,

            olympiad_physics_rate INTEGER,

            school_physics_rate INTEGER,
            school_chemistry_rate INTEGER,

            parent_name TEXT,
            parent_phone TEXT,
            parent_telegram_id INTEGER,

            active INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    # Existing TutorBot/test databases can predate fields that are present in
    # the current CREATE TABLE statement. CREATE TABLE IF NOT EXISTS does not
    # add those columns, so migrate them BEFORE any index or query references
    # them. Keep this list additive/idempotent for safe production upgrades.
    user_columns = {

        "telegram_username":
            "TEXT",

        "phone":
            "TEXT",

        "education_type":
            "TEXT DEFAULT 'SCHOOL'",

        "education_level":
            "INTEGER",

        "trial_used":
            "INTEGER DEFAULT 0",

        "ege_physics_rate":
            "INTEGER",

        "oge_physics_rate":
            "INTEGER",

        "oge_chemistry_rate":
            "INTEGER",

        "olympiad_physics_rate":
            "INTEGER",

        "school_physics_rate":
            "INTEGER",

        "school_chemistry_rate":
            "INTEGER",

        "updated_at":
            "TEXT",

        "extra_minutes_balance":
            "INTEGER DEFAULT 0",

        "bonus_lessons_earned":
            "INTEGER DEFAULT 0",

        "parent_name":
            "TEXT",

        "parent_phone":
            "TEXT",

        "parent_telegram_id":
            "INTEGER",

        "active":
            "INTEGER DEFAULT 1",

        "board_url":
            "TEXT",
    }

    for column_name, definition in user_columns.items():

        add_column_if_missing(
            conn,
            "users",
            column_name,
            definition
        )

    # The remainder of create_tables() is unchanged below this point.
    # It is intentionally preserved in the repository's current version.
    raise RuntimeError('partial_update_guard')
