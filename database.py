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

DEFAULT_DB_NAME = os.path.join(
    BASE_DIR,
    "tutor.db"
)

DB_NAME = os.path.abspath(
    os.path.expanduser(
        os.environ.get("ADELIA_DB_PATH", DEFAULT_DB_NAME)
    )
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


    # ========================================================
    # PARENTS / ПРИВЯЗКА РОДИТЕЛЕЙ К УЧЕНИКАМ
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parent_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            telegram_username TEXT,
            name TEXT NOT NULL,
            phone TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parent_student_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            notify_schedule INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(parent_id, student_id),
            FOREIGN KEY(parent_id) REFERENCES parent_accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_link_codes (
            student_id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ========================================================
    # STUDENT PROGRAMS / НАПРАВЛЕНИЯ УЧЕНИКА
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_programs (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            custom_hourly_rate INTEGER,

            underworked_minutes_balance INTEGER DEFAULT 0,

            is_primary INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1,

            approval_status TEXT DEFAULT 'APPROVED',

            trial_used INTEGER DEFAULT 0,

            created_by TEXT DEFAULT 'SYSTEM',

            created_at TEXT NOT NULL,
            updated_at TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            UNIQUE(
                user_id,
                study_goal,
                subject
            )
        )
    """)

    add_column_if_missing(
        conn,
        "student_programs",
        "underworked_minutes_balance",
        "INTEGER DEFAULT 0"
    )


    # ========================================================
    # PRICE SETTINGS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_settings (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            rate_key TEXT NOT NULL UNIQUE,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            grade_min INTEGER,
            grade_max INTEGER,

            hourly_rate INTEGER NOT NULL,

            title TEXT NOT NULL,

            active INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    default_prices = [
        (
            "EGE_PHYSICS",
            "EGE",
            "PHYSICS",
            10,
            11,
            2000,
            "ЕГЭ • Физика",
        ),
        (
            "OGE_PHYSICS",
            "OGE",
            "PHYSICS",
            8,
            9,
            1750,
            "ОГЭ • Физика",
        ),
        (
            "OGE_CHEMISTRY",
            "OGE",
            "CHEMISTRY",
            8,
            9,
            1750,
            "ОГЭ • Химия",
        ),
        (
            "OLYMPIAD_PHYSICS",
            "OLYMPIAD",
            "PHYSICS",
            None,
            None,
            2500,
            "Олимпиадная физика",
        ),
        (
            "SCHOOL_PHYSICS_5_8",
            "SCHOOL",
            "PHYSICS",
            5,
            8,
            1500,
            "Школьная физика • 5–8 класс",
        ),
        (
            "SCHOOL_PHYSICS_9_11",
            "SCHOOL",
            "PHYSICS",
            9,
            11,
            1650,
            "Школьная физика • 9–11 класс",
        ),
        (
            "SCHOOL_CHEMISTRY_5_8",
            "SCHOOL",
            "CHEMISTRY",
            5,
            8,
            1500,
            "Школьная химия • 5–8 класс",
        ),
        (
            "SCHOOL_CHEMISTRY_9_11",
            "SCHOOL",
            "CHEMISTRY",
            9,
            11,
            1650,
            "Школьная химия • 9–11 класс",
        ),
    ]

    for (
        rate_key,
        study_goal,
        subject,
        grade_min,
        grade_max,
        hourly_rate,
        title,
    ) in default_prices:

        cursor.execute("""
            INSERT OR IGNORE INTO price_settings (

                rate_key,

                study_goal,
                subject,

                grade_min,
                grade_max,

                hourly_rate,

                title,

                active,

                created_at
            )

            VALUES (
                ?,
                ?, ?,
                ?, ?,
                ?,
                ?,
                1,
                ?
            )
        """, (
            rate_key,
            study_goal,
            subject,
            grade_min,
            grade_max,
            hourly_rate,
            title,
            now_iso()
        ))



    # ========================================================
    # WORKING HOURS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS working_hours (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            weekday INTEGER NOT NULL,

            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,

            active INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    # Week-aware teacher availability. Existing rows stay as ALL and therefore
    # remain valid after the migration. ODD/EVEN rows override ALL rows for
    # the same weekday when alternating weeks are enabled.
    add_column_if_missing(
        conn,
        "working_hours",
        "week_type",
        "TEXT DEFAULT 'ALL'",
    )


    # ========================================================
    # SCHEDULE EXCEPTIONS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule_exceptions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            date TEXT NOT NULL,

            exception_type TEXT NOT NULL,

            start_time TEXT,
            end_time TEXT,

            comment TEXT,

            created_at TEXT NOT NULL
        )
    """)


    # ========================================================
    # REGULAR SCHEDULES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regular_schedules (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            weekday INTEGER NOT NULL,

            start_time TEXT NOT NULL,

            duration_minutes INTEGER NOT NULL,

            active INTEGER DEFAULT 1,

            student_approved INTEGER DEFAULT 0,
            admin_approved INTEGER DEFAULT 0,

            created_at TEXT NOT NULL,
            updated_at TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    regular_schedule_columns = {

        "start_date":
            "TEXT",

        "end_date":
            "TEXT",

        "status":
            "TEXT DEFAULT 'PENDING'",

        "request_source":
            "TEXT DEFAULT 'STUDENT'",

        "requested_at":
            "TEXT",

        "approved_at":
            "TEXT",

        "rejected_at":
            "TEXT",

        "cancelled_at":
            "TEXT",

        "pause_until":
            "TEXT",

        "created_lessons_count":
            "INTEGER DEFAULT 0",

        "comment":
            "TEXT",
    }

    for column_name, definition in regular_schedule_columns.items():

        add_column_if_missing(
            conn,
            "regular_schedules",
            column_name,
            definition
        )


    # ========================================================
    # ONE-OFF BOOKING DRAFTS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS booking_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,
            program_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,

            duration_minutes INTEGER NOT NULL,
            hourly_rate INTEGER NOT NULL,
            price INTEGER NOT NULL,

            payment_choice TEXT,
            payment_id INTEGER,

            status TEXT NOT NULL DEFAULT 'DRAFT',
            rejection_reason TEXT,

            submitted_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,

            FOREIGN KEY(user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY(program_id)
                REFERENCES student_programs(id)
                ON DELETE CASCADE,

            FOREIGN KEY(payment_id)
                REFERENCES payments(id)
                ON DELETE SET NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_booking_drafts_user_status
        ON booking_drafts(user_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_booking_drafts_payment
        ON booking_drafts(payment_id)
    """)


    # ========================================================
    # PROMO CODES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            code TEXT NOT NULL UNIQUE,

            discount_type TEXT NOT NULL,
            discount_value INTEGER NOT NULL,

            max_uses INTEGER,

            uses_count INTEGER DEFAULT 0,

            per_user_limit INTEGER DEFAULT 1,

            expires_at TEXT,

            active INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)


    # ========================================================
    # PAYMENT METHODS / СПОСОБЫ ОПЛАТЫ
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    """)

    # ========================================================
    # PAYMENTS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            payment_type TEXT NOT NULL,

            lessons_count INTEGER NOT NULL,

            price_per_lesson INTEGER NOT NULL,

            subtotal INTEGER NOT NULL,

            discount_percent INTEGER DEFAULT 0,

            package_discount_amount INTEGER DEFAULT 0,

            promo_id INTEGER,
            promo_code TEXT,

            promo_discount_amount INTEGER DEFAULT 0,

            total_amount INTEGER NOT NULL,

            status TEXT DEFAULT 'WAITING',

            created_at TEXT NOT NULL,
            confirmed_at TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (promo_id)
                REFERENCES promo_codes(id)
                ON DELETE SET NULL
        )
    """)


    # Связь платежа с конкретным вручную назначенным занятием
    add_column_if_missing(
        conn,
        "payments",
        "lesson_id",
        "INTEGER"
    )


    # ========================================================
    # PROMO USAGES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promo_code_usages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            promo_id INTEGER NOT NULL,

            user_id INTEGER NOT NULL,

            payment_id INTEGER,

            discount_amount INTEGER NOT NULL,

            used_at TEXT NOT NULL,

            FOREIGN KEY (promo_id)
                REFERENCES promo_codes(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (payment_id)
                REFERENCES payments(id)
                ON DELETE SET NULL
        )
    """)


    # ========================================================
    # LESSON PACKAGES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_packages (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            payment_id INTEGER NOT NULL,

            user_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            lessons_total INTEGER NOT NULL,
            lessons_used INTEGER DEFAULT 0,

            price_per_lesson INTEGER NOT NULL,

            discount_percent INTEGER DEFAULT 0,

            amount_paid INTEGER NOT NULL,

            status TEXT DEFAULT 'ACTIVE',

            source_type TEXT DEFAULT 'PAID',

            bonus_reason TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (payment_id)
                REFERENCES payments(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    add_column_if_missing(
        conn,
        "lesson_packages",
        "source_type",
        "TEXT DEFAULT 'PAID'"
    )

    add_column_if_missing(
        conn,
        "lesson_packages",
        "bonus_reason",
        "TEXT"
    )


    # ========================================================
    # RECEIPTS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS receipts (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            payment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            telegram_file_id TEXT,

            source_platform TEXT DEFAULT 'TELEGRAM',

            file_type TEXT NOT NULL,

            status TEXT DEFAULT 'WAITING',

            created_at TEXT NOT NULL,
            reviewed_at TEXT,

            FOREIGN KEY (payment_id)
                REFERENCES payments(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # ========================================================
    # LESSONS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lessons (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,

            duration_minutes INTEGER NOT NULL,

            hourly_rate INTEGER DEFAULT 0,
            price INTEGER DEFAULT 0,

            payment_status TEXT DEFAULT 'UNPAID',

            payment_id INTEGER,
            package_id INTEGER,

            lesson_status TEXT DEFAULT 'PENDING',

            charged INTEGER DEFAULT 0,

            is_trial INTEGER DEFAULT 0,
            is_regular INTEGER DEFAULT 0,

            google_event_id TEXT,

            tutor_comment TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    lesson_columns = {

        "request_source":
            "TEXT DEFAULT 'STUDENT'",

        "requested_at":
            "TEXT",

        "approved_at":
            "TEXT",

        "rejected_at":
            "TEXT",

        "payment_deadline":
            "TEXT",

        "auto_cancelled_for_nonpayment":
            "INTEGER DEFAULT 0",

        "started_at":
            "TEXT",

        "finished_at":
            "TEXT",

        "actual_duration_minutes":
            "INTEGER DEFAULT 0",

        "extra_minutes":
            "INTEGER DEFAULT 0",

        "underworked_minutes":
            "INTEGER DEFAULT 0",

        "meeting_url":
            "TEXT",

        "meeting_link_sent_at":
            "TEXT",

        "tutor_delay_minutes":
            "INTEGER DEFAULT 0",

        "tutor_delay_notified_at":
            "TEXT",

        "bonus_minutes_processed":
            "INTEGER DEFAULT 0",

        "attendance_status":
            "TEXT",

        "cancelled_at":
            "TEXT",

        "cancellation_reason":
            "TEXT",

        "rescheduled_from_lesson_id":
            "INTEGER",

        "rescheduled_to_lesson_id":
            "INTEGER",

        "reschedule_type":
            "TEXT",

        "rescheduled_at":
            "TEXT",

        "sickness_comment":
            "TEXT",

        "sickness_requested_at":
            "TEXT",

        "sickness_number_in_month":
            "INTEGER",

        "sickness_admin_decision":
            "TEXT",

        "homework_required":
            "INTEGER DEFAULT 0",

        "homework_assigned":
            "INTEGER DEFAULT 0",

        "homework_skipped":
            "INTEGER DEFAULT 0",

        "homework_reminder_sent":
            "INTEGER DEFAULT 0",

        "regular_schedule_id":
            "INTEGER",
    }

    for column_name, definition in lesson_columns.items():

        add_column_if_missing(
            conn,
            "lessons",
            column_name,
            definition
        )


    # ========================================================
    # PROGRAM LINKS
    # ========================================================

    add_column_if_missing(
        conn,
        "lessons",
        "program_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "payments",
        "program_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "lesson_packages",
        "program_id",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "regular_schedules",
        "program_id",
        "INTEGER"
    )


    # ========================================================
    # LESSON NOTES FROM STUDENT
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_notes (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            lesson_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            text TEXT,

            photo_file_id TEXT,
            photo_file_unique_id TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lesson_notes_lesson
        ON lesson_notes(
            lesson_id,
            created_at
        )
    """)


    # UX/SPEED indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_grade_active_name ON users(grade,active,name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(telegram_username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_user_start ON lessons(user_id,start_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_lessons_status_start ON lessons(lesson_status,start_time)")

    # ========================================================
    # HOMEWORK
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,
            lesson_id INTEGER,

            study_goal TEXT NOT NULL,
            subject TEXT NOT NULL,

            title TEXT,
            description TEXT,

            homework_type TEXT DEFAULT 'MAIN',

            source_type TEXT DEFAULT 'CUSTOM',

            source_reference TEXT,
            source_url TEXT,

            deadline TEXT,

            status TEXT DEFAULT 'ASSIGNED',

            assigned_at TEXT NOT NULL,

            submitted_at TEXT,
            reviewed_at TEXT,

            created_at TEXT NOT NULL,
            updated_at TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id)
                ON DELETE SET NULL
        )
    """)


    add_column_if_missing(
        conn,
        "homework",
        "program_id",
        "INTEGER"
    )


    # ========================================================
    # HOMEWORK SUBMISSIONS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework_submissions (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            homework_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            attempt_number INTEGER DEFAULT 1,

            student_comment TEXT,

            status TEXT DEFAULT 'SUBMITTED',

            submitted_from TEXT,

            submitted_at TEXT NOT NULL,
            reviewed_at TEXT,

            FOREIGN KEY (homework_id)
                REFERENCES homework(id)
                ON DELETE CASCADE,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)


    # ========================================================
    # HOMEWORK REVIEWS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework_reviews (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            homework_id INTEGER NOT NULL,

            submission_id INTEGER,

            result TEXT NOT NULL,

            tutor_comment TEXT,

            reviewed_at TEXT NOT NULL,

            FOREIGN KEY (homework_id)
                REFERENCES homework(id)
                ON DELETE CASCADE,

            FOREIGN KEY (submission_id)
                REFERENCES homework_submissions(id)
                ON DELETE SET NULL
        )
    """)


    add_column_if_missing(
        conn,
        "homework_reviews",
        "total_tasks",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "homework_reviews",
        "correct_tasks",
        "INTEGER"
    )

    add_column_if_missing(
        conn,
        "homework_reviews",
        "accuracy_percent",
        "REAL"
    )


    # ========================================================
    # PENDING RESCHEDULES
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_reschedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL UNIQUE,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            reminder_due_at TEXT,
            reminded_at TEXT,
            completed_at TEXT,
            new_lesson_id INTEGER,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_reschedules_due
        ON pending_reschedules(status, reminder_due_at)
    """)


    # ========================================================
    # REMINDERS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_reminders (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            lesson_id INTEGER NOT NULL,

            reminder_type TEXT NOT NULL,

            sent INTEGER DEFAULT 0,

            sent_at TEXT,

            UNIQUE(
                lesson_id,
                reminder_type
            ),

            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id)
                ON DELETE CASCADE
        )
    """)


    # ========================================================
    # LESSON TIME ADJUSTMENTS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lesson_time_adjustments (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER NOT NULL,

            lesson_id INTEGER,

            difference_minutes INTEGER NOT NULL,

            bonus_lessons_added INTEGER DEFAULT 0,

            balance_after INTEGER DEFAULT 0,

            created_at TEXT NOT NULL,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id)
                ON DELETE SET NULL
        )
    """)



    # ========================================================
    # BOT SETTINGS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (

            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)


    # ========================================================
    # USER TIMEZONES / REGION MIGRATION
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_timezones (
            telegram_id INTEGER PRIMARY KEY,
            msk_offset INTEGER NOT NULL DEFAULT 0,
            zone_name TEXT,
            configured INTEGER NOT NULL DEFAULT 0,
            notified_at TEXT,
            configured_at TEXT,
            updated_at TEXT
        )
    """)



    # ========================================================
    # CHANNEL MEMBER EVENTS
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_member_events (

            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
            telegram_id INTEGER,
            username TEXT,
            full_name TEXT,
            event_type TEXT NOT NULL,
            happened_at TEXT NOT NULL,

            CHECK(event_type IN ('JOIN', 'LEAVE'))
        )
    """)

    add_column_if_missing(
        conn,
        "channel_member_events",
        "telegram_update_id",
        "INTEGER",
    )


    # ========================================================
    # INDEXES
    # ========================================================

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lessons_user
        ON lessons(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lessons_start
        ON lessons(start_time)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lessons_status
        ON lessons(lesson_status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lessons_regular
        ON lessons(regular_schedule_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_payments_user
        ON payments(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_homework_user
        ON homework(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_regular_schedule_user
        ON regular_schedules(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_regular_schedule_status
        ON regular_schedules(status)
    """)


    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_channel_member_events_channel_time
        ON channel_member_events(channel_id, happened_at)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_channel_member_events_type_time
        ON channel_member_events(event_type, happened_at)
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_channel_member_events_update_id
        ON channel_member_events(telegram_update_id)
        WHERE telegram_update_id IS NOT NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_student_programs_user
        ON student_programs(user_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_student_programs_active
        ON student_programs(user_id, active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_lessons_program
        ON lessons(program_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_homework_program
        ON homework(program_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_payments_program
        ON payments(program_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_packages_program
        ON lesson_packages(program_id)
    """)

    # Переносим старых учеников в новую модель направлений.
    migrate_legacy_student_programs(
        conn
    )

    # Заполняем program_id у старых записей по study_goal + subject.
    backfill_program_links(
        conn
    )


    # ========================================================
    # OLD STATUS MIGRATION
    # ========================================================

    cursor.execute("""
        UPDATE lessons

        SET lesson_status = 'CONFIRMED'

        WHERE lesson_status = 'SCHEDULED'
    """)

    conn.commit()
    conn.close()


# ============================================================
# USERS
# ============================================================

def get_user(
    user_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM users

        WHERE id = ?
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return row


def get_user_by_telegram_id(
    telegram_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM users

        WHERE telegram_id = ?
    """, (
        telegram_id,
    )).fetchone()

    conn.close()

    return row


def get_user_by_telegram_username(
    username
):

    username = normalize_username(
        username
    )

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM users

        WHERE LOWER(
            telegram_username
        ) = ?
    """, (
        username,
    )).fetchone()

    conn.close()

    return row


def add_telegram_user(
    telegram_id,
    telegram_username,
    name,
    grade,
    study_goal,
    main_subject,
    phone=None
):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO users (

            telegram_id,
            telegram_username,

            name,
            grade,

            phone,

            study_goal,
            main_subject,

            created_at
        )

        VALUES (
            ?, ?,
            ?, ?,
            ?,
            ?, ?,
            ?
        )
    """, (
        telegram_id,

        normalize_username(
            telegram_username
        ),

        name,
        int(grade),

        phone,

        study_goal,
        main_subject,

        now_iso()
    ))

    user_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return user_id


def get_all_users(
    active_only=True
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM users

            WHERE active = 1

            ORDER BY
                grade ASC,
                name COLLATE NOCASE ASC
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM users

            ORDER BY
                grade ASC,
                name COLLATE NOCASE ASC
        """).fetchall()

    conn.close()

    return rows


def get_users_by_grade(
    grade,
    active_only=True
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM users

            WHERE
                grade = ?
                AND active = 1

            ORDER BY
                name COLLATE NOCASE ASC
        """, (
            int(grade),
        )).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM users

            WHERE grade = ?

            ORDER BY
                name COLLATE NOCASE ASC
        """, (
            int(grade),
        )).fetchall()

    conn.close()

    return rows


def get_student_grades(
    active_only=True
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT DISTINCT grade
            FROM users

            WHERE active = 1

            ORDER BY grade ASC
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT DISTINCT grade
            FROM users

            ORDER BY grade ASC
        """).fetchall()

    conn.close()

    return [
        int(row["grade"])
        for row in rows
    ]


def set_user_active(
    user_id,
    active
):

    conn = connect()

    conn.execute("""
        UPDATE users

        SET
            active = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        int(bool(active)),
        now_iso(),
        user_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# RATES
# ============================================================

def get_rate_key(
    study_goal,
    subject,
    grade=None
):

    study_goal = str(
        study_goal
    ).upper()

    subject = str(
        subject
    ).upper()

    if (
        study_goal == "EGE"
        and subject == "PHYSICS"
    ):

        return "EGE_PHYSICS"

    if (
        study_goal == "OGE"
        and subject == "PHYSICS"
    ):

        return "OGE_PHYSICS"

    if (
        study_goal == "OGE"
        and subject == "CHEMISTRY"
    ):

        return "OGE_CHEMISTRY"

    if (
        study_goal == "OLYMPIAD"
        and subject == "PHYSICS"
    ):

        return "OLYMPIAD_PHYSICS"

    if study_goal == "SCHOOL":

        if grade is None:

            raise ValueError(
                "Для школьного тарифа нужен класс ученика."
            )

        grade = int(
            grade
        )

        suffix = (
            "5_8"
            if grade < 9
            else "9_11"
        )

        if subject == "PHYSICS":

            return (
                f"SCHOOL_PHYSICS_{suffix}"
            )

        if subject == "CHEMISTRY":

            return (
                f"SCHOOL_CHEMISTRY_{suffix}"
            )

    raise ValueError(
        "Тариф не найден."
    )


def get_all_price_settings(
    active_only=True
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM price_settings

            WHERE active = 1

            ORDER BY
                CASE study_goal
                    WHEN 'SCHOOL'
                    THEN 1

                    WHEN 'OGE'
                    THEN 2

                    WHEN 'EGE'
                    THEN 3

                    WHEN 'OLYMPIAD'
                    THEN 4

                    ELSE 5
                END,

                subject,
                grade_min
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM price_settings

            ORDER BY
                study_goal,
                subject,
                grade_min
        """).fetchall()

    conn.close()

    return rows


def get_price_setting(
    rate_key
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM price_settings

        WHERE rate_key = ?
    """, (
        str(rate_key).upper(),
    )).fetchone()

    conn.close()

    return row


def get_default_rate(
    study_goal,
    subject,
    grade
):

    rate_key = get_rate_key(
        study_goal,
        subject,
        grade
    )

    setting = get_price_setting(
        rate_key
    )

    if setting is None:

        # Fallback нужен только для очень старой БД,
        # если create_tables() ещё не запускался.
        fallback = {

            "EGE_PHYSICS":
                2000,

            "OGE_PHYSICS":
                1750,

            "OGE_CHEMISTRY":
                1750,

            "OLYMPIAD_PHYSICS":
                2500,

            "SCHOOL_PHYSICS_5_8":
                1500,

            "SCHOOL_PHYSICS_9_11":
                1650,

            "SCHOOL_CHEMISTRY_5_8":
                1500,

            "SCHOOL_CHEMISTRY_9_11":
                1650,
        }

        if rate_key not in fallback:

            raise ValueError(
                "Общая ставка не найдена."
            )

        return fallback[
            rate_key
        ]

    return int(
        setting[
            "hourly_rate"
        ]
    )


def set_default_rate(
    rate_key,
    hourly_rate
):

    rate_key = str(
        rate_key
    ).upper()

    hourly_rate = int(
        hourly_rate
    )

    if hourly_rate <= 0:

        raise ValueError(
            "Цена должна быть больше нуля."
        )

    setting = get_price_setting(
        rate_key
    )

    if setting is None:

        raise ValueError(
            "Общая ставка не найдена."
        )

    conn = connect()

    conn.execute("""
        UPDATE price_settings

        SET
            hourly_rate = ?,
            updated_at = ?

        WHERE rate_key = ?
    """, (
        hourly_rate,
        now_iso(),
        rate_key
    ))

    conn.commit()
    conn.close()

    return hourly_rate


def set_default_rate_for_course(
    study_goal,
    subject,
    grade,
    hourly_rate
):

    rate_key = get_rate_key(
        study_goal,
        subject,
        grade
    )

    return set_default_rate(
        rate_key,
        hourly_rate
    )


def get_rate_column(
    study_goal,
    subject
):

    mapping = {

        (
            "EGE",
            "PHYSICS"
        ):
            "ege_physics_rate",

        (
            "OGE",
            "PHYSICS"
        ):
            "oge_physics_rate",

        (
            "OGE",
            "CHEMISTRY"
        ):
            "oge_chemistry_rate",

        (
            "OLYMPIAD",
            "PHYSICS"
        ):
            "olympiad_physics_rate",

        (
            "SCHOOL",
            "PHYSICS"
        ):
            "school_physics_rate",

        (
            "SCHOOL",
            "CHEMISTRY"
        ):
            "school_chemistry_rate",
    }

    value = mapping.get(
        (
            study_goal,
            subject
        )
    )

    if value is None:

        raise ValueError(
            "Тариф не найден."
        )

    return value


def get_student_rate_info(
    user_id,
    study_goal=None,
    subject=None
):

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    if study_goal is None:

        study_goal = (
            user["study_goal"]
        )

    if subject is None:

        subject = (
            user["main_subject"]
        )

    column = get_rate_column(
        study_goal,
        subject
    )

    # student_programs.custom_hourly_rate is canonical.  The legacy users.*
    # rate column remains a fallback for old profiles that have not yet been
    # migrated to programme-scoped pricing.
    conn = connect()
    try:
        program = conn.execute("""
            SELECT custom_hourly_rate
            FROM student_programs
            WHERE user_id = ?
              AND study_goal = ?
              AND subject = ?
              AND COALESCE(active,1) = 1
              AND COALESCE(approval_status,'APPROVED') = 'APPROVED'
            ORDER BY is_primary DESC, id
            LIMIT 1
        """, (
            int(user_id),
            study_goal,
            subject,
        )).fetchone()
    finally:
        conn.close()

    program_custom_rate = (
        program["custom_hourly_rate"]
        if program is not None
        else None
    )

    custom_rate = (
        program_custom_rate
        if program_custom_rate is not None
        else user[column]
    )

    common_rate = (
        get_default_rate(
            study_goal,
            subject,
            user["grade"]
        )
    )

    if custom_rate is not None:

        effective_rate = int(
            custom_rate
        )

        source = "CUSTOM"

    else:

        effective_rate = int(
            common_rate
        )

        source = "DEFAULT"

    return {
        "user_id":
            user_id,

        "study_goal":
            study_goal,

        "subject":
            subject,

        "grade":
            int(
                user["grade"]
            ),

        "rate_key":
            get_rate_key(
                study_goal,
                subject,
                user["grade"]
            ),

        "effective_rate":
            effective_rate,

        "common_rate":
            int(
                common_rate
            ),

        "custom_rate":
            (
                int(custom_rate)
                if custom_rate is not None
                else None
            ),

        "source":
            source,
    }


def get_student_rate(
    user_id,
    study_goal=None,
    subject=None
):

    return int(
        get_student_rate_info(
            user_id,
            study_goal,
            subject
        )[
            "effective_rate"
        ]
    )


def set_custom_rate(
    user_id,
    study_goal,
    subject,
    rate
):
    """
    Compatibility entry point.

    The canonical individual rate is student_programs.custom_hourly_rate.
    Keep the legacy users.*_rate field synchronized as well.
    """
    rate = int(rate)
    if rate <= 0:
        raise ValueError("Цена должна быть больше нуля.")

    column = get_rate_column(study_goal, subject)
    conn = connect()

    try:
        now = now_iso()

        conn.execute(
            f"""
            UPDATE users
            SET {column} = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (rate, now, int(user_id)),
        )

        conn.execute(
            """
            UPDATE student_programs
            SET custom_hourly_rate = ?,
                updated_at = ?
            WHERE user_id = ?
              AND study_goal = ?
              AND subject = ?
            """,
            (
                rate,
                now,
                int(user_id),
                study_goal,
                subject,
            ),
        )

        rows = conn.execute(
            """
            SELECT l.id, l.duration_minutes
            FROM lessons l
            LEFT JOIN student_programs sp
              ON sp.id = l.program_id
            WHERE l.user_id = ?
              AND l.lesson_status = 'CONFIRMED'
              AND l.payment_status IN ('AWAITING_PAYMENT','UNPAID')
              AND COALESCE(l.is_trial,0) = 0
              AND l.start_time > ?
              AND (
                    (
                        l.program_id IS NOT NULL
                        AND sp.study_goal = ?
                        AND sp.subject = ?
                    )
                    OR
                    (
                        l.program_id IS NULL
                        AND l.study_goal = ?
                        AND l.subject = ?
                    )
                  )
            """,
            (
                int(user_id),
                now,
                study_goal,
                subject,
                study_goal,
                subject,
            ),
        ).fetchall()

        for row in rows:
            price = calculate_lesson_price(
                rate,
                int(row["duration_minutes"] or 60),
            )
            conn.execute(
                """
                UPDATE lessons
                SET hourly_rate = ?,
                    price = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (rate, price, now, int(row["id"])),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return rate


def clear_custom_rate(
    user_id,
    study_goal,
    subject
):
    column = get_rate_column(study_goal, subject)
    conn = connect()

    try:
        now = now_iso()

        user = conn.execute(
            "SELECT grade FROM users WHERE id=?",
            (int(user_id),),
        ).fetchone()

        if user is None:
            raise ValueError("Ученик не найден.")

        default_rate = int(
            get_default_rate(
                study_goal,
                subject,
                user["grade"],
            )
        )

        conn.execute(
            f"""
            UPDATE users
            SET {column} = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (now, int(user_id)),
        )

        conn.execute(
            """
            UPDATE student_programs
            SET custom_hourly_rate = NULL,
                updated_at = ?
            WHERE user_id = ?
              AND study_goal = ?
              AND subject = ?
            """,
            (
                now,
                int(user_id),
                study_goal,
                subject,
            ),
        )

        rows = conn.execute(
            """
            SELECT l.id, l.duration_minutes
            FROM lessons l
            LEFT JOIN student_programs sp
              ON sp.id = l.program_id
            WHERE l.user_id = ?
              AND l.lesson_status = 'CONFIRMED'
              AND l.payment_status IN ('AWAITING_PAYMENT','UNPAID')
              AND COALESCE(l.is_trial,0) = 0
              AND l.start_time > ?
              AND (
                    (
                        l.program_id IS NOT NULL
                        AND sp.study_goal = ?
                        AND sp.subject = ?
                    )
                    OR
                    (
                        l.program_id IS NULL
                        AND l.study_goal = ?
                        AND l.subject = ?
                    )
                  )
            """,
            (
                int(user_id),
                now,
                study_goal,
                subject,
                study_goal,
                subject,
            ),
        ).fetchall()

        for row in rows:
            price = calculate_lesson_price(
                default_rate,
                int(row["duration_minutes"] or 60),
            )
            conn.execute(
                """
                UPDATE lessons
                SET hourly_rate = ?,
                    price = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    default_rate,
                    price,
                    now,
                    int(row["id"]),
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_student_rate_info(
        user_id,
        study_goal,
        subject,
    )


def calculate_lesson_price(
    hourly_rate,
    duration_minutes
):

    return round(
        int(hourly_rate)
        * int(duration_minutes)
        / 60
    )


# ============================================================
# STATUS LABELS
# ============================================================

LESSON_STATUS_RU = {

    "PENDING":
        "Ожидает подтверждения",

    "CONFIRMED":
        "Подтверждено",

    "IN_PROGRESS":
        "Занятие идёт",

    "COMPLETED":
        "Проведено",

    "CANCELLED":
        "Отменено",

    "REJECTED":
        "Отклонено",

    "NO_SHOW":
        "Неявка",

    "LATE_CANCELLED":
        "Поздняя отмена",

    "SICKNESS":
        "Больничный",
}


PAYMENT_STATUS_RU = {
    "REVERSED": "Подтверждение отменено",

    "WAITING":
        "Ожидает оплаты",

    "RECEIPT_SENT":
        "Чек отправлен",

    "PAID":
        "Оплачено",

    "FREE":
        "Бесплатно",

    "UNPAID":
        "Не оплачено",

    "AWAITING_PAYMENT":
        "Ожидает оплаты",

    "RESERVED_BALANCE":
        "Зарезервировано с абонемента",

    "REFUNDED":
        "Возвращено на баланс",

    "UNPAID_CANCELLED":
        "Отменено из-за неоплаты",

    "TRANSFERRED":
        "Перенесено",
}


REGULAR_STATUS_RU = {

    "PENDING":
        "Ожидает подтверждения",

    "APPROVED":
        "Подтверждено",

    "PAUSED":
        "Приостановлено",

    "REJECTED":
        "Отклонено",

    "CANCELLED":
        "Отменено",
}


def get_lesson_status_ru(
    status
):

    return LESSON_STATUS_RU.get(
        status,
        status or "—"
    )


def get_payment_status_ru(
    status
):

    return PAYMENT_STATUS_RU.get(
        status,
        status or "—"
    )


def get_regular_status_ru(
    status
):

    return REGULAR_STATUS_RU.get(
        status,
        status or "—"
    )


# ============================================================
# TRIAL
# ============================================================

def has_used_trial(
    user_id
):

    user = get_user(
        user_id
    )

    if user is None:
        return False

    return bool(
        user["trial_used"]
    )


def mark_trial_used(
    user_id
):

    conn = connect()

    conn.execute("""
        UPDATE users

        SET
            trial_used = 1,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        user_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# WORKING HOURS
# ============================================================

def add_working_hours(
    weekday,
    start_time,
    end_time,
    week_type="ALL",
):

    if int(weekday) < 0 or int(weekday) > 6:

        raise ValueError(
            "Неверный день недели."
        )

    start_dt = datetime.strptime(
        start_time,
        "%H:%M"
    )

    end_dt = datetime.strptime(
        end_time,
        "%H:%M"
    )

    if end_dt <= start_dt:

        raise ValueError(
            "Время окончания должно быть позже начала."
        )

    week_type = str(week_type or "ALL").upper().strip()
    if week_type not in {"ALL", "ODD", "EVEN"}:
        raise ValueError("Неверный тип недели.")

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO working_hours (

            weekday,

            start_time,
            end_time,
            week_type,

            active,

            created_at
        )

        VALUES (
            ?,
            ?, ?, ?,
            1,
            ?
        )
    """, (
        int(weekday),
        start_time,
        end_time,
        week_type,
        now_iso()
    ))

    row_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return row_id


def get_working_hours(
    weekday=None,
    week_type=None,
    conn=None,
):

    own_conn = conn is None
    if own_conn:
        conn = connect()

    clauses = ["active = 1"]
    params = []

    if weekday is not None:
        clauses.append("weekday = ?")
        params.append(int(weekday))

    if week_type is not None:
        week_type = str(week_type).upper().strip()
        clauses.append("COALESCE(week_type, 'ALL') = ?")
        params.append(week_type)

    rows = conn.execute(
        f"""
        SELECT *
        FROM working_hours
        WHERE {' AND '.join(clauses)}
        ORDER BY weekday, start_time
        """,
        params,
    ).fetchall()

    if own_conn:
        conn.close()

    return rows


ODD_WEEK_ANCHOR = date(2026, 8, 31)  # week containing 1 September 2026


def teacher_week_kind(day_value):
    """Return ODD/EVEN using the user-defined school-year anchor.

    The week 31.08.2026-06.09.2026 is ODD. This is intentionally independent
    from ISO week numbering so the academic schedule remains predictable.
    """
    if isinstance(day_value, datetime):
        day_value = day_value.date()
    elif isinstance(day_value, str):
        day_value = date.fromisoformat(day_value[:10])
    if not isinstance(day_value, date):
        raise ValueError("day_value must be date/datetime/ISO date")
    weeks = (day_value - ODD_WEEK_ANCHOR).days // 7
    return "ODD" if weeks % 2 == 0 else "EVEN"


def teacher_week_label(kind):
    return "нечётная" if str(kind).upper() == "ODD" else "чётная"


def teacher_week_enabled(kind, conn=None):
    key = "teacher_odd_week_enabled" if str(kind).upper() == "ODD" else "teacher_even_week_enabled"
    return str(
        get_setting(key, "1", conn=conn)
    ).lower() not in {"0", "false", "off", "no"}


def teacher_week_day_off(kind, weekday, conn=None):
    kind = str(kind).upper()
    key = f"teacher_week_day_off_{kind}_{int(weekday)}"
    return str(
        get_setting(key, "0", conn=conn)
    ).lower() in {"1", "true", "on", "yes"}


def set_teacher_week_day_off(kind, weekday, value):
    kind = str(kind).upper()
    key = f"teacher_week_day_off_{kind}_{int(weekday)}"
    set_setting(key, "1" if value else "0")


def get_effective_working_hours(day_value, conn=None):
    """Working intervals actually available on a concrete teacher-local date.

    Modes:
      SAME        - only common ALL rows are used every week.
      ALTERNATING - ODD/EVEN rows override common rows per weekday; when no
                    specific rows exist, ALL rows are a safe fallback.

    Each week can be temporarily disabled without deleting its schedule.
    """
    if isinstance(day_value, datetime):
        day_obj = day_value.date()
    elif isinstance(day_value, str):
        day_obj = date.fromisoformat(day_value[:10])
    else:
        day_obj = day_value

    mode = str(
        get_setting(
            "teacher_week_mode",
            "SAME",
            conn=conn,
        ) or "SAME"
    ).upper()

    weekday = int(day_obj.weekday())

    if mode == "SAME":
        return get_working_hours(
            weekday,
            "ALL",
            conn=conn,
        )

    kind = teacher_week_kind(day_obj)

    if not teacher_week_enabled(
        kind,
        conn=conn,
    ):
        return []

    if teacher_week_day_off(
        kind,
        weekday,
        conn=conn,
    ):
        return []

    specific = get_working_hours(
        weekday,
        kind,
        conn=conn,
    )

    if specific:
        return specific

    return get_working_hours(
        weekday,
        "ALL",
        conn=conn,
    )


def replace_week_schedule(source_type, target_type):
    """Copy the effective source parity schedule to target parity."""
    source_type = str(source_type).upper()
    target_type = str(target_type).upper()
    if source_type not in {"ODD", "EVEN"} or target_type not in {"ODD", "EVEN"}:
        raise ValueError("Неверный тип недели")

    snapshot = []
    off_map = {}
    for weekday in range(7):
        is_off = teacher_week_day_off(source_type, weekday)
        off_map[weekday] = is_off
        if is_off:
            continue
        rows = get_working_hours(weekday, source_type) or get_working_hours(weekday, "ALL")
        for row in rows:
            snapshot.append((weekday, row["start_time"], row["end_time"]))

    conn = connect()
    conn.execute("DELETE FROM working_hours WHERE COALESCE(week_type,'ALL') = ?", (target_type,))
    for weekday, start_time, end_time in snapshot:
        conn.execute(
            """INSERT INTO working_hours(weekday,start_time,end_time,week_type,active,created_at,updated_at)
               VALUES(?,?,?,?,1,?,?)""",
            (weekday, start_time, end_time, target_type, now_iso(), now_iso()),
        )
    conn.commit()
    conn.close()

    for weekday, is_off in off_map.items():
        set_teacher_week_day_off(target_type, weekday, is_off)
    return len(snapshot)

def clear_week_schedule(week_type):
    week_type = str(week_type).upper()
    if week_type not in {"ODD", "EVEN"}:
        raise ValueError("Неверный тип недели")
    conn = connect()
    cur = conn.execute("DELETE FROM working_hours WHERE COALESCE(week_type,'ALL') = ?", (week_type,))
    conn.commit()
    count = cur.rowcount
    conn.close()
    for weekday in range(7):
        set_teacher_week_day_off(week_type, weekday, False)
    return count

def get_all_working_hours():

    return get_working_hours(
        weekday=None
    )


def delete_working_hours(
    item_id
):

    conn = connect()

    conn.execute("""
        DELETE FROM working_hours
        WHERE id = ?
    """, (
        item_id,
    ))

    conn.commit()
    conn.close()


def clear_working_hours():

    conn = connect()

    conn.execute("""
        DELETE FROM working_hours
    """)

    conn.commit()
    conn.close()


# ============================================================
# SCHEDULE EXCEPTIONS
# ============================================================

def add_schedule_exception(
    date,
    exception_type,
    start_time=None,
    end_time=None,
    comment=None
):

    if exception_type not in {
        "OPEN",
        "CLOSED"
    }:

        raise ValueError(
            "Тип исключения должен быть OPEN или CLOSED."
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO schedule_exceptions (

            date,

            exception_type,

            start_time,
            end_time,

            comment,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?,
            ?
        )
    """, (
        date,
        exception_type,
        start_time,
        end_time,
        comment,
        now_iso()
    ))

    item_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return item_id


def get_schedule_exceptions(
    date=None
):

    conn = connect()

    if date is None:

        rows = conn.execute("""
            SELECT *
            FROM schedule_exceptions

            ORDER BY
                date,
                start_time
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM schedule_exceptions

            WHERE date = ?

            ORDER BY start_time
        """, (
            date,
        )).fetchall()

    conn.close()

    return rows


def delete_schedule_exception(
    item_id
):

    conn = connect()

    conn.execute("""
        DELETE FROM schedule_exceptions
        WHERE id = ?
    """, (
        item_id,
    ))

    conn.commit()
    conn.close()


# ============================================================
# REGULAR SCHEDULE — LEGACY
# ============================================================

def create_regular_schedule(
    user_id,
    study_goal,
    subject,
    weekday,
    start_time,
    duration_minutes
):

    today = date.today()

    return create_regular_schedule_request(

        user_id=user_id,

        study_goal=study_goal,

        subject=subject,

        weekday=weekday,

        start_time=start_time,

        duration_minutes=duration_minutes,

        start_date=today.isoformat(),

        end_date=date(
            today.year,
            12,
            31
        ).isoformat()
    )


def get_regular_schedules(
    user_id=None,
    approved_only=False
):

    conn = connect()

    sql = """
        SELECT *
        FROM regular_schedules

        WHERE active = 1
    """

    params = []

    if user_id is not None:

        sql += """
            AND user_id = ?
        """

        params.append(
            user_id
        )

    if approved_only:

        sql += """
            AND status = 'APPROVED'
        """

    sql += """
        ORDER BY
            weekday,
            start_time
    """

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    return rows


def approve_regular_schedule(
    schedule_id
):

    return approve_regular_schedule_v2(
        schedule_id
    )


# ============================================================
# REGULAR SCHEDULE V2
# ============================================================

def get_regular_schedule(
    schedule_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM regular_schedules

        WHERE id = ?
    """, (
        schedule_id,
    )).fetchone()

    conn.close()

    return row


def get_student_regular_schedules(
    user_id,
    active_only=False
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM regular_schedules

            WHERE
                user_id = ?

                AND active = 1

                AND status IN (
                    'PENDING',
                    'APPROVED',
                    'PAUSED'
                )

            ORDER BY
                weekday,
                start_time
        """, (
            user_id,
        )).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM regular_schedules

            WHERE user_id = ?

            ORDER BY
                created_at DESC
        """, (
            user_id,
        )).fetchall()

    conn.close()

    return rows


def get_pending_regular_schedule_requests():

    conn = connect()

    rows = conn.execute("""
        SELECT

            rs.*,

            u.name,
            u.grade,
            u.telegram_id,
            u.telegram_username

        FROM regular_schedules rs

        JOIN users u
            ON u.id = rs.user_id

        WHERE
            rs.active = 1
            AND rs.status = 'PENDING'

        ORDER BY
            rs.created_at
    """).fetchall()

    conn.close()

    return rows


def get_active_regular_schedules():

    conn = connect()

    rows = conn.execute("""
        SELECT

            rs.*,

            u.name,
            u.telegram_id,
            u.grade

        FROM regular_schedules rs

        JOIN users u
            ON u.id = rs.user_id

        WHERE
            rs.active = 1

            AND rs.status IN (
                'APPROVED',
                'PAUSED'
            )

        ORDER BY
            rs.weekday,
            rs.start_time
    """).fetchall()

    conn.close()

    return rows


def student_has_pending_regular_schedule(
    user_id
):

    conn = connect()

    row = conn.execute("""
        SELECT id
        FROM regular_schedules

        WHERE
            user_id = ?

            AND active = 1

            AND status = 'PENDING'

        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return (
        row is not None
    )


def get_regular_recurring_slots(
    weekday,
    duration_minutes,
    anchor_date=None,
    step_minutes=30,
):
    """Canonical weekly recurring availability for Telegram/Web flows.

    Uses one SQLite connection for working-hours/settings/conflicts so callers
    cannot accidentally observe different DB state between parity checks.
    """
    weekday = int(weekday)
    duration_minutes = int(duration_minutes)
    step_minutes = int(step_minutes)
    if duration_minutes <= 0 or step_minutes <= 0:
        return []

    if anchor_date is None:
        anchor_date = date.today()
    elif isinstance(anchor_date, datetime):
        anchor_date = anchor_date.date()
    elif isinstance(anchor_date, str):
        anchor_date = date.fromisoformat(anchor_date[:10])

    day = anchor_date
    while day.weekday() != weekday:
        day += timedelta(days=1)

    conn = connect()
    try:
        mode = str(get_setting("teacher_week_mode", "SAME", conn=conn) or "SAME").upper()

        def busy(start_value):
            requested_start = datetime.strptime(start_value, "%H:%M")
            requested_end = requested_start + timedelta(minutes=duration_minutes)
            rows = conn.execute(
                """
                SELECT start_time, duration_minutes
                FROM regular_schedules
                WHERE weekday = ?
                  AND (
                    status = 'PENDING'
                    OR (COALESCE(active, 0) = 1 AND status = 'APPROVED')
                  )
                """,
                (weekday,),
            ).fetchall()
            for row in rows:
                existing_start = datetime.strptime(row["start_time"], "%H:%M")
                existing_end = existing_start + timedelta(
                    minutes=int(row["duration_minutes"] or 60)
                )
                if requested_start < existing_end and existing_start < requested_end:
                    return True
            return False

        def slots_for_day(day_obj):
            values = set()
            for row in get_effective_working_hours(day_obj, conn=conn):
                start_dt = datetime.combine(
                    day_obj,
                    datetime.strptime(row["start_time"], "%H:%M").time(),
                )
                end_dt = datetime.combine(
                    day_obj,
                    datetime.strptime(row["end_time"], "%H:%M").time(),
                )
                current = start_dt
                while current + timedelta(minutes=duration_minutes) <= end_dt:
                    value = current.strftime("%H:%M")
                    if not busy(value):
                        values.add(value)
                    current += timedelta(minutes=step_minutes)
            return values

        if mode == "SAME":
            return sorted(slots_for_day(day))

        if not teacher_week_enabled("ODD", conn=conn):
            return []
        if not teacher_week_enabled("EVEN", conn=conn):
            return []

        odd_slots = None
        even_slots = None
        current_day = day
        for _ in range(5):
            kind = teacher_week_kind(current_day)
            values = slots_for_day(current_day)
            if kind == "ODD" and odd_slots is None:
                odd_slots = values
            elif kind == "EVEN" and even_slots is None:
                even_slots = values
            if odd_slots is not None and even_slots is not None:
                break
            current_day += timedelta(days=7)

        if odd_slots is None or even_slots is None:
            return []

        return sorted(odd_slots & even_slots)
    finally:
        conn.close()



def regular_schedule_slot_conflict(
    weekday,
    start_time,
    duration_minutes,
    exclude_schedule_id=None
):

    requested_start = (
        datetime.strptime(
            start_time,
            "%H:%M"
        )
    )

    requested_end = (
        requested_start
        + timedelta(
            minutes=int(
                duration_minutes
            )
        )
    )

    conn = connect()

    sql = """
        SELECT *
        FROM regular_schedules

        WHERE
            weekday = ?

            AND (
                status = 'PENDING'
                OR (
                    active = 1
                    AND status = 'APPROVED'
                )
            )
    """

    params = [
        int(weekday)
    ]

    if exclude_schedule_id is not None:

        sql += """
            AND id != ?
        """

        params.append(
            exclude_schedule_id
        )

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    for row in rows:

        existing_start = (
            datetime.strptime(
                row["start_time"],
                "%H:%M"
            )
        )

        existing_end = (
            existing_start
            + timedelta(
                minutes=int(
                    row[
                        "duration_minutes"
                    ]
                )
            )
        )

        if (
            requested_start < existing_end
            and
            requested_end > existing_start
        ):

            return True

    return False


def _validate_regular_schedule_dates(
    start_date,
    end_date
):

    start_date_obj = (
        datetime.strptime(
            start_date,
            "%Y-%m-%d"
        ).date()
    )

    end_date_obj = (
        datetime.strptime(
            end_date,
            "%Y-%m-%d"
        ).date()
    )

    if (
        end_date_obj
        < start_date_obj
    ):

        raise ValueError(
            "Дата окончания раньше даты начала."
        )

    max_date = date(
        start_date_obj.year,
        12,
        31
    )

    if (
        end_date_obj
        > max_date
    ):

        raise ValueError(
            "Постоянное расписание можно оформить максимум до 31 декабря."
        )

    return (
        start_date_obj,
        end_date_obj
    )


def create_regular_schedule_request(
    user_id,
    study_goal,
    subject,
    weekday,
    start_time,
    duration_minutes,
    start_date,
    end_date,
    comment=None,
    program_id=None
):

    _validate_regular_schedule_dates(
        start_date,
        end_date
    )

    if not 0 <= int(weekday) <= 6:

        raise ValueError(
            "Неверный день недели."
        )

    if student_has_pending_regular_schedule(
        user_id
    ):

        raise ValueError(
            "У вас уже есть заявка на постоянное расписание."
        )

    if regular_schedule_slot_conflict(
        weekday,
        start_time,
        duration_minutes
    ):

        raise ValueError(
            "Этот постоянный слот уже занят или ожидает подтверждения."
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO regular_schedules (

            user_id,

            program_id,

            study_goal,
            subject,

            weekday,

            start_time,

            duration_minutes,

            active,

            student_approved,
            admin_approved,

            start_date,
            end_date,

            status,

            request_source,

            requested_at,

            created_lessons_count,

            comment,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?,
            ?,
            ?,
            1,
            1,
            0,
            ?, ?,
            'PENDING',
            'STUDENT',
            ?,
            0,
            ?,
            ?
        )
    """, (
        user_id,
        program_id,
        study_goal,
        subject,
        int(weekday),
        start_time,
        int(duration_minutes),
        start_date,
        end_date,
        now_iso(),
        comment,
        now_iso()
    ))

    schedule_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return schedule_id


def create_admin_regular_schedule(
    user_id,
    study_goal,
    subject,
    weekday,
    start_time,
    duration_minutes,
    start_date,
    end_date,
    comment=None
):

    _validate_regular_schedule_dates(
        start_date,
        end_date
    )

    if regular_schedule_slot_conflict(
        weekday,
        start_time,
        duration_minutes
    ):

        raise ValueError(
            "Этот постоянный слот уже занят."
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO regular_schedules (

            user_id,

            study_goal,
            subject,

            weekday,

            start_time,

            duration_minutes,

            active,

            student_approved,
            admin_approved,

            start_date,
            end_date,

            status,

            request_source,

            requested_at,
            approved_at,

            created_lessons_count,

            comment,

            created_at
        )

        VALUES (
            ?,
            ?, ?,
            ?,
            ?,
            ?,
            1,
            1,
            1,
            ?, ?,
            'APPROVED',
            'ADMIN',
            ?,
            ?,
            0,
            ?,
            ?
        )
    """, (
        user_id,
        study_goal,
        subject,
        int(weekday),
        start_time,
        int(duration_minutes),
        start_date,
        end_date,
        now_iso(),
        now_iso(),
        comment,
        now_iso()
    ))

    schedule_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return schedule_id


def approve_regular_schedule_v2(
    schedule_id
):

    schedule = get_regular_schedule(
        schedule_id
    )

    if schedule is None:

        raise ValueError(
            "Заявка не найдена."
        )

    if (
        schedule["status"]
        != "PENDING"
    ):

        raise ValueError(
            "Заявка уже обработана."
        )

    if regular_schedule_slot_conflict(
        schedule["weekday"],
        schedule["start_time"],
        schedule["duration_minutes"],
        exclude_schedule_id=schedule_id
    ):

        raise ValueError(
            "Пока заявка ожидала подтверждения, этот слот уже заняли."
        )

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            status = 'APPROVED',

            active = 1,

            admin_approved = 1,

            approved_at = ?,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()

    return True


def reject_regular_schedule(
    schedule_id,
    reason=None
):

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            status = 'REJECTED',

            admin_approved = 0,

            active = 0,

            rejected_at = ?,

            comment = COALESCE(
                ?,
                comment
            ),

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        reason,
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()


def pause_regular_schedule(
    schedule_id,
    pause_until=None
):

    schedule = get_regular_schedule(
        schedule_id
    )

    if schedule is None:

        raise ValueError(
            "Постоянное расписание не найдено."
        )

    if (
        schedule["status"]
        != "APPROVED"
    ):

        raise ValueError(
            "Можно приостановить только активное расписание."
        )

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            status = 'PAUSED',

            pause_until = ?,

            updated_at = ?

        WHERE id = ?
    """, (
        pause_until,
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()


def resume_regular_schedule(
    schedule_id
):

    schedule = get_regular_schedule(
        schedule_id
    )

    if schedule is None:

        raise ValueError(
            "Постоянное расписание не найдено."
        )

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            status = 'APPROVED',

            pause_until = NULL,

            active = 1,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()


def cancel_regular_schedule(
    schedule_id,
    reason=None
):

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            status = 'CANCELLED',

            active = 0,

            cancelled_at = ?,

            comment = COALESCE(
                ?,
                comment
            ),

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        reason,
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()


def get_regular_schedule_dates(
    schedule_id
):

    schedule = get_regular_schedule(
        schedule_id
    )

    if schedule is None:

        return []

    if not (
        schedule["start_date"]
        and
        schedule["end_date"]
    ):

        return []

    start_date_obj = (
        datetime.strptime(
            schedule[
                "start_date"
            ],
            "%Y-%m-%d"
        ).date()
    )

    end_date_obj = (
        datetime.strptime(
            schedule[
                "end_date"
            ],
            "%Y-%m-%d"
        ).date()
    )

    wanted_weekday = int(
        schedule[
            "weekday"
        ]
    )

    current = (
        start_date_obj
    )

    while (
        current.weekday()
        != wanted_weekday
    ):

        current += timedelta(
            days=1
        )

    dates = []

    while (
        current <= end_date_obj
    ):

        dates.append(
            current
        )

        current += timedelta(
            days=7
        )

    return dates


def count_regular_schedule_dates(
    schedule_id
):

    return len(
        get_regular_schedule_dates(
            schedule_id
        )
    )


# ============================================================
# PROMO CODES
# ============================================================

def create_promo_code(
    code,
    discount_type,
    discount_value,
    max_uses=None,
    per_user_limit=1,
    expires_at=None
):

    code = normalize_promo_code(
        code
    )

    if not code:

        raise ValueError(
            "Промокод пуст."
        )

    if discount_type not in {
        "PERCENT",
        "FIXED"
    }:

        raise ValueError(
            "Неверный тип скидки."
        )

    conn = connect()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO promo_codes (

                code,

                discount_type,
                discount_value,

                max_uses,

                uses_count,

                per_user_limit,

                expires_at,

                active,

                created_at
            )

            VALUES (
                ?,
                ?, ?,
                ?,
                0,
                ?,
                ?,
                1,
                ?
            )
        """, (
            code,
            discount_type,
            int(discount_value),
            max_uses,
            per_user_limit,
            expires_at,
            now_iso()
        ))

    except sqlite3.IntegrityError:

        conn.close()

        raise ValueError(
            "Такой промокод уже существует."
        )

    promo_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return promo_id


def get_promo(
    promo_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM promo_codes

        WHERE id = ?
    """, (
        promo_id,
    )).fetchone()

    conn.close()

    return row


def get_promo_by_code(
    code
):

    code = normalize_promo_code(
        code
    )

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM promo_codes

        WHERE code = ?
    """, (
        code,
    )).fetchone()

    conn.close()

    return row


def get_all_promos(
    active_only=False
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM promo_codes

            WHERE active = 1

            ORDER BY id DESC
        """).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM promo_codes

            ORDER BY id DESC
        """).fetchall()

    conn.close()

    return rows


def count_user_promo_uses(
    promo_id,
    user_id
):

    conn = connect()

    count = conn.execute("""
        SELECT COUNT(*)
        FROM promo_code_usages

        WHERE
            promo_id = ?
            AND user_id = ?
    """, (
        promo_id,
        user_id
    )).fetchone()[0]

    conn.close()

    return int(
        count
    )


def validate_promo_code(
    code,
    user_id
):

    promo = get_promo_by_code(
        code
    )

    if promo is None:

        return {
            "valid": False,
            "reason": "Промокод не найден.",
            "promo": None,
        }

    if not promo["active"]:

        return {
            "valid": False,
            "reason": "Промокод отключён.",
            "promo": promo,
        }

    if promo["expires_at"]:

        expires_at = (
            datetime.fromisoformat(
                promo["expires_at"]
            )
        )

        if (
            datetime.now()
            > expires_at
        ):

            return {
                "valid": False,
                "reason": "Срок действия промокода истёк.",
                "promo": promo,
            }

    if (
        promo["max_uses"]
        is not None

        and promo["uses_count"]
        >= promo["max_uses"]
    ):

        return {
            "valid": False,
            "reason": "Лимит промокода исчерпан.",
            "promo": promo,
        }

    if (
        promo["per_user_limit"]
        is not None
    ):

        uses = (
            count_user_promo_uses(
                promo["id"],
                user_id
            )
        )

        if (
            uses
            >= promo["per_user_limit"]
        ):

            return {
                "valid": False,
                "reason": "Вы уже использовали этот промокод.",
                "promo": promo,
            }

    return {
        "valid": True,
        "reason": None,
        "promo": promo,
    }


def calculate_promo_discount(
    amount,
    promo
):

    amount = int(
        amount
    )

    if promo is None:

        return 0

    if (
        promo["discount_type"]
        == "PERCENT"
    ):

        result = round(
            amount
            * int(
                promo[
                    "discount_value"
                ]
            )
            / 100
        )

    else:

        result = int(
            promo[
                "discount_value"
            ]
        )

    return min(
        max(
            result,
            0
        ),
        amount
    )


def toggle_promo(
    promo_id
):

    promo = get_promo(
        promo_id
    )

    if promo is None:

        raise ValueError(
            "Промокод не найден."
        )

    new_value = (
        0
        if promo["active"]
        else 1
    )

    conn = connect()

    conn.execute("""
        UPDATE promo_codes

        SET
            active = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        new_value,
        now_iso(),
        promo_id
    ))

    conn.commit()
    conn.close()

    return bool(
        new_value
    )


def delete_promo(
    promo_id
):

    conn = connect()

    uses = conn.execute("""
        SELECT COUNT(*)
        FROM promo_code_usages

        WHERE promo_id = ?
    """, (
        promo_id,
    )).fetchone()[0]

    if uses:

        conn.execute("""
            UPDATE promo_codes

            SET
                active = 0,
                updated_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            promo_id
        ))

    else:

        conn.execute("""
            DELETE FROM promo_codes
            WHERE id = ?
        """, (
            promo_id,
        ))

    conn.commit()
    conn.close()


def get_promo_usages(
    promo_id
):

    conn = connect()

    rows = conn.execute("""
        SELECT

            pcu.*,

            u.name,
            u.telegram_username

        FROM promo_code_usages pcu

        JOIN users u
            ON u.id = pcu.user_id

        WHERE
            pcu.promo_id = ?

        ORDER BY
            pcu.used_at DESC
    """, (
        promo_id,
    )).fetchall()

    conn.close()

    return rows


# ============================================================
# PACKAGE DISCOUNT
# ============================================================

def calculate_package_discount_percent(
    lessons_count
):

    lessons_count = int(
        lessons_count
    )

    if lessons_count >= 10:

        return 15

    if lessons_count >= 6:

        return 10

    if lessons_count >= 4:

        return 5

    return 0


def calculate_package(
    price_per_lesson,
    lessons_count
):

    price_per_lesson = int(
        price_per_lesson
    )

    lessons_count = int(
        lessons_count
    )

    subtotal = (
        price_per_lesson
        * lessons_count
    )

    discount_percent = (
        calculate_package_discount_percent(
            lessons_count
        )
    )

    discount_amount = round(
        subtotal
        * discount_percent
        / 100
    )

    total = (
        subtotal
        - discount_amount
    )

    return {
        "lessons_count":
            lessons_count,

        "subtotal":
            subtotal,

        "discount_percent":
            discount_percent,

        "discount_amount":
            discount_amount,

        "total":
            total,
    }


# ============================================================
# PAYMENTS
# ============================================================

def create_payment(
    user_id,
    study_goal,
    subject,
    lessons_count,
    price_per_lesson,
    promo_code=None,
    lesson_id=None,
    minutes_total=None,
    base_duration_minutes=None,
    hourly_rate=None,
    program_id=None
):

    package = (
        calculate_package(
            price_per_lesson,
            lessons_count
        )
    )
    # Final tariff center is the source of truth for minute-package discounts.
    # Fall back to the legacy tiers for old/direct calls without a programme.
    if program_id is not None:
        try:
            from final_features.tariffs import package_quote
            _q = package_quote(int(program_id), int(lessons_count))
            package = {
                "lessons_count": int(lessons_count),
                "subtotal": int(_q["subtotal"]),
                "discount_percent": int(_q["discount_percent"]),
                "discount_amount": int(_q["subtotal"] - _q["total"]),
                "total": int(_q["total"]),
            }
        except Exception:
            pass

    # Minute subscription metadata (legacy lesson-count fields remain for compatibility).
    if base_duration_minutes is None:
        base_duration_minutes = 90 if str(study_goal).upper() in {"OGE", "EGE", "OLYMPIAD"} else 60
    base_duration_minutes = int(base_duration_minutes)
    if minutes_total is None:
        minutes_total = int(lessons_count) * base_duration_minutes
    minutes_total = int(minutes_total)
    if hourly_rate is None:
        hourly_rate = round(int(price_per_lesson) * 60 / max(base_duration_minutes, 1))
    hourly_rate = int(hourly_rate)

    promo = None
    promo_discount = 0

    if promo_code:

        validation = (
            validate_promo_code(
                promo_code,
                user_id
            )
        )

        if not validation[
            "valid"
        ]:

            raise ValueError(
                validation["reason"]
            )

        promo = (
            validation["promo"]
        )

        promo_discount = (
            calculate_promo_discount(
                package["total"],
                promo
            )
        )

    total_amount = max(
        package["total"]
        - promo_discount,
        0
    )

    payment_type = (
        "SINGLE"
        if int(
            lessons_count
        ) == 1
        else "PACKAGE"
    )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO payments (

            user_id,

            study_goal,
            subject,

            payment_type,

            lessons_count,
            price_per_lesson,

            subtotal,

            discount_percent,
            package_discount_amount,

            promo_id,
            promo_code,
            promo_discount_amount,

            total_amount,

            lesson_id,

            status,

            created_at
        )

        VALUES (
            ?,
            ?, ?,
            ?,
            ?, ?,
            ?,
            ?, ?,
            ?, ?, ?,
            ?,
            ?,
            'WAITING',
            ?
        )
    """, (
        user_id,
        study_goal,
        subject,
        payment_type,
        int(lessons_count),
        int(price_per_lesson),
        package["subtotal"],
        package[
            "discount_percent"
        ],
        package[
            "discount_amount"
        ],
        promo["id"]
        if promo
        else None,
        promo["code"]
        if promo
        else None,
        promo_discount,
        total_amount,
        lesson_id,
        now_iso()
    ))

    payment_id = (
        cursor.lastrowid
    )

    # Columns are added by core.minute_balance.ensure_schema() before normal use.
    try:
        cursor.execute("""
            UPDATE payments
            SET minutes_total=?, base_duration_minutes=?, hourly_rate=?, program_id=COALESCE(?, program_id)
            WHERE id=?
        """, (minutes_total, base_duration_minutes, hourly_rate, program_id, payment_id))
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

    return payment_id


def get_payment(
    payment_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM payments

        WHERE id = ?
    """, (
        payment_id,
    )).fetchone()

    conn.close()

    return row


def get_payment_for_lesson(
    lesson_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM payments

        WHERE
            lesson_id = ?
            AND status IN (
                'WAITING',
                'RECEIPT_SENT',
                'PAID'
            )

        ORDER BY id DESC
        LIMIT 1
    """, (
        lesson_id,
    )).fetchone()

    conn.close()

    return row


def create_lesson_payment(
    lesson_id,
    promo_code=None
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson["payment_status"] == "PAID":

        raise ValueError(
            "Занятие уже оплачено."
        )

    if lesson["lesson_status"] != "CONFIRMED":

        raise ValueError(
            "Это занятие сейчас нельзя оплатить."
        )

    existing = get_payment_for_lesson(
        lesson_id
    )

    if existing is not None:

        if existing["status"] == "PAID":

            raise ValueError(
                "Занятие уже оплачено."
            )

        return existing["id"]

    return create_payment(
        user_id=lesson["user_id"],
        study_goal=lesson["study_goal"],
        subject=lesson["subject"],
        lessons_count=1,
        price_per_lesson=int(lesson["price"]),
        promo_code=promo_code,
        lesson_id=lesson_id,
    )


def get_user_payments(
    user_id,
    limit=20
):

    conn = connect()

    rows = conn.execute("""
        SELECT *
        FROM payments

        WHERE user_id = ?

        ORDER BY id DESC

        LIMIT ?
    """, (
        user_id,
        int(limit)
    )).fetchall()

    conn.close()

    return rows


def add_receipt(
    payment_id,
    user_id,
    file_id,
    file_type,
    source_platform="TELEGRAM"
):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")
    payment = cursor.execute("SELECT user_id,status FROM payments WHERE id=?", (int(payment_id),)).fetchone()
    if payment is None or int(payment["user_id"]) != int(user_id):
        conn.rollback()
        conn.close()
        raise ValueError("Платёж не найден.")
    if payment["status"] in {"PAID", "REVERSED", "CANCELLED"}:
        conn.rollback()
        conn.close()
        raise ValueError("Этот платёж закрыт. Создайте новый счёт.")

    cursor.execute("""
        INSERT INTO receipts (

            payment_id,
            user_id,

            telegram_file_id,

            source_platform,

            file_type,

            status,

            created_at
        )

        VALUES (
            ?, ?,
            ?,
            ?,
            ?,
            'WAITING',
            ?
        )
    """, (
        payment_id,
        user_id,
        file_id,
        source_platform,
        file_type,
        now_iso()
    ))

    receipt_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        UPDATE payments

        SET status = 'RECEIPT_SENT'

        WHERE id = ?
    """, (
        payment_id,
    ))

    conn.commit()
    conn.close()

    return receipt_id


def approve_payment(
    payment_id, *, verify_in_transaction=None
):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    payment = cursor.execute("""
        SELECT *
        FROM payments

        WHERE id = ?
    """, (
        payment_id,
    )).fetchone()

    if payment is None:

        conn.rollback()
        conn.close()

        raise ValueError(
            "Платёж не найден."
        )

    # Provider verification/audit runs under the same write lock as crediting.
    # Only trusted server code may supply this callback (never HTTP input).
    if verify_in_transaction is not None:
        try:
            verify_in_transaction(conn, payment)
        except Exception:
            conn.rollback()
            conn.close()
            raise

    if payment["status"] == "REVERSED":
        conn.rollback()
        conn.close()
        raise ValueError("Это подтверждение отменено. Создайте новый платёж.")

    if (
        payment["status"]
        == "PAID"
    ):

        package = cursor.execute(
            "SELECT id FROM lesson_packages WHERE payment_id=? ORDER BY id LIMIT 1",
            (int(payment_id),),
        ).fetchone()

        conn.rollback()
        conn.close()

        if package is None:
            raise ValueError(
                "Подтверждённый платёж не имеет связанного пакета."
            )

        try:
            from core import minute_balance
            minute_balance.credit_confirmed_payment(int(payment_id), int(package["id"]))
        except Exception as error:
            print("MINUTE CREDIT RETRY ERROR:", error)

        return int(package["id"])

    # ========================================================
    # ОПЛАТА КОНКРЕТНОГО НАЗНАЧЕННОГО ЗАНЯТИЯ
    # ========================================================

    if (
        "lesson_id" in payment.keys()
        and payment["lesson_id"]
    ):

        lesson = cursor.execute("""
            SELECT *
            FROM lessons
            WHERE id = ?
        """, (
            payment["lesson_id"],
        )).fetchone()

        if lesson is None:

            conn.rollback()
            conn.close()

            raise ValueError(
                "Связанное занятие не найдено."
            )

        if lesson["payment_status"] == "PAID":

            conn.rollback()
            conn.close()

            raise ValueError(
                "Это занятие уже оплачено."
            )

        cursor.execute("""
            UPDATE payments

            SET
                status = 'PAID',
                confirmed_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            payment_id
        ))

        cursor.execute("""
            UPDATE receipts

            SET
                status = 'APPROVED',
                reviewed_at = ?

            WHERE
                payment_id = ?
                AND status = 'WAITING'
        """, (
            now_iso(),
            payment_id
        ))

        cursor.execute("""
            INSERT INTO lesson_packages (

                payment_id,
                user_id,
                study_goal,
                subject,
                lessons_total,
                lessons_used,
                price_per_lesson,
                discount_percent,
                amount_paid,
                status,
                source_type,
                created_at
            )

            VALUES (
                ?,
                ?,
                ?, ?,
                1,
                1,
                ?,
                0,
                ?,
                'USED',
                'PAID',
                ?
            )
        """, (
            payment["id"],
            payment["user_id"],
            payment["study_goal"],
            payment["subject"],
            payment["price_per_lesson"],
            payment["total_amount"],
            now_iso()
        ))

        package_id = cursor.lastrowid

        cursor.execute("""
            UPDATE lessons

            SET
                payment_status = 'PAID',
                payment_id = ?,
                package_id = ?,
                charged = 1,
                payment_deadline = NULL,
                updated_at = ?

            WHERE id = ?
        """, (
            payment_id,
            package_id,
            now_iso(),
            payment["lesson_id"]
        ))

        if payment["promo_id"]:

            cursor.execute("""
                INSERT INTO promo_code_usages (
                    promo_id,
                    user_id,
                    payment_id,
                    discount_amount,
                    used_at
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                payment["promo_id"],
                payment["user_id"],
                payment["id"],
                payment["promo_discount_amount"],
                now_iso()
            ))

            cursor.execute("""
                UPDATE promo_codes

                SET
                    uses_count = uses_count + 1,
                    updated_at = ?

                WHERE id = ?
            """, (
                now_iso(),
                payment["promo_id"]
            ))

        conn.commit()
        conn.close()

        try:
            from core import minute_balance
            minute_balance.credit_confirmed_payment(payment_id, package_id)
        except Exception as error:
            print("MINUTE CREDIT ERROR:", error)

        return package_id

    cursor.execute("""
        UPDATE payments

        SET
            status = 'PAID',
            confirmed_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        payment_id
    ))

    cursor.execute("""
        UPDATE receipts

        SET
            status = 'APPROVED',
            reviewed_at = ?

        WHERE
            payment_id = ?
            AND status = 'WAITING'
    """, (
        now_iso(),
        payment_id
    ))

    cursor.execute("""
        INSERT INTO lesson_packages (

            payment_id,

            user_id,

            study_goal,
            subject,

            lessons_total,
            lessons_used,

            price_per_lesson,

            discount_percent,

            amount_paid,

            status,

            source_type,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?, 0,
            ?,
            ?,
            ?,
            'ACTIVE',
            'PAID',
            ?
        )
    """, (
        payment["id"],
        payment["user_id"],
        payment["study_goal"],
        payment["subject"],
        payment["lessons_count"],
        payment[
            "price_per_lesson"
        ],
        payment[
            "discount_percent"
        ],
        payment[
            "total_amount"
        ],
        now_iso()
    ))

    package_id = (
        cursor.lastrowid
    )

    if payment["promo_id"]:

        cursor.execute("""
            INSERT INTO promo_code_usages (

                promo_id,
                user_id,
                payment_id,

                discount_amount,

                used_at
            )

            VALUES (
                ?, ?, ?,
                ?,
                ?
            )
        """, (
            payment["promo_id"],
            payment["user_id"],
            payment["id"],
            payment[
                "promo_discount_amount"
            ],
            now_iso()
        ))

        cursor.execute("""
            UPDATE promo_codes

            SET
                uses_count =
                    uses_count + 1,

                updated_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            payment["promo_id"]
        ))

    conn.commit()
    conn.close()

    try:
        from core import minute_balance
        minute_balance.credit_confirmed_payment(payment_id, package_id)
    except Exception as error:
        print("MINUTE CREDIT ERROR:", error)

    return package_id


def reject_payment(
    payment_id
):

    conn = connect()

    conn.execute("""
        UPDATE payments

        SET status = 'REJECTED'

        WHERE
            id = ?
            AND status != 'PAID'
    """, (
        payment_id,
    ))

    conn.execute("""
        UPDATE receipts

        SET
            status = 'REJECTED',
            reviewed_at = ?

        WHERE
            payment_id = ?
            AND status = 'WAITING'
    """, (
        now_iso(),
        payment_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# BALANCE
# ============================================================

def get_active_packages(
    user_id,
    study_goal=None,
    subject=None,
    price_per_lesson=None
):

    conn = connect()

    sql = """
        SELECT *
        FROM lesson_packages

        WHERE
            user_id = ?
            AND status = 'ACTIVE'
            AND lessons_used < lessons_total
    """

    params = [user_id]

    # Новая модель баланса: пакет совместим с любым направлением
    # ученика, если совпадает номинал одного занятия.
    if price_per_lesson is not None:
        if study_goal and subject:
            sql += """
                AND (
                    price_per_lesson = ?
                    OR (
                        source_type = 'BONUS'
                        AND price_per_lesson = 0
                        AND study_goal = ?
                        AND subject = ?
                    )
                )
            """
            params.extend([int(price_per_lesson), study_goal, subject])
        else:
            sql += " AND price_per_lesson = ? "
            params.append(int(price_per_lesson))
    else:
        # Совместимость со старым кодом/старыми пакетами.
        if study_goal:
            sql += " AND study_goal = ? "
            params.append(study_goal)
        if subject:
            sql += " AND subject = ? "
            params.append(subject)

    sql += """
        ORDER BY
            CASE WHEN source_type = 'BONUS' THEN 0 ELSE 1 END,
            created_at,
            id
    """

    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return rows


def get_balance_breakdown(
    user_id,
    study_goal=None,
    subject=None,
    price_per_lesson=None
):

    packages = get_active_packages(
        user_id,
        study_goal,
        subject,
        price_per_lesson=price_per_lesson,
    )

    paid = 0
    bonus = 0

    for package in packages:
        remaining = package["lessons_total"] - package["lessons_used"]
        if package["source_type"] == "BONUS":
            bonus += remaining
        else:
            paid += remaining

    return {"paid": paid, "bonus": bonus, "total": paid + bonus}


def get_prepaid_lessons_remaining(
    user_id,
    study_goal=None,
    subject=None,
    price_per_lesson=None
):
    return get_balance_breakdown(
        user_id,
        study_goal,
        subject,
        price_per_lesson=price_per_lesson,
    )["total"]


def use_prepaid_lesson(
    user_id,
    study_goal=None,
    subject=None,
    price_per_lesson=None
):

    conn = connect()
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")

    sql = """
        SELECT *
        FROM lesson_packages
        WHERE user_id = ?
          AND status = 'ACTIVE'
          AND lessons_used < lessons_total
    """
    params = [user_id]

    if price_per_lesson is not None:
        if study_goal and subject:
            sql += """
                AND (
                    price_per_lesson = ?
                    OR (
                        source_type = 'BONUS'
                        AND price_per_lesson = 0
                        AND study_goal = ?
                        AND subject = ?
                    )
                )
            """
            params.extend([int(price_per_lesson), study_goal, subject])
        else:
            sql += " AND price_per_lesson = ? "
            params.append(int(price_per_lesson))
    else:
        if study_goal:
            sql += " AND study_goal = ? "
            params.append(study_goal)
        if subject:
            sql += " AND subject = ? "
            params.append(subject)

    sql += """
        ORDER BY
            CASE WHEN source_type = 'BONUS' THEN 0 ELSE 1 END,
            created_at,
            id
        LIMIT 1
    """

    package = cursor.execute(sql, tuple(params)).fetchone()

    if package is None:
        conn.rollback()
        conn.close()
        return None

    new_used = package["lessons_used"] + 1
    new_status = "USED" if new_used >= package["lessons_total"] else "ACTIVE"

    cursor.execute(
        "UPDATE lesson_packages SET lessons_used = ?, status = ? WHERE id = ?",
        (new_used, new_status, package["id"]),
    )
    conn.commit()
    conn.close()
    return package["id"]


def refund_prepaid_lesson(
    package_id
):

    if not package_id:

        return False

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    package = cursor.execute("""
        SELECT *
        FROM lesson_packages

        WHERE id = ?
    """, (
        package_id,
    )).fetchone()

    if package is None:

        conn.rollback()
        conn.close()

        return False

    if (
        package[
            "lessons_used"
        ] <= 0
    ):

        conn.rollback()
        conn.close()

        return False

    cursor.execute("""
        UPDATE lesson_packages

        SET
            lessons_used =
                lessons_used - 1,

            status = 'ACTIVE'

        WHERE id = ?
    """, (
        package_id,
    ))

    conn.commit()
    conn.close()

    return True


def refund_lesson_balance(lesson_id, package_id=None):
    """Refund exact minute reservations when present, otherwise legacy package unit."""
    try:
        from core import minute_balance
        if minute_balance.refund_lesson_minutes(int(lesson_id)):
            return True
    except Exception:
        pass
    return refund_prepaid_lesson(package_id) if package_id else False


# ============================================================
# BONUS LESSONS
# ============================================================

def add_bonus_lessons(
    user_id,
    lessons_count,
    study_goal,
    subject,
    reason="EXTRA_TIME",
    price_per_lesson=0
):

    lessons_count = int(
        lessons_count
    )

    if lessons_count <= 0:

        return None

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    cursor.execute("""
        INSERT INTO payments (

            user_id,

            study_goal,
            subject,

            payment_type,

            lessons_count,
            price_per_lesson,

            subtotal,

            discount_percent,
            package_discount_amount,

            promo_discount_amount,

            total_amount,

            status,

            created_at,
            confirmed_at
        )

        VALUES (
            ?,
            ?, ?,
            'BONUS',
            ?, ?,
            0,
            0,
            0,
            0,
            0,
            'PAID',
            ?,
            ?
        )
    """, (
        user_id,
        study_goal,
        subject,
        lessons_count,
        int(price_per_lesson),
        now_iso(),
        now_iso()
    ))

    payment_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        INSERT INTO lesson_packages (

            payment_id,

            user_id,

            study_goal,
            subject,

            lessons_total,
            lessons_used,

            price_per_lesson,

            discount_percent,

            amount_paid,

            status,

            source_type,

            bonus_reason,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?, 0,
            ?,
            0,
            0,
            'ACTIVE',
            'BONUS',
            ?,
            ?
        )
    """, (
        payment_id,
        user_id,
        study_goal,
        subject,
        lessons_count,
        int(price_per_lesson),
        reason,
        now_iso()
    ))

    package_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        UPDATE users

        SET
            bonus_lessons_earned =
                COALESCE(
                    bonus_lessons_earned,
                    0
                ) + ?,

            updated_at = ?

        WHERE id = ?
    """, (
        lessons_count,
        now_iso(),
        user_id
    ))

    conn.commit()
    conn.close()

    return package_id


# ============================================================
# LESSON HELPERS
# ============================================================

def get_lesson(
    lesson_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM lessons

        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    conn.close()

    return row


def get_hours_until_lesson(
    lesson
):

    start_dt = (
        datetime.fromisoformat(
            lesson[
                "start_time"
            ]
        )
    )

    if start_dt.tzinfo:

        now = datetime.now(
            tz=start_dt.tzinfo
        )

    else:

        now = datetime.now()

    delta = (
        start_dt
        - now
    )

    return (
        delta.total_seconds()
        / 3600
    )


def has_pending_booking(
    user_id
):

    conn = connect()

    row = conn.execute("""
        SELECT id
        FROM lessons

        WHERE
            user_id = ?

            AND request_source = 'STUDENT'

            AND lesson_status = 'PENDING'

        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return (
        row is not None
    )


def get_pending_booking(
    user_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            user_id = ?

            AND request_source = 'STUDENT'

            AND lesson_status = 'PENDING'

        ORDER BY created_at DESC

        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return row


def has_student_lesson_on_date(
    user_id,
    date_value
):

    if isinstance(
        date_value,
        date
    ):

        date_value = (
            date_value.isoformat()
        )

    conn = connect()

    row = conn.execute("""
        SELECT id
        FROM lessons

        WHERE
            user_id = ?

            AND DATE(start_time) = ?

            AND lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS',
                'COMPLETED'
            )

        LIMIT 1
    """, (
        user_id,
        date_value
    )).fetchone()

    conn.close()

    return (
        row is not None
    )


def is_slot_reserved(
    start_time,
    end_time,
    exclude_lesson_id=None
):

    conn = connect()

    sql = """
        SELECT id
        FROM lessons

        WHERE
            lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS'
            )

            AND start_time < ?

            AND end_time > ?
    """

    params = [
        end_time,
        start_time
    ]

    if exclude_lesson_id:

        sql += """
            AND id != ?
        """

        params.append(
            exclude_lesson_id
        )

    sql += """
        LIMIT 1
    """

    row = conn.execute(
        sql,
        tuple(params)
    ).fetchone()

    conn.close()

    return (
        row is not None
    )


# ============================================================
# ONE-OFF BOOKING DRAFTS
# ============================================================

def save_booking_draft(
    user_id,
    program_id,
    study_goal,
    subject,
    start_time,
    end_time,
    duration_minutes,
    hourly_rate,
    price,
):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE booking_drafts
        SET status = 'CANCELLED',
            updated_at = ?
        WHERE user_id = ?
          AND status = 'DRAFT'
        """,
        (
            now_iso(),
            int(user_id),
        ),
    )

    cursor.execute(
        """
        INSERT INTO booking_drafts (
            user_id,
            program_id,
            study_goal,
            subject,
            start_time,
            end_time,
            duration_minutes,
            hourly_rate,
            price,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
        """,
        (
            int(user_id),
            int(program_id),
            study_goal,
            subject,
            start_time,
            end_time,
            int(duration_minutes),
            int(hourly_rate),
            int(price),
            now_iso(),
            now_iso(),
        ),
    )

    draft_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return draft_id


def get_booking_draft(draft_id, user_id=None):
    conn = connect()

    if user_id is None:
        row = conn.execute(
            """
            SELECT *
            FROM booking_drafts
            WHERE id = ?
            """,
            (int(draft_id),),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT *
            FROM booking_drafts
            WHERE id = ?
              AND user_id = ?
            """,
            (
                int(draft_id),
                int(user_id),
            ),
        ).fetchone()

    conn.close()
    return row


def get_active_booking_draft(user_id):
    conn = connect()

    row = conn.execute(
        """
        SELECT *
        FROM booking_drafts
        WHERE user_id = ?
          AND status IN (
              'DRAFT',
              'PAYMENT_PENDING',
              'PAYMENT_ATTACHED',
              'NEEDS_NEW_TIME',
              'NEEDS_PAYMENT_FIX'
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(user_id),),
    ).fetchone()

    conn.close()
    return row


def update_booking_draft(
    draft_id,
    *,
    status=None,
    payment_choice=None,
    payment_id=None,
    start_time=None,
    end_time=None,
    rejection_reason=None,
):
    fields = []
    params = []

    values = {
        "status": status,
        "payment_choice": payment_choice,
        "payment_id": payment_id,
        "start_time": start_time,
        "end_time": end_time,
        "rejection_reason": rejection_reason,
    }

    for field, value in values.items():
        if value is not None:
            fields.append(f"{field} = ?")
            params.append(value)

    if not fields:
        return

    fields.append("updated_at = ?")
    params.append(now_iso())
    params.append(int(draft_id))

    conn = connect()

    conn.execute(
        f"""
        UPDATE booking_drafts
        SET {", ".join(fields)}
        WHERE id = ?
        """,
        tuple(params),
    )

    conn.commit()
    conn.close()


def cancel_booking_draft(draft_id, user_id):
    conn = connect()

    conn.execute(
        """
        UPDATE booking_drafts
        SET status = 'CANCELLED',
            updated_at = ?
        WHERE id = ?
          AND user_id = ?
          AND status NOT IN ('SUBMITTED', 'CONFIRMED')
        """,
        (
            now_iso(),
            int(draft_id),
            int(user_id),
        ),
    )

    conn.commit()
    conn.close()



def approve_paid_booking_draft_payment(payment_id):
    """
    Подтверждает оплату, которая относится к разовому booking_draft.

    ВАЖНО:
    это НЕ покупка свободного пакета минут.
    Оплаченные минуты сразу считаются использованными конкретным занятием.

    Возвращает:
        None                         — если payment не относится к booking_draft
        (package_id, lesson_id)      — если обработано
    """
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")

    payment = cursor.execute(
        """
        SELECT *
        FROM payments
        WHERE id = ?
        """,
        (int(payment_id),),
    ).fetchone()

    if payment is None:
        conn.rollback()
        conn.close()
        raise ValueError("Платёж не найден.")

    if payment["status"] == "REVERSED":
        conn.rollback()
        conn.close()
        raise ValueError("Это подтверждение отменено. Создайте новый платёж.")

    draft = cursor.execute(
        """
        SELECT *
        FROM booking_drafts
        WHERE payment_id = ?
          AND status IN (
              'DRAFT',
              'PAYMENT_PENDING',
              'PAYMENT_ATTACHED',
              'SUBMITTED'
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(payment_id),),
    ).fetchone()

    if draft is None:
        conn.rollback()
        conn.close()
        return None

    if payment["status"] == "PAID":
        conn.rollback()
        conn.close()
        raise ValueError("Платёж уже подтверждён.")

    # Не создаём второй урок при повторной обработке.
    lesson = cursor.execute(
        """
        SELECT *
        FROM lessons
        WHERE user_id = ?
          AND start_time = ?
          AND end_time = ?
          AND lesson_status IN (
              'PENDING',
              'CONFIRMED',
              'IN_PROGRESS'
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (
            int(draft["user_id"]),
            draft["start_time"],
            draft["end_time"],
        ),
    ).fetchone()

    cursor.execute(
        """
        UPDATE payments
        SET status = 'PAID',
            confirmed_at = ?
        WHERE id = ?
        """,
        (
            now_iso(),
            int(payment_id),
        ),
    )

    cursor.execute(
        """
        UPDATE receipts
        SET status = 'APPROVED',
            reviewed_at = ?
        WHERE payment_id = ?
          AND status = 'WAITING'
        """,
        (
            now_iso(),
            int(payment_id),
        ),
    )

    # Разовая оплата — пакет технически создаём для совместимости,
    # но сразу считаем его полностью использованным.
    cursor.execute(
        """
        INSERT INTO lesson_packages (
            payment_id,
            user_id,
            study_goal,
            subject,
            lessons_total,
            lessons_used,
            price_per_lesson,
            discount_percent,
            amount_paid,
            status,
            source_type,
            created_at
        )
        VALUES (
            ?,
            ?,
            ?, ?,
            1,
            1,
            ?,
            ?,
            ?,
            'USED',
            'PAID',
            ?
        )
        """,
        (
            int(payment["id"]),
            int(payment["user_id"]),
            payment["study_goal"],
            payment["subject"],
            int(payment["price_per_lesson"]),
            int(payment["discount_percent"] or 0),
            int(payment["total_amount"]),
            now_iso(),
        ),
    )

    package_id = int(cursor.lastrowid)

    if lesson is None:
        cursor.execute(
            """
            INSERT INTO lessons (
                user_id,
                program_id,
                study_goal,
                subject,
                start_time,
                end_time,
                duration_minutes,
                hourly_rate,
                price,
                lesson_status,
                request_source,
                requested_at,
                approved_at,
                payment_status,
                payment_id,
                package_id,
                charged,
                is_trial,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                'CONFIRMED',
                'STUDENT',
                ?,
                ?,
                'PAID',
                ?,
                ?,
                1,
                0,
                ?,
                ?
            )
            """,
            (
                int(draft["user_id"]),
                int(draft["program_id"]),
                draft["study_goal"],
                draft["subject"],
                draft["start_time"],
                draft["end_time"],
                int(draft["duration_minutes"]),
                int(draft["hourly_rate"]),
                int(draft["price"]),
                now_iso(),
                now_iso(),
                int(payment_id),
                int(package_id),
                now_iso(),
                now_iso(),
            ),
        )

        lesson_id = int(cursor.lastrowid)

    else:
        lesson_id = int(lesson["id"])

        cursor.execute(
            """
            UPDATE lessons
            SET lesson_status = 'CONFIRMED',
                payment_status = 'PAID',
                payment_id = ?,
                package_id = ?,
                charged = 1,
                approved_at = COALESCE(approved_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (
                int(payment_id),
                int(package_id),
                now_iso(),
                now_iso(),
                int(lesson_id),
            ),
        )

    cursor.execute(
        """
        UPDATE payments
        SET lesson_id = ?
        WHERE id = ?
        """,
        (
            int(lesson_id),
            int(payment_id),
        ),
    )

    cursor.execute(
        """
        UPDATE booking_drafts
        SET status = 'CONFIRMED',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now_iso(),
            int(draft["id"]),
        ),
    )

    if payment["promo_id"]:
        existing_usage = cursor.execute(
            """
            SELECT id
            FROM promo_code_usages
            WHERE payment_id = ?
            LIMIT 1
            """,
            (int(payment_id),),
        ).fetchone()

        if existing_usage is None:
            cursor.execute(
                """
                INSERT INTO promo_code_usages (
                    promo_id,
                    user_id,
                    payment_id,
                    discount_amount,
                    used_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(payment["promo_id"]),
                    int(payment["user_id"]),
                    int(payment_id),
                    int(payment["promo_discount_amount"] or 0),
                    now_iso(),
                ),
            )

            cursor.execute(
                """
                UPDATE promo_codes
                SET uses_count = uses_count + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    now_iso(),
                    int(payment["promo_id"]),
                ),
            )

    conn.commit()
    conn.close()

    # Заполняем минутные compatibility-поля.
    # lessons_used=1 => minutes_used станет равен minutes_total,
    # поэтому свободный баланс НЕ увеличится.
    try:
        from core import minute_balance
        minute_balance.credit_confirmed_payment(
            int(payment_id),
            int(package_id),
        )
    except Exception as error:
        print(
            "DIRECT DRAFT MINUTE METADATA ERROR:",
            repr(error),
        )

    return int(package_id), int(lesson_id)



def confirm_paid_booking_draft(payment_id):
    conn = connect()
    cursor = conn.cursor()

    cursor.execute("BEGIN IMMEDIATE")

    draft = cursor.execute(
        """
        SELECT *
        FROM booking_drafts
        WHERE payment_id = ?
          AND status IN (
              'PAYMENT_PENDING',
              'PAYMENT_ATTACHED',
              'DRAFT'
          )
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(payment_id),),
    ).fetchone()

    if draft is None:
        conn.rollback()
        conn.close()
        return None

    existing = cursor.execute(
        """
        SELECT id
        FROM lessons
        WHERE user_id = ?
          AND start_time = ?
          AND end_time = ?
          AND lesson_status IN (
              'PENDING',
              'CONFIRMED',
              'IN_PROGRESS'
          )
        LIMIT 1
        """,
        (
            int(draft["user_id"]),
            draft["start_time"],
            draft["end_time"],
        ),
    ).fetchone()

    if existing:
        cursor.execute(
            """
            UPDATE booking_drafts
            SET status = 'CONFIRMED',
                updated_at = ?
            WHERE id = ?
            """,
            (
                now_iso(),
                int(draft["id"]),
            ),
        )

        conn.commit()
        conn.close()

        return int(existing["id"])

    cursor.execute(
        """
        INSERT INTO lessons (
            user_id,
            program_id,
            study_goal,
            subject,
            start_time,
            end_time,
            duration_minutes,
            hourly_rate,
            price,
            lesson_status,
            request_source,
            requested_at,
            payment_status,
            charged,
            is_trial,
            created_at
        )
        VALUES (
            ?, ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            'CONFIRMED',
            'STUDENT',
            ?,
            'PAID',
            0,
            0,
            ?
        )
        """,
        (
            int(draft["user_id"]),
            int(draft["program_id"]),
            draft["study_goal"],
            draft["subject"],
            draft["start_time"],
            draft["end_time"],
            int(draft["duration_minutes"]),
            int(draft["hourly_rate"]),
            int(draft["price"]),
            now_iso(),
            now_iso(),
        ),
    )

    lesson_id = cursor.lastrowid

    cursor.execute(
        """
        UPDATE payments
        SET lesson_id = ?
        WHERE id = ?
        """,
        (
            int(lesson_id),
            int(payment_id),
        ),
    )

    cursor.execute(
        """
        UPDATE booking_drafts
        SET status = 'CONFIRMED',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now_iso(),
            int(draft["id"]),
        ),
    )

    conn.commit()
    conn.close()

    return int(lesson_id)


# ============================================================
# STUDENT LESSON REQUEST
# ============================================================

def create_lesson_request(
    user_id,
    study_goal,
    subject,
    start_time,
    end_time,
    duration_minutes,
    hourly_rate,
    price,
    is_trial=False,
    program_id=None
):

    start_dt = (
        datetime.fromisoformat(
            start_time
        )
    )

    if has_pending_booking(
        user_id
    ):

        raise ValueError(
            "У вас уже есть заявка на подтверждении."
        )

    if has_student_lesson_on_date(
        user_id,
        start_dt.date()
    ):

        raise ValueError(
            "В этот день у вас уже есть занятие или заявка."
        )

    if is_slot_reserved(
        start_time,
        end_time
    ):

        raise ValueError(
            "Это время уже занято."
        )

    if not is_trial:
        from core import minute_balance
        available_minutes = minute_balance.get_balance(
            user_id, hourly_rate=int(hourly_rate)
        )["total"]
        if available_minutes < int(duration_minutes):
            raise ValueError(
                f"Недостаточно минут на балансе. Доступно: {available_minutes} мин, "
                f"нужно: {int(duration_minutes)} мин."
            )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO lessons (

            user_id,

            program_id,

            study_goal,
            subject,

            start_time,
            end_time,

            duration_minutes,

            hourly_rate,
            price,

            lesson_status,

            request_source,

            requested_at,

            payment_status,

            charged,

            is_trial,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?, ?,
            ?,
            ?, ?,
            'PENDING',
            'STUDENT',
            ?,
            ?,
            0,
            ?,
            ?
        )
    """, (
        user_id,
        program_id,
        study_goal,
        subject,
        start_time,
        end_time,
        int(duration_minutes),
        int(hourly_rate),
        int(price),
        now_iso(),
        (
            "FREE"
            if is_trial
            else "RESERVED_BALANCE"
        ),
        int(bool(is_trial)),
        now_iso()
    ))

    lesson_id = (
        cursor.lastrowid
    )

    conn.commit()
    conn.close()

    return lesson_id


def approve_lesson_request(
    lesson_id,
    google_event_id=None
):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    lesson = cursor.execute("""
        SELECT *
        FROM lessons

        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    if lesson is None:

        conn.rollback()
        conn.close()

        raise ValueError(
            "Заявка не найдена."
        )

    if (
        lesson[
            "lesson_status"
        ] != "PENDING"
    ):

        conn.rollback()
        conn.close()

        raise ValueError(
            "Заявка уже обработана."
        )

    if lesson["is_trial"]:

        user = cursor.execute("""
            SELECT *
            FROM users

            WHERE id = ?
        """, (
            lesson["user_id"],
        )).fetchone()

        if user["trial_used"]:

            conn.rollback()
            conn.close()

            raise ValueError(
                "Пробное уже использовано."
            )

        cursor.execute("""
            UPDATE lessons

            SET
                lesson_status = 'CONFIRMED',

                payment_status = 'FREE',

                charged = 0,

                approved_at = ?,

                google_event_id = ?,

                updated_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            google_event_id,
            now_iso(),
            lesson_id
        ))

        # Пробное считается использованным только после фактического завершения занятия.
        conn.commit()
        conn.close()

        return None

    # Minute model: approve first, then reserve exactly the planned minutes.
    cursor.execute("""
        UPDATE lessons
        SET lesson_status='CONFIRMED', approved_at=?, google_event_id=?, updated_at=?
        WHERE id=?
    """, (now_iso(), google_event_id, now_iso(), lesson_id))
    conn.commit()
    conn.close()

    from core import minute_balance
    minute_balance.reserve_minutes(
        lesson["user_id"], int(lesson["hourly_rate"]), int(lesson["duration_minutes"]), lesson_id
    )
    updated = get_lesson(lesson_id)
    return updated["package_id"] if updated else None


def reject_lesson_request(
    lesson_id,
    reason=None
):

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'REJECTED',

            rejected_at = ?,

            cancellation_reason = ?,

            updated_at = ?

        WHERE
            id = ?
            AND lesson_status = 'PENDING'
    """, (
        now_iso(),
        reason,
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


def cancel_pending_request(
    lesson_id,
    user_id
):

    conn = connect()

    lesson = conn.execute("""
        SELECT *
        FROM lessons

        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    if (
        lesson is None

        or lesson[
            "user_id"
        ] != user_id
    ):

        conn.close()

        raise ValueError(
            "Заявка не найдена."
        )

    if (
        lesson[
            "lesson_status"
        ] != "PENDING"
    ):

        conn.close()

        raise ValueError(
            "Эту заявку уже нельзя отменить."
        )

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',

            cancelled_at = ?,

            cancellation_reason =
                'STUDENT_CANCELLED_PENDING',

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# ADMIN LESSON
# ============================================================

def create_admin_lesson(
    user_id,
    study_goal,
    subject,
    start_time,
    end_time,
    duration_minutes,
    hourly_rate,
    price,
    payment_mode="BALANCE",
    is_trial=False,
    google_event_id=None,
    force=False,
    regular_schedule_id=None
):

    if (
        not force

        and is_slot_reserved(
            start_time,
            end_time
        )
    ):

        raise ValueError(
            "Это время уже занято."
        )

    payment_mode = (
        str(payment_mode)
        .upper()
    )

    if payment_mode not in {
        "BALANCE",
        "AWAITING_PAYMENT",
        "FREE",
        "RESERVED",
    }:

        raise ValueError(
            "Неверный режим оплаты."
        )

    payment_status = "UNPAID"
    package_id = None
    charged = 0

    start_dt = (
        datetime.fromisoformat(
            start_time
        )
    )

    deadline_dt = (
        start_dt
        - timedelta(hours=2)
    )

    if payment_mode == "FREE":

        payment_status = "FREE"

    elif (
        payment_mode
        == "AWAITING_PAYMENT"
    ):

        payment_status = (
            "AWAITING_PAYMENT"
        )

    elif (
        payment_mode
        == "RESERVED"
    ):

        payment_status = (
            "RESERVED_BALANCE"
        )

    elif payment_mode == "BALANCE":
        from core import minute_balance
        available_minutes = minute_balance.get_balance(
            user_id, hourly_rate=int(hourly_rate)
        )["total"]
        if available_minutes < int(duration_minutes):
            raise ValueError(
                f"Недостаточно минут на балансе. Доступно: {available_minutes} мин, "
                f"нужно: {int(duration_minutes)} мин."
            )
        payment_status = "RESERVED_BALANCE"
        charged = 0

    conn = connect()
    cursor = conn.cursor()

    try:

        cursor.execute("""
            INSERT INTO lessons (

                user_id,

                study_goal,
                subject,

                start_time,
                end_time,

                duration_minutes,

                hourly_rate,
                price,

                lesson_status,

                request_source,

                requested_at,
                approved_at,

                payment_status,

                payment_deadline,

                package_id,

                charged,

                is_trial,
                is_regular,

                regular_schedule_id,

                google_event_id,

                created_at
            )

            VALUES (
                ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?,
                'CONFIRMED',
                'ADMIN',
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
        """, (
            user_id,
            study_goal,
            subject,
            start_time,
            end_time,
            int(duration_minutes),
            int(hourly_rate),
            int(price),
            now_iso(),
            now_iso(),
            payment_status,
            (
                deadline_dt.isoformat(
                    timespec="seconds"
                )
                if payment_mode
                == "AWAITING_PAYMENT"
                else None
            ),
            package_id,
            charged,
            int(bool(is_trial)),
            int(
                regular_schedule_id
                is not None
            ),
            regular_schedule_id,
            google_event_id,
            now_iso()
        ))

        lesson_id = (
            cursor.lastrowid
        )

        conn.commit()
        conn.close()

        if payment_mode == "BALANCE":
            from core import minute_balance
            minute_balance.reserve_minutes(user_id, int(hourly_rate), int(duration_minutes), lesson_id)

        return lesson_id

    except Exception:

        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass

        if 'lesson_id' in locals() and payment_mode == "BALANCE":
            try:
                from core import minute_balance
                minute_balance.refund_lesson_minutes(lesson_id)
            except Exception:
                pass

        raise


# ============================================================
# REGULAR LESSON GENERATION
# ============================================================

def regular_lesson_exists(
    schedule_id,
    lesson_date
):

    conn = connect()

    row = conn.execute("""
        SELECT id
        FROM lessons

        WHERE
            regular_schedule_id = ?

            AND DATE(start_time) = ?

            AND lesson_status NOT IN (
                'REJECTED'
            )

        LIMIT 1
    """, (
        schedule_id,
        lesson_date
    )).fetchone()

    conn.close()

    return (
        row is not None
    )

def is_date_fully_closed(
    date_value
):

    if isinstance(date_value, date):
        date_value = date_value.isoformat()

    conn = connect()

    row = conn.execute("""
        SELECT id
        FROM schedule_exceptions

        WHERE
            date = ?
            AND exception_type = 'CLOSED'
            AND start_time IS NULL
            AND end_time IS NULL

        LIMIT 1
    """, (
        date_value,
    )).fetchone()

    conn.close()

    return row is not None


def is_interval_closed(
    start_time,
    end_time
):

    start_dt = datetime.fromisoformat(
        start_time
    )

    end_dt = datetime.fromisoformat(
        end_time
    )

    date_value = (
        start_dt.date()
        .isoformat()
    )

    conn = connect()

    rows = conn.execute("""
        SELECT *
        FROM schedule_exceptions

        WHERE
            date = ?
            AND exception_type = 'CLOSED'
    """, (
        date_value,
    )).fetchall()

    conn.close()

    for row in rows:

        # Весь день закрыт
        if (
            not row["start_time"]
            and not row["end_time"]
        ):
            return True

        if (
            not row["start_time"]
            or not row["end_time"]
        ):
            continue

        closed_start = datetime.combine(
            start_dt.date(),
            datetime.strptime(
                row["start_time"],
                "%H:%M"
            ).time(),
        )

        closed_end = datetime.combine(
            start_dt.date(),
            datetime.strptime(
                row["end_time"],
                "%H:%M"
            ).time(),
        )

        # Сохраняем timezone
        if start_dt.tzinfo:

            closed_start = (
                closed_start.replace(
                    tzinfo=start_dt.tzinfo
                )
            )

            closed_end = (
                closed_end.replace(
                    tzinfo=start_dt.tzinfo
                )
            )

        if (
            start_dt < closed_end
            and end_dt > closed_start
        ):
            return True

    return False

def generate_regular_lessons(
    schedule_id,
    until_date=None
):

    if str(get_setting("teacher_schedule_booking_paused","0") or "0").lower() in {"1","true","on","yes"}:
        return {
            "created": [],
            "created_count": 0,
            "skipped": [{"reason": "TEACHER_REGION_CHANGE_PAUSED"}],
            "skipped_count": 1,
            "paused": True,
        }

    schedule = get_regular_schedule(
        schedule_id
    )

    if schedule is None:

        raise ValueError(
            "Постоянное расписание не найдено."
        )

    if (
        schedule["status"]
        != "APPROVED"
    ):

        raise ValueError(
            "Расписание не активно."
        )

    user = get_user(
        schedule["user_id"]
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    schedule_dates = (
        get_regular_schedule_dates(
            schedule_id
        )
    )

    if until_date:

        if isinstance(
            until_date,
            str
        ):

            until_date_obj = (
                datetime.strptime(
                    until_date,
                    "%Y-%m-%d"
                ).date()
            )

        else:

            until_date_obj = (
                until_date
            )

        schedule_dates = [
            item
            for item in schedule_dates
            if item <= until_date_obj
        ]

    rate = get_student_rate(
        user["id"],
        schedule["study_goal"],
        schedule["subject"]
    )

    price = (
        calculate_lesson_price(
            rate,
            schedule[
                "duration_minutes"
            ]
        )
    )

    created = []
    skipped = []

    start_clock = (
        datetime.strptime(
            schedule["start_time"],
            "%H:%M"
        ).time()
    )

    for lesson_day in schedule_dates:

        if regular_lesson_exists(
            schedule_id,
            lesson_day.isoformat()
        ):

            continue

        start_dt = datetime.combine(
            lesson_day,
            start_clock
        )

        end_dt = (
            start_dt
            + timedelta(
                minutes=int(
                    schedule[
                        "duration_minutes"
                    ]
                )
            )
        )

        # Конкретная дата/время закрыты преподавателем
        if is_interval_closed(
            start_dt.isoformat(),
            end_dt.isoformat()
        ):

            skipped.append({
                "date":
                    lesson_day.isoformat(),

                "reason":
                    "ADMIN_DAY_OFF",
            })

            continue

        if is_slot_reserved(
            start_dt.isoformat(),
            end_dt.isoformat()
        ):

            skipped.append({
                "date":
                    lesson_day.isoformat(),

                "reason":
                    "SLOT_BUSY",
            })

            continue

        try:

            lesson_id = (
                create_admin_lesson(

                    user_id=(
                        user["id"]
                    ),

                    study_goal=(
                        schedule[
                            "study_goal"
                        ]
                    ),

                    subject=(
                        schedule[
                            "subject"
                        ]
                    ),

                    start_time=(
                        start_dt.isoformat()
                    ),

                    end_time=(
                        end_dt.isoformat()
                    ),

                    duration_minutes=(
                        schedule[
                            "duration_minutes"
                        ]
                    ),

                    hourly_rate=rate,

                    price=price,

                    payment_mode=(
                        "BALANCE"
                        if __import__("core.minute_balance", fromlist=["get_balance"])
                        .get_balance(
                            user["id"],
                            hourly_rate=int(rate)
                        )["total"] >= int(schedule["duration_minutes"])
                        else "AWAITING_PAYMENT"
                    ),

                    force=False,

                    regular_schedule_id=(
                        schedule_id
                    )
                )
            )

            created.append(
                lesson_id
            )

        except Exception as error:

            skipped.append({
                "date":
                    lesson_day.isoformat(),

                "reason":
                    str(error),
            })

    conn = connect()

    conn.execute("""
        UPDATE regular_schedules

        SET
            created_lessons_count =
                (
                    SELECT COUNT(*)
                    FROM lessons

                    WHERE
                        regular_schedule_id = ?
                        AND lesson_status
                            != 'REJECTED'
                ),

            updated_at = ?

        WHERE id = ?
    """, (
        schedule_id,
        now_iso(),
        schedule_id
    ))

    conn.commit()
    conn.close()

    return {
        "created":
            created,

        "created_count":
            len(created),

        "skipped":
            skipped,

        "skipped_count":
            len(skipped),
    }


# ============================================================
# CHARGE RESERVED REGULAR LESSON
# ============================================================

def charge_reserved_lesson(
    lesson_id
):

    lesson = get_lesson(lesson_id)
    if lesson is None:
        raise ValueError("Занятие не найдено.")

    # Minute model reserves the full planned duration, not one abstract lesson.
    if int(lesson["reserved_minutes"] or 0) > 0 and lesson["charged"]:
        return lesson["package_id"]

    if lesson["payment_status"] not in {"RESERVED_BALANCE", "AWAITING_PAYMENT"}:
        raise ValueError("Занятие не ожидает списания.")

    from core import minute_balance
    minute_balance.reserve_minutes(
        lesson["user_id"],
        int(lesson["hourly_rate"] or 0),
        int(lesson["duration_minutes"] or 0),
        int(lesson_id),
    )
    updated = get_lesson(lesson_id)
    return updated["package_id"] if updated else None


# ============================================================
# MANUAL PAYMENT
# ============================================================

def confirm_manual_lesson_payment(
    lesson_id,
    amount=None
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "payment_status"
        ] != "AWAITING_PAYMENT"
    ):

        raise ValueError(
            "Занятие не ожидает оплату."
        )

    if amount is None:

        amount = (
            lesson["price"]
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    cursor.execute("""
        INSERT INTO payments (

            user_id,

            study_goal,
            subject,

            payment_type,

            lessons_count,

            price_per_lesson,

            subtotal,

            discount_percent,
            package_discount_amount,

            promo_discount_amount,

            total_amount,

            status,

            created_at,
            confirmed_at
        )

        VALUES (
            ?,
            ?, ?,
            'MANUAL_SINGLE',
            1,
            ?,
            ?,
            0,
            0,
            0,
            ?,
            'PAID',
            ?,
            ?
        )
    """, (
        lesson["user_id"],
        lesson["study_goal"],
        lesson["subject"],
        int(amount),
        int(amount),
        int(amount),
        now_iso(),
        now_iso()
    ))

    payment_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        INSERT INTO lesson_packages (

            payment_id,

            user_id,

            study_goal,
            subject,

            lessons_total,
            lessons_used,

            price_per_lesson,

            discount_percent,

            amount_paid,

            status,

            source_type,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            1,
            1,
            ?,
            0,
            ?,
            'USED',
            'PAID',
            ?
        )
    """, (
        payment_id,
        lesson["user_id"],
        lesson["study_goal"],
        lesson["subject"],
        int(amount),
        int(amount),
        now_iso()
    ))

    package_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        UPDATE lessons

        SET
            payment_status = 'PAID',

            payment_id = ?,

            package_id = ?,

            charged = 1,

            payment_deadline = NULL,

            updated_at = ?

        WHERE id = ?
    """, (
        payment_id,
        package_id,
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return (
        payment_id,
        package_id
    )


def charge_admin_lesson_from_balance(
    lesson_id
):

    return charge_reserved_lesson(
        lesson_id
    )


# ============================================================
# UNPAID AUTO CANCEL
# ============================================================

def get_unpaid_lessons_due(
    at_time=None
):

    if at_time is None:

        at_time = now_iso()

    conn = connect()

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            lesson_status = 'CONFIRMED'

            AND payment_status =
                'AWAITING_PAYMENT'

            AND payment_deadline
                IS NOT NULL

            AND payment_deadline <= ?
    """, (
        at_time,
    )).fetchall()

    conn.close()

    return rows


def auto_cancel_unpaid_lesson(
    lesson_id
):

    lesson = get_lesson(
        lesson_id
    )

    # Administrator may explicitly allow this lesson to proceed
    # while payment is still pending.
    if not lesson:
        return False

    try:
        if int(lesson["allow_unpaid"] or 0):
            return False
    except (KeyError, IndexError):
        pass

    if lesson is None:

        return False

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"

        or lesson[
            "payment_status"
        ] != "AWAITING_PAYMENT"
    ):

        return False

    # Final payment reconciliation before destructive cancellation.
    # A confirmed payment can credit balance shortly before the deadline
    # while this lesson still temporarily says AWAITING_PAYMENT.
    try:
        charge_reserved_lesson(lesson_id)
    except ValueError:
        # No sufficient compatible balance: continue with normal cancellation.
        pass
    else:
        # Compatible balance existed and the lesson was reserved successfully.
        return False

    # Re-read after reconciliation in case another worker changed the lesson.
    lesson = get_lesson(lesson_id)
    if (
        lesson is None
        or lesson["lesson_status"] != "CONFIRMED"
        or lesson["payment_status"] != "AWAITING_PAYMENT"
    ):
        return False

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',

            payment_status =
                'UNPAID_CANCELLED',

            auto_cancelled_for_nonpayment = 1,

            cancelled_at = ?,

            cancellation_reason =
                'NON_PAYMENT',

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return True


# ============================================================
# UPCOMING
# ============================================================

def get_upcoming_lessons(
    user_id=None
):

    conn = connect()

    sql = """
        SELECT *
        FROM lessons

        WHERE
            lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS'
            )

            AND start_time >= ?
    """

    params = [
        now_iso()
    ]

    if user_id is not None:

        sql += """
            AND user_id = ?
        """

        params.append(
            user_id
        )

    sql += """
        ORDER BY start_time
    """

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    return rows


def get_pending_requests():

    conn = connect()

    rows = conn.execute("""
        SELECT

            l.*,

            u.name,
            u.grade,
            u.telegram_username

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            l.lesson_status = 'PENDING'

        ORDER BY
            l.start_time
    """).fetchall()

    conn.close()

    return rows


# ============================================================
# PENDING RESCHEDULES
# ============================================================

def create_pending_reschedule(lesson_id, reason, remind_after_days=2):

    lesson = get_lesson(lesson_id)

    if lesson is None:
        raise ValueError("Занятие не найдено.")

    due_at = (
        datetime.now()
        + timedelta(days=int(remind_after_days))
    ).isoformat()

    conn = connect()

    existing = conn.execute("""
        SELECT id
        FROM pending_reschedules
        WHERE lesson_id = ?
    """, (lesson_id,)).fetchone()

    if existing is None:

        conn.execute("""
            INSERT INTO pending_reschedules (
                lesson_id, user_id, reason, status,
                created_at, reminder_due_at
            )
            VALUES (?, ?, ?, 'PENDING', ?, ?)
        """, (
            lesson_id,
            lesson["user_id"],
            reason,
            now_iso(),
            due_at,
        ))

    else:

        conn.execute("""
            UPDATE pending_reschedules
            SET
                reason = ?,
                status = 'PENDING',
                reminder_due_at = ?,
                reminded_at = NULL,
                completed_at = NULL,
                new_lesson_id = NULL
            WHERE lesson_id = ?
        """, (
            reason,
            due_at,
            lesson_id,
        ))

    conn.commit()
    conn.close()


def complete_pending_reschedule(lesson_id, new_lesson_id):

    conn = connect()

    conn.execute("""
        UPDATE pending_reschedules
        SET
            status = 'COMPLETED',
            completed_at = ?,
            new_lesson_id = ?
        WHERE lesson_id = ?
    """, (
        now_iso(),
        new_lesson_id,
        lesson_id,
    ))

    conn.commit()
    conn.close()


def get_due_reschedule_reminders():

    conn = connect()

    rows = conn.execute("""
        SELECT
            pr.*,
            l.start_time,
            l.subject,
            l.study_goal,
            u.name,
            u.telegram_id
        FROM pending_reschedules pr
        JOIN lessons l ON l.id = pr.lesson_id
        JOIN users u ON u.id = pr.user_id
        WHERE
            pr.status = 'PENDING'
            AND pr.reminder_due_at <= ?
            AND pr.reminded_at IS NULL
        ORDER BY pr.reminder_due_at
    """, (now_iso(),)).fetchall()

    conn.close()
    return rows


def mark_reschedule_reminded(lesson_id):

    conn = connect()

    conn.execute("""
        UPDATE pending_reschedules
        SET reminded_at = ?
        WHERE lesson_id = ?
    """, (
        now_iso(),
        lesson_id,
    ))

    conn.commit()
    conn.close()


def get_lessons_in_date_range(date_from, date_to):

    conn = connect()

    rows = conn.execute("""
        SELECT l.*, u.name, u.telegram_id
        FROM lessons l
        JOIN users u ON u.id = l.user_id
        WHERE
            DATE(l.start_time) BETWEEN ? AND ?
            AND l.lesson_status IN ('PENDING', 'CONFIRMED')
        ORDER BY l.start_time
    """, (
        date_from,
        date_to,
    )).fetchall()

    conn.close()
    return rows


def close_date_range(date_from, date_to, comment=None):

    start = date.fromisoformat(date_from)
    finish = date.fromisoformat(date_to)

    if finish < start:
        raise ValueError("Последняя дата раньше первой.")

    current = start

    while current <= finish:

        existing = get_schedule_exceptions(
            current.isoformat()
        )

        fully_closed = any(
            row["exception_type"] == "CLOSED"
            and not row["start_time"]
            and not row["end_time"]
            for row in existing
        )

        if not fully_closed:
            add_schedule_exception(
                current.isoformat(),
                "CLOSED",
                comment=comment,
            )

        current += timedelta(days=1)


def prepare_lesson_for_forced_reschedule(lesson_id, reason):

    lesson = get_lesson(lesson_id)

    if lesson is None:
        raise ValueError("Занятие не найдено.")

    if lesson["lesson_status"] not in {
        "PENDING", "CONFIRMED", "SICKNESS", "CANCELLED"
    }:
        raise ValueError("Это занятие нельзя поставить на перенос.")

    conn = connect()

    conn.execute("""
        UPDATE lessons
        SET
            lesson_status = 'CONFIRMED',
            attendance_status = NULL,
            cancellation_reason = ?,
            cancelled_at = NULL,
            updated_at = ?
        WHERE id = ?
    """, (
        reason,
        now_iso(),
        lesson_id,
    ))

    conn.commit()
    conn.close()

    create_pending_reschedule(
        lesson_id,
        reason,
        remind_after_days=2,
    )


# ============================================================
# FREE RESCHEDULE
# ============================================================

def free_reschedule_lesson(
    lesson_id,
    new_start_time,
    new_end_time
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
    ):

        raise ValueError(
            "Это занятие нельзя перенести."
        )

    teacher_day_off = False
    try:
        from web_backend import teacher_day_off_state
        teacher_day_off = teacher_day_off_state.is_marked(int(lesson_id))
    except Exception:
        teacher_day_off = False

    if (
        not teacher_day_off
        and get_hours_until_lesson(
            lesson
        ) < 2
    ):

        raise ValueError(
            "До занятия осталось меньше 2 часов."
        )

    if is_slot_reserved(
        new_start_time,
        new_end_time,
        exclude_lesson_id=lesson_id
    ):

        raise ValueError(
            "Новое время уже занято."
        )

    start_dt = (
        datetime.fromisoformat(
            new_start_time
        )
    )

    conn = connect()

    same_day = conn.execute("""
        SELECT id
        FROM lessons

        WHERE
            user_id = ?

            AND DATE(start_time) = ?

            AND id != ?

            AND lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS',
                'COMPLETED'
            )

        LIMIT 1
    """, (
        lesson["user_id"],
        start_dt.date().isoformat(),
        lesson_id
    )).fetchone()

    conn.close()

    if same_day:

        raise ValueError(
            "У ученика уже есть занятие в этот день."
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    cursor.execute("""
        INSERT INTO lessons (

            user_id,

            program_id,

            study_goal,
            subject,

            start_time,
            end_time,

            duration_minutes,

            hourly_rate,
            price,

            payment_status,

            payment_id,

            package_id,

            lesson_status,

            charged,

            reserved_minutes,
            reserved_paid_minutes,
            reserved_bonus_minutes,

            request_source,

            requested_at,
            approved_at,

            is_trial,
            is_regular,

            regular_schedule_id,

            rescheduled_from_lesson_id,

            created_at
        )

        VALUES (
            ?,
            ?,
            ?, ?,
            ?, ?,
            ?,
            ?, ?,
            ?,
            ?,
            ?,
            'CONFIRMED',
            ?,
            ?, ?, ?,
            'STUDENT_RESCHEDULE',
            ?,
            ?,
            ?, ?,
            ?,
            ?,
            ?
        )
    """, (
        lesson["user_id"],
        lesson["program_id"],
        lesson["study_goal"],
        lesson["subject"],
        new_start_time,
        new_end_time,
        lesson["duration_minutes"],
        lesson["hourly_rate"],
        lesson["price"],
        lesson["payment_status"],
        lesson["payment_id"],
        lesson["package_id"],
        lesson["charged"],
        lesson["reserved_minutes"],
        lesson["reserved_paid_minutes"],
        lesson["reserved_bonus_minutes"],
        now_iso(),
        now_iso(),
        lesson["is_trial"],
        lesson["is_regular"],
        lesson["regular_schedule_id"],
        lesson_id,
        now_iso()
    ))

    new_lesson_id = (
        cursor.lastrowid
    )

    # A free reschedule transfers the existing minute reservation instead of
    # refunding and reserving again. Move the charge rows to the replacement
    # lesson so any later cancellation refunds the exact same minutes once.
    minute_charge_table = cursor.execute("""
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name='lesson_minute_charges'
        LIMIT 1
    """).fetchone()
    if minute_charge_table is not None:
        cursor.execute("""
            UPDATE lesson_minute_charges
            SET lesson_id = ?
            WHERE lesson_id = ? AND refunded = 0
        """, (
            new_lesson_id,
            lesson_id,
        ))

    cursor.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',

            charged = 0,

            package_id = NULL,

            payment_status =
                'TRANSFERRED',

            reschedule_type =
                'FREE',

            rescheduled_at = ?,

            rescheduled_to_lesson_id = ?,

            cancelled_at = ?,

            cancellation_reason =
                'FREE_RESCHEDULE',

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        new_lesson_id,
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    complete_pending_reschedule(lesson_id, new_lesson_id)

    return new_lesson_id


# ============================================================
# LATE RESCHEDULE
# ============================================================

def mark_late_reschedule(
    lesson_id
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
    ):

        raise ValueError(
            "Нельзя выполнить перенос."
        )

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status =
                'LATE_CANCELLED',

            attendance_status =
                'LATE_CANCELLED',

            reschedule_type =
                'LATE',

            rescheduled_at = ?,

            finished_at = ?,

            cancellation_reason =
                'LATE_RESCHEDULE',

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return True


# ============================================================
# SICKNESS
# ============================================================

def get_month_sickness_count(
    user_id,
    year,
    month
):

    month_prefix = (
        f"{int(year):04d}-"
        f"{int(month):02d}"
    )

    conn = connect()

    count = conn.execute("""
        SELECT COUNT(*)
        FROM lessons

        WHERE
            user_id = ?

            AND lesson_status =
                'SICKNESS'

            AND SUBSTR(
                start_time,
                1,
                7
            ) = ?
    """, (
        user_id,
        month_prefix
    )).fetchone()[0]

    conn.close()

    return int(
        count
    )


def request_sickness(
    lesson_id,
    user_id,
    comment
):

    lesson = get_lesson(
        lesson_id
    )

    if (
        lesson is None

        or lesson[
            "user_id"
        ] != user_id
    ):

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
    ):

        raise ValueError(
            "Для этого занятия нельзя оформить больничный."
        )

    start_dt = (
        datetime.fromisoformat(
            lesson["start_time"]
        )
    )

    sickness_count = (
        get_month_sickness_count(
            user_id,
            start_dt.year,
            start_dt.month
        )
        + 1
    )

    hours_left = (
        get_hours_until_lesson(
            lesson
        )
    )

    automatic_refund = (
        hours_left >= 2
        and sickness_count <= 2
    )

    needs_admin = (
        not automatic_refund
    )

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status =
                'SICKNESS',

            attendance_status =
                'SICKNESS',

            sickness_comment = ?,

            sickness_requested_at = ?,

            sickness_number_in_month = ?,

            sickness_admin_decision = ?,

            finished_at = ?,

            homework_required = 0,

            updated_at = ?

        WHERE id = ?
    """, (
        comment,
        now_iso(),
        sickness_count,
        (
            'PENDING'
            if needs_admin
            else 'NO_CHARGE'
        ),
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    refunded = False

    if automatic_refund:

        if (
            lesson["charged"]

            and lesson[
                "package_id"
            ]
        ):

            refunded = (
                refund_lesson_balance(
                    lesson_id, lesson["package_id"]
                )
            )

            if refunded:

                conn = connect()

                conn.execute("""
                    UPDATE lessons

                    SET
                        charged = 0,

                        payment_status =
                            'REFUNDED',

                        package_id = NULL,

                        updated_at = ?

                    WHERE id = ?
                """, (
                    now_iso(),
                    lesson_id
                ))

                conn.commit()
                conn.close()

    return {
        "sickness_number":
            sickness_count,

        "hours_left":
            hours_left,

        "needs_admin_decision":
            needs_admin,

        "refunded":
            refunded,
    }


def resolve_sickness(
    lesson_id,
    charge
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "lesson_status"
        ] != "SICKNESS"
    ):

        raise ValueError(
            "Это не больничный."
        )

    if charge:

        conn = connect()

        conn.execute("""
            UPDATE lessons

            SET
                sickness_admin_decision =
                    'CHARGE',

                updated_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            lesson_id
        ))

        conn.commit()
        conn.close()

        return {
            "charged":
                bool(
                    lesson["charged"]
                ),

            "refunded":
                False,
        }

    refunded = False

    if (
        lesson["charged"]

        and lesson[
            "package_id"
        ]
    ):

        refunded = (
            refund_lesson_balance(
                lesson_id, lesson["package_id"]
            )
        )

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            sickness_admin_decision =
                'NO_CHARGE',

            charged = 0,

            payment_status =
                'REFUNDED',

            package_id = NULL,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return {
        "charged":
            False,

        "refunded":
            refunded,
    }


# ============================================================
# STUDENT BOARD / LESSON LINKS
# ============================================================

def set_student_board_url(
    user_id,
    board_url
):

    board_url = (
        str(board_url).strip()
        if board_url
        else None
    )

    conn = connect()

    result = conn.execute("""
        UPDATE users

        SET
            board_url = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        board_url,
        now_iso(),
        user_id,
    ))

    if result.rowcount == 0:

        conn.close()

        raise ValueError(
            "Ученик не найден."
        )

    conn.commit()
    conn.close()

    return board_url


def get_student_board_url(
    user_id
):

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    return user[
        "board_url"
    ]


def save_lesson_meeting_url(
    lesson_id,
    meeting_url,
    sent_at=None
):

    if sent_at is None:

        sent_at = now_iso()

    conn = connect()

    result = conn.execute("""
        UPDATE lessons

        SET
            meeting_url = ?,
            meeting_link_sent_at = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        str(meeting_url).strip(),
        sent_at,
        now_iso(),
        lesson_id,
    ))

    if result.rowcount == 0:

        conn.close()

        raise ValueError(
            "Занятие не найдено."
        )

    conn.commit()
    conn.close()

    return sent_at


# ============================================================
# ACTIVE LESSON
# ============================================================

def get_active_lesson(
    exclude_lesson_id=None
):

    conn = connect()

    sql = """
        SELECT
            l.*,
            u.name

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            l.lesson_status = 'IN_PROGRESS'
    """

    params = []

    if exclude_lesson_id is not None:

        sql += """
            AND l.id != ?
        """

        params.append(
            exclude_lesson_id
        )

    sql += """
        ORDER BY l.started_at
        LIMIT 1
    """

    row = conn.execute(
        sql,
        tuple(params)
    ).fetchone()

    conn.close()

    return row


# ============================================================
# START LESSON
# ============================================================

def start_lesson(
    lesson_id,
    started_at=None,
    force=False
):

    if started_at is None:

        started_at = now_iso()

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if (
        lesson[
            "lesson_status"
        ] != "CONFIRMED"
    ):

        raise ValueError(
            "Это занятие нельзя начать."
        )

    active_lesson = get_active_lesson(
        exclude_lesson_id=lesson_id
    )

    if (
        active_lesson is not None
        and not force
    ):

        raise ValueError(
            "Сейчас уже идёт другое занятие."
        )

    if (
        lesson[
            "payment_status"
        ] == "AWAITING_PAYMENT"
    ):

        raise ValueError(
            "Занятие ещё не оплачено."
        )

    if (
        lesson[
            "payment_status"
        ] == "RESERVED_BALANCE"

        and not lesson[
            "charged"
        ]
    ):

        charge_reserved_lesson(
            lesson_id
        )

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status =
                'IN_PROGRESS',

            started_at = ?,

            attendance_status =
                'PRESENT',

            updated_at = ?

        WHERE id = ?
    """, (
        started_at,
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return started_at


# ============================================================
# FINISH LESSON
# ============================================================

def finish_lesson(
    lesson_id,
    finished_at=None
):

    # FINISH FALLBACK START
    #
    # Manual "Finish lesson" is authoritative.
    # If an older flow failed to save started_at,
    # use the planned start instead of leaving the lesson CONFIRMED.
    before_finish = get_lesson(lesson_id)

    if (
        before_finish is not None
        and str(
            before_finish["lesson_status"]
            or ""
        ).upper() == "CONFIRMED"
        and not before_finish["started_at"]
    ):
        start_lesson(
            lesson_id,
            started_at=before_finish["start_time"],
        )
    # FINISH FALLBACK END


    if finished_at is None:

        finished_at = now_iso()

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    lesson = cursor.execute("""
        SELECT *
        FROM lessons
        WHERE id = ?
    """, (
        lesson_id,
    )).fetchone()

    if lesson is None:

        conn.rollback()
        conn.close()

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson["lesson_status"] == "COMPLETED" and lesson["finished_at"]:
        paid_minutes = int(lesson["duration_minutes"] or 0)
        actual_minutes = int(lesson["actual_duration_minutes"] or 0)
        extra_minutes = int(lesson["extra_minutes"] or 0)
        underworked_minutes = int(lesson["underworked_minutes"] or 0)
        program_id = lesson["program_id"]
        if program_id is None:
            program = cursor.execute("""
                SELECT * FROM student_programs
                WHERE user_id=? AND study_goal=? AND subject=? AND active=1
                ORDER BY is_primary DESC, id LIMIT 1
            """, (lesson["user_id"], lesson["study_goal"], lesson["subject"])).fetchone()
            if program is not None:
                program_id = program["id"]
        pending_bonus = bool(underworked_minutes > 0 and not lesson["bonus_minutes_processed"])
        conn.rollback()
        conn.close()

        bonus_minutes_awarded = 0
        if pending_bonus:
            try:
                from core import minute_balance
                minute_balance.add_bonus_minutes(
                    lesson["user_id"], program_id, underworked_minutes,
                    reason="UNDERWORKED_TIME_CREDIT", lesson_id=lesson_id
                )
                conn = connect()
                conn.execute(
                    "UPDATE lessons SET bonus_minutes_processed=1,updated_at=? WHERE id=? AND bonus_minutes_processed=0",
                    (now_iso(), lesson_id),
                )
                conn.commit()
                conn.close()
                bonus_minutes_awarded = underworked_minutes
            except Exception as error:
                print("BONUS MINUTES CREDIT RETRY ERROR:", error)

        return {
            "lesson_id": lesson_id,
            "scheduled_minutes": paid_minutes,
            "actual_minutes": actual_minutes,
            "extra_minutes": extra_minutes,
            "underworked_minutes": underworked_minutes,
            "bonus_lessons_awarded": 0,
            "bonus_minutes_awarded": bonus_minutes_awarded,
            "underworked_minutes_balance": bonus_minutes_awarded,
            "already_finished": True,
        }

    if lesson["lesson_status"] != "IN_PROGRESS":

        conn.rollback()
        conn.close()

        raise ValueError(
            "Сначала нужно начать занятие."
        )

    if not lesson["started_at"]:

        conn.rollback()
        conn.close()

        raise ValueError(
            "Фактическое начало занятия не сохранено."
        )

    start_dt = datetime.fromisoformat(
        lesson["started_at"]
    )

    finish_dt = datetime.fromisoformat(
        finished_at
    )

    actual_minutes = max(
        round(
            (
                finish_dt
                - start_dt
            ).total_seconds()
            / 60
        ),
        0
    )

    paid_minutes = int(
        lesson["duration_minutes"] or 0
    )

    # Статистика переработки остаётся отдельной:
    # если работали дольше — это видно в actual/extra,
    # но само по себе бонус не создаёт.
    extra_minutes = max(
        actual_minutes - paid_minutes,
        0
    )

    # Недоработка — то, что преподаватель должен ученику.
    underworked_minutes = max(
        paid_minutes - actual_minutes,
        0
    )

    cursor.execute("""
        UPDATE lessons

        SET
            lesson_status = 'COMPLETED',
            attendance_status = 'PRESENT',
            finished_at = ?,
            actual_duration_minutes = ?,
            extra_minutes = ?,
            underworked_minutes = ?,
            homework_required = 1,
            updated_at = ?

        WHERE id = ?
    """, (
        finished_at,
        actual_minutes,
        extra_minutes,
        underworked_minutes,
        now_iso(),
        lesson_id,
    ))

    # Только фактически завершённое пробное скрывает кнопку из меню ученика.
    if lesson["is_trial"]:
        cursor.execute("""
            UPDATE users SET trial_used = 1, updated_at = ? WHERE id = ?
        """, (now_iso(), lesson["user_id"]))

    bonus_lessons = 0
    balance_after = 0
    bonus_minutes_awarded = 0
    program_id = lesson["program_id"]

    if program_id is None:
        program = cursor.execute("""
            SELECT * FROM student_programs
            WHERE user_id=? AND study_goal=? AND subject=? AND active=1
            ORDER BY is_primary DESC, id LIMIT 1
        """, (lesson["user_id"], lesson["study_goal"], lesson["subject"])).fetchone()
        if program is not None:
            program_id = program["id"]

    should_credit_bonus = bool(underworked_minutes > 0 and not lesson["bonus_minutes_processed"])
    if not lesson["bonus_minutes_processed"]:
        cursor.execute("""
            INSERT INTO lesson_time_adjustments(
                user_id,lesson_id,difference_minutes,bonus_lessons_added,balance_after,created_at
            ) VALUES(?,?,?,?,?,?)
        """, (lesson["user_id"],lesson_id,underworked_minutes,0,0,now_iso()))

    conn.commit()
    conn.close()

    # Credit missing minutes before marking the lesson processed.  The credit itself
    # is keyed by lesson_id, so a retry after a partial failure cannot double-credit.
    if should_credit_bonus:
        try:
            from core import minute_balance
            minute_balance.add_bonus_minutes(
                lesson["user_id"], program_id, underworked_minutes,
                reason="UNDERWORKED_TIME_CREDIT", lesson_id=lesson_id
            )
            conn = connect()
            conn.execute("UPDATE lessons SET bonus_minutes_processed=1,updated_at=? WHERE id=?", (now_iso(),lesson_id))
            conn.commit()
            conn.close()
            balance_after = underworked_minutes
            bonus_minutes_awarded = underworked_minutes
        except Exception as error:
            print("BONUS MINUTES CREDIT ERROR:", error)

    return {
        "lesson_id":
            lesson_id,

        "scheduled_minutes":
            paid_minutes,

        "actual_minutes":
            actual_minutes,

        "extra_minutes":
            extra_minutes,

        "underworked_minutes":
            underworked_minutes,

        "bonus_lessons_awarded":
            bonus_lessons,

        "bonus_minutes_awarded":
            bonus_minutes_awarded,

        "underworked_minutes_balance":
            balance_after,
    }


# ============================================================
# NO SHOW
# ============================================================

def mark_no_show(
    lesson_id
):

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status =
                'NO_SHOW',

            attendance_status =
                'NO_SHOW',

            actual_duration_minutes =
                0,

            finished_at = ?,

            homework_required = 0,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


# ============================================================
# LESSON NOTES FROM STUDENT
# ============================================================

def add_lesson_note(
    lesson_id,
    user_id,
    text=None,
    photo_file_id=None,
    photo_file_unique_id=None
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson["user_id"] != user_id:

        raise ValueError(
            "Это занятие принадлежит другому ученику."
        )

    if lesson["lesson_status"] not in {
        "PENDING",
        "CONFIRMED",
    }:

        raise ValueError(
            "Комментарий можно оставить только "
            "к предстоящему занятию."
        )

    clean_text = (
        str(text).strip()
        if text
        else None
    )

    if (
        not clean_text
        and not photo_file_id
    ):

        raise ValueError(
            "Добавьте текст или фотографию."
        )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO lesson_notes (

            lesson_id,
            user_id,

            text,

            photo_file_id,
            photo_file_unique_id,

            created_at
        )

        VALUES (
            ?, ?,
            ?,
            ?, ?,
            ?
        )
    """, (
        lesson_id,
        user_id,
        clean_text,
        photo_file_id,
        photo_file_unique_id,
        now_iso(),
    ))

    note_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return note_id


def get_lesson_notes(
    lesson_id
):

    conn = connect()

    rows = conn.execute("""
        SELECT
            ln.*,
            u.name

        FROM lesson_notes ln

        JOIN users u
            ON u.id = ln.user_id

        WHERE ln.lesson_id = ?

        ORDER BY
            ln.created_at,
            ln.id
    """, (
        lesson_id,
    )).fetchall()

    conn.close()

    return rows


def count_lesson_notes(
    lesson_id
):

    conn = connect()

    value = conn.execute("""
        SELECT COUNT(*)
        FROM lesson_notes
        WHERE lesson_id = ?
    """, (
        lesson_id,
    )).fetchone()[0]

    conn.close()

    return int(
        value or 0
    )


# ============================================================
# HOMEWORK
# ============================================================

def create_homework(
    user_id,
    study_goal,
    subject,
    description,
    title=None,
    lesson_id=None,
    source_reference=None,
    source_url=None,
    deadline=None,
    program_id=None,
    homework_type="MAIN"
):

    conn = connect()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO homework (

            user_id,
            lesson_id,
            program_id,

            study_goal,
            subject,

            homework_type,

            title,
            description,

            source_reference,
            source_url,

            deadline,

            status,

            assigned_at,

            created_at
        )

        VALUES (
            ?, ?, ?,
            ?, ?,
            ?,
            ?, ?,
            ?, ?,
            ?,
            'ASSIGNED',
            ?,
            ?
        )
    """, (
        user_id,
        lesson_id,
        program_id,
        study_goal,
        subject,
        homework_type,
        title,
        description,
        source_reference,
        source_url,
        deadline,
        now_iso(),
        now_iso()
    ))

    homework_id = (
        cursor.lastrowid
    )

    if lesson_id:

        cursor.execute("""
            UPDATE lessons

            SET
                homework_assigned = 1,

                homework_skipped = 0,

                homework_required = 1,

                updated_at = ?

            WHERE id = ?
        """, (
            now_iso(),
            lesson_id
        ))

    conn.commit()
    conn.close()

    return homework_id


def skip_homework_for_lesson(
    lesson_id
):

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            homework_required = 0,

            homework_assigned = 0,

            homework_skipped = 1,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


def lesson_needs_homework_reminder(
    lesson_id
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        return False

    return (
        lesson[
            "lesson_status"
        ] == "COMPLETED"

        and bool(
            lesson[
                "homework_required"
            ]
        )

        and not bool(
            lesson[
                "homework_assigned"
            ]
        )

        and not bool(
            lesson[
                "homework_skipped"
            ]
        )

        and not bool(
            lesson[
                "homework_reminder_sent"
            ]
        )
    )


def mark_homework_reminder_sent(
    lesson_id
):

    conn = connect()

    conn.execute("""
        UPDATE lessons

        SET
            homework_reminder_sent = 1,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()


def get_homework(
    homework_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM homework

        WHERE id = ?
    """, (
        homework_id,
    )).fetchone()

    conn.close()

    return row


def get_student_homework(
    user_id,
    active_only=False
):

    conn = connect()

    if active_only:

        rows = conn.execute("""
            SELECT *
            FROM homework

            WHERE
                user_id = ?

                AND status IN (
                    'ASSIGNED',
                    'UNDER_REVIEW',
                    'REVISION'
                )

            ORDER BY
                assigned_at DESC
        """, (
            user_id,
        )).fetchall()

    else:

        rows = conn.execute("""
            SELECT *
            FROM homework

            WHERE user_id = ?

            ORDER BY
                assigned_at DESC
        """, (
            user_id,
        )).fetchall()

    conn.close()

    return rows


def submit_homework(
    homework_id,
    user_id,
    submitted_from="TELEGRAM",
    student_comment=None
):

    homework = get_homework(
        homework_id
    )

    if homework is None:

        raise ValueError(
            "Домашнее задание не найдено."
        )

    if (
        homework["user_id"]
        != user_id
    ):

        raise PermissionError(
            "Это задание другого ученика."
        )

    conn = connect()
    cursor = conn.cursor()

    attempts = cursor.execute("""
        SELECT COUNT(*)
        FROM homework_submissions

        WHERE homework_id = ?
    """, (
        homework_id,
    )).fetchone()[0]

    attempt_number = (
        int(attempts)
        + 1
    )

    cursor.execute("""
        INSERT INTO homework_submissions (

            homework_id,
            user_id,

            attempt_number,

            student_comment,

            status,

            submitted_from,

            submitted_at
        )

        VALUES (
            ?, ?,
            ?,
            ?,
            'SUBMITTED',
            ?,
            ?
        )
    """, (
        homework_id,
        user_id,
        attempt_number,
        student_comment,
        submitted_from,
        now_iso()
    ))

    submission_id = (
        cursor.lastrowid
    )

    cursor.execute("""
        UPDATE homework

        SET
            status =
                'UNDER_REVIEW',

            submitted_at = ?,

            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        homework_id
    ))

    conn.commit()
    conn.close()

    return submission_id


def review_homework(
    homework_id,
    result,
    tutor_comment=None
):

    conn = connect()
    cursor = conn.cursor()

    submission = cursor.execute("""
        SELECT *
        FROM homework_submissions

        WHERE homework_id = ?

        ORDER BY
            attempt_number DESC

        LIMIT 1
    """, (
        homework_id,
    )).fetchone()

    submission_id = (
        submission["id"]
        if submission
        else None
    )

    cursor.execute("""
        INSERT INTO homework_reviews (

            homework_id,

            submission_id,

            result,

            tutor_comment,

            reviewed_at
        )

        VALUES (
            ?,
            ?,
            ?,
            ?,
            ?
        )
    """, (
        homework_id,
        submission_id,
        result,
        tutor_comment,
        now_iso()
    ))

    new_status = (
        "REVISION"
        if result == "REVISION"
        else "REVIEWED"
    )

    cursor.execute("""
        UPDATE homework

        SET
            status = ?,

            reviewed_at = ?,

            updated_at = ?

        WHERE id = ?
    """, (
        new_status,
        now_iso(),
        now_iso(),
        homework_id
    ))

    conn.commit()
    conn.close()



def set_lesson_tutor_delay(lesson_id, minutes):
    """Store the tutor's current estimated delay for an upcoming lesson."""
    minutes = max(0, int(minutes))
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE lessons
        SET tutor_delay_minutes = ?,
            tutor_delay_notified_at = ?,
            updated_at = ?
        WHERE id = ?
    """, (minutes, now_iso(), now_iso(), lesson_id))
    conn.commit()
    changed = cur.rowcount > 0
    conn.close()
    return changed

# ============================================================
# REMINDERS
# ============================================================

def reminder_was_sent(
    lesson_id,
    reminder_type
):

    conn = connect()

    row = conn.execute("""
        SELECT sent
        FROM lesson_reminders

        WHERE
            lesson_id = ?
            AND reminder_type = ?
    """, (
        lesson_id,
        reminder_type
    )).fetchone()

    conn.close()

    return bool(
        row
        and row["sent"]
    )


def mark_reminder_sent(
    lesson_id,
    reminder_type
):

    conn = connect()

    conn.execute("""
        INSERT INTO lesson_reminders (

            lesson_id,

            reminder_type,

            sent,

            sent_at
        )

        VALUES (
            ?,
            ?,
            1,
            ?
        )

        ON CONFLICT(
            lesson_id,
            reminder_type
        )

        DO UPDATE SET

            sent = 1,

            sent_at =
                excluded.sent_at
    """, (
        lesson_id,
        reminder_type,
        now_iso()
    ))

    conn.commit()
    conn.close()

    # ============================================================
# ADMIN LESSON MANAGEMENT
# ============================================================

def get_upcoming_admin_lessons(
    limit=100
):

    conn = connect()

    rows = conn.execute("""
        SELECT

            l.*,

            u.name,
            u.grade,
            u.telegram_id,
            u.telegram_username

        FROM lessons l

        JOIN users u
            ON u.id = l.user_id

        WHERE
            l.start_time >= ?

            AND l.lesson_status IN (
                'PENDING',
                'CONFIRMED',
                'IN_PROGRESS'
            )

        ORDER BY
            l.start_time

        LIMIT ?
    """, (
        now_iso(),
        int(limit)
    )).fetchall()

    conn.close()

    return rows



def cancel_lesson_by_student(lesson_id, user_id, late=False, reason="STUDENT_CANCEL"):
    """Cancel a student's confirmed lesson with ownership validation.

    Normal cancellation refunds a charged package lesson. Late cancellation keeps
    the charge and is marked LATE_CANCELLED for statistics.
    """
    lesson = get_lesson(lesson_id)
    if lesson is None or int(lesson["user_id"]) != int(user_id):
        raise ValueError("Занятие не найдено.")
    if lesson["lesson_status"] != "CONFIRMED":
        raise ValueError("Это занятие уже нельзя отменить.")

    cancel_lesson_by_admin(
        lesson_id,
        reason=reason,
        refund=not late,
        comment=None,
    )

    if late:
        conn = connect()
        conn.execute("""
            UPDATE lessons
            SET lesson_status = 'LATE_CANCELLED',
                attendance_status = 'LATE_CANCELLED',
                cancellation_reason = ?,
                updated_at = ?
            WHERE id = ?
        """, (reason, now_iso(), lesson_id))
        conn.commit()
        conn.close()

    return get_lesson(lesson_id)

def cancel_lesson_by_admin(
    lesson_id,
    reason="ADMIN_CANCEL",
    refund=True,
    comment=None
):

    lesson = get_lesson(
        lesson_id
    )

    if lesson is None:

        raise ValueError(
            "Занятие не найдено."
        )

    if lesson[
        "lesson_status"
    ] in {
        "COMPLETED",
        "CANCELLED",
        "REJECTED",
        "NO_SHOW",
        "LATE_CANCELLED",
        "SICKNESS",
    }:

        raise ValueError(
            "Это занятие уже нельзя отменить."
        )

    refunded = False

    # Если занятие было реально списано
    if (
        refund
        and lesson["charged"]
        and lesson["package_id"]
    ):

        refunded = (
            refund_lesson_balance(
                lesson_id, lesson["package_id"]
            )
        )

    conn = connect()

    if refund:

        new_payment_status = (
            "FREE"
            if lesson[
                "payment_status"
            ] == "FREE"
            else "REFUNDED"
        )

        charged = 0
        package_id = None

    else:

        new_payment_status = (
            lesson[
                "payment_status"
            ]
        )

        charged = (
            lesson["charged"]
        )

        package_id = (
            lesson["package_id"]
        )

    conn.execute("""
        UPDATE lessons

        SET
            lesson_status = 'CANCELLED',

            attendance_status =
                'CANCELLED',

            payment_status = ?,

            charged = ?,

            package_id = ?,

            cancelled_at = ?,

            cancellation_reason = ?,

            tutor_comment =
                CASE

                    WHEN ? IS NULL
                    THEN tutor_comment

                    WHEN tutor_comment IS NULL
                    THEN ?

                    ELSE
                        tutor_comment
                        || CHAR(10)
                        || ?

                END,

            homework_required = 0,

            updated_at = ?

        WHERE id = ?
    """, (
        new_payment_status,
        charged,
        package_id,
        now_iso(),
        reason,

        comment,
        comment,
        comment,

        now_iso(),
        lesson_id
    ))

    conn.commit()
    conn.close()

    return {
        "cancelled":
            True,

        "refunded":
            refunded,

        "refund_requested":
            bool(refund),

        "was_charged":
            bool(
                lesson["charged"]
            ),

        "regular_schedule_id":
            lesson[
                "regular_schedule_id"
            ],
    }


def get_next_regular_lesson_after(
    regular_schedule_id,
    after_datetime=None
):

    if not regular_schedule_id:

        return None

    if after_datetime is None:

        after_datetime = now_iso()

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            regular_schedule_id = ?

            AND start_time > ?

            AND lesson_status IN (
                'CONFIRMED',
                'PENDING'
            )

        ORDER BY
            start_time

        LIMIT 1
    """, (
        regular_schedule_id,
        after_datetime
    )).fetchone()

    conn.close()

    return row


# ============================================================
# STUDENT PROGRAMS V4
# Несколько направлений у одного ученика
# ============================================================

PROGRAM_STATUS_NAMES = {
    "PENDING": "Ожидает подтверждения",
    "APPROVED": "Подтверждено",
    "REJECTED": "Отклонено",
    "DISABLED": "Отключено",
}


def _legacy_custom_rate_from_user(
    user,
    study_goal,
    subject
):

    try:
        column = get_rate_column(
            study_goal,
            subject
        )
    except Exception:
        return None

    if column not in user.keys():
        return None

    value = user[column]

    return (
        int(value)
        if value is not None
        else None
    )


def migrate_legacy_student_programs(
    conn=None
):

    own_connection = (
        conn is None
    )

    if own_connection:
        conn = connect()

    users = conn.execute("""
        SELECT *
        FROM users
    """).fetchall()

    for user in users:

        existing = conn.execute("""
            SELECT id
            FROM student_programs
            WHERE user_id = ?
            LIMIT 1
        """, (
            user["id"],
        )).fetchone()

        if existing is not None:
            continue

        study_goal = user[
            "study_goal"
        ]

        subject = user[
            "main_subject"
        ]

        custom_rate = (
            _legacy_custom_rate_from_user(
                user,
                study_goal,
                subject
            )
        )

        conn.execute("""
            INSERT OR IGNORE
            INTO student_programs (

                user_id,
                study_goal,
                subject,

                custom_hourly_rate,

                is_primary,
                active,
                approval_status,

                trial_used,

                created_by,
                created_at
            )

            VALUES (
                ?, ?, ?,
                ?,
                1, 1, 'APPROVED',
                ?,
                'MIGRATION',
                ?
            )
        """, (
            user["id"],
            study_goal,
            subject,
            custom_rate,
            int(
                user["trial_used"] or 0
            ),
            now_iso(),
        ))

    if own_connection:
        conn.commit()
        conn.close()


def backfill_program_links(
    conn=None
):

    own_connection = (
        conn is None
    )

    if own_connection:
        conn = connect()

    targets = [
        "lessons",
        "payments",
        "lesson_packages",
        "regular_schedules",
        "homework",
    ]

    for table_name in targets:

        if not table_exists(
            conn,
            table_name
        ):
            continue

        columns = table_columns(
            conn,
            table_name
        )

        if not {
            "program_id",
            "user_id",
            "study_goal",
            "subject",
        }.issubset(
            columns
        ):
            continue

        conn.execute(
            f"""
            UPDATE {table_name}

            SET program_id = (
                SELECT sp.id
                FROM student_programs sp

                WHERE
                    sp.user_id =
                        {table_name}.user_id

                    AND sp.study_goal =
                        {table_name}.study_goal

                    AND sp.subject =
                        {table_name}.subject

                ORDER BY
                    sp.active DESC,
                    sp.is_primary DESC,
                    sp.id

                LIMIT 1
            )

            WHERE program_id IS NULL
            """
        )

    if own_connection:
        conn.commit()
        conn.close()


def ensure_student_programs_for_user(user_id, programs):

    created = []

    for index, item in enumerate(programs):

        existing = get_program_by_goal_subject(
            user_id,
            item["study_goal"],
            item["subject"],
            include_inactive=True,
        )

        if existing is not None:
            program_id = existing["id"]

            if not existing["active"]:
                conn = connect()
                conn.execute("""
                    UPDATE student_programs
                    SET active = 1,
                        approval_status = 'APPROVED',
                        updated_at = ?
                    WHERE id = ?
                """, (now_iso(), program_id))
                conn.commit()
                conn.close()
        else:
            program_id = create_student_program(
                user_id=user_id,
                study_goal=item["study_goal"],
                subject=item["subject"],
                is_primary=bool(item.get("is_primary", index == 0)),
                approval_status=item.get("approval_status", "APPROVED"),
                created_by=item.get("created_by", "REGISTRATION"),
            )

        created.append(program_id)

    return created


def get_student_program(
    program_id
):

    conn = connect()

    row = conn.execute("""
        SELECT
            sp.*,
            u.name,
            u.grade,
            u.telegram_id,
            u.telegram_username

        FROM student_programs sp

        JOIN users u
            ON u.id = sp.user_id

        WHERE sp.id = ?
    """, (
        program_id,
    )).fetchone()

    conn.close()

    return row


def get_student_programs(
    user_id,
    active_only=True,
    approved_only=False
):

    conn = connect()

    sql = """
        SELECT *
        FROM student_programs

        WHERE user_id = ?
    """

    params = [
        user_id
    ]

    if active_only:

        sql += """
            AND active = 1
        """

    if approved_only:

        sql += """
            AND approval_status =
                'APPROVED'
        """

    sql += """
        ORDER BY
            is_primary DESC,
            subject,
            study_goal,
            id
    """

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    return rows


def get_primary_student_program(
    user_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM student_programs

        WHERE
            user_id = ?
            AND active = 1

        ORDER BY
            is_primary DESC,
            id

        LIMIT 1
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return row


def get_program_by_goal_subject(
    user_id,
    study_goal,
    subject,
    include_inactive=False
):

    conn = connect()

    sql = """
        SELECT *
        FROM student_programs

        WHERE
            user_id = ?
            AND study_goal = ?
            AND subject = ?
    """

    params = [
        user_id,
        study_goal,
        subject,
    ]

    if not include_inactive:

        sql += """
            AND active = 1
        """

    sql += """
        ORDER BY
            is_primary DESC,
            id
        LIMIT 1
    """

    row = conn.execute(
        sql,
        tuple(params)
    ).fetchone()

    conn.close()

    return row


def create_student_program(
    user_id,
    study_goal,
    subject,
    custom_hourly_rate=None,
    is_primary=False,
    approval_status="APPROVED",
    created_by="ADMIN"
):

    if approval_status not in {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }:

        raise ValueError(
            "Неверный статус направления."
        )

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    conn = connect()
    cursor = conn.cursor()

    existing = cursor.execute("""
        SELECT *
        FROM student_programs

        WHERE
            user_id = ?
            AND study_goal = ?
            AND subject = ?

        LIMIT 1
    """, (
        user_id,
        study_goal,
        subject,
    )).fetchone()

    if existing is not None:

        if existing["active"]:

            conn.close()

            raise ValueError(
                "Это направление уже добавлено ученику."
            )

        cursor.execute("""
            UPDATE student_programs

            SET
                active = 1,
                approval_status = ?,
                custom_hourly_rate =
                    COALESCE(
                        ?,
                        custom_hourly_rate
                    ),
                updated_at = ?

            WHERE id = ?
        """, (
            approval_status,
            custom_hourly_rate,
            now_iso(),
            existing["id"],
        ))

        program_id = existing["id"]

    else:

        if is_primary:

            cursor.execute("""
                UPDATE student_programs

                SET
                    is_primary = 0,
                    updated_at = ?

                WHERE user_id = ?
            """, (
                now_iso(),
                user_id,
            ))

        cursor.execute("""
            INSERT INTO student_programs (

                user_id,
                study_goal,
                subject,

                custom_hourly_rate,

                is_primary,
                active,
                approval_status,

                trial_used,

                created_by,
                created_at
            )

            VALUES (
                ?, ?, ?,
                ?,
                ?, 1, ?,
                0,
                ?,
                ?
            )
        """, (
            user_id,
            study_goal,
            subject,
            custom_hourly_rate,
            int(bool(is_primary)),
            approval_status,
            created_by,
            now_iso(),
        ))

        program_id = (
            cursor.lastrowid
        )

    count = cursor.execute("""
        SELECT COUNT(*)
        FROM student_programs

        WHERE
            user_id = ?
            AND active = 1
    """, (
        user_id,
    )).fetchone()[0]

    if count == 1:

        cursor.execute("""
            UPDATE student_programs

            SET is_primary = 1

            WHERE id = ?
        """, (
            program_id,
        ))

    conn.commit()
    conn.close()

    return program_id


def request_student_program(
    user_id,
    study_goal,
    subject
):

    return create_student_program(
        user_id=user_id,
        study_goal=study_goal,
        subject=subject,
        approval_status="PENDING",
        created_by="STUDENT",
    )


def approve_student_program(
    program_id
):

    conn = connect()

    row = conn.execute("""
        SELECT *
        FROM student_programs
        WHERE id = ?
    """, (
        program_id,
    )).fetchone()

    if row is None:

        conn.close()

        raise ValueError(
            "Направление не найдено."
        )

    conn.execute("""
        UPDATE student_programs

        SET
            approval_status = 'APPROVED',
            active = 1,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        program_id,
    ))

    conn.commit()
    conn.close()


def reject_student_program(
    program_id
):

    conn = connect()

    conn.execute("""
        UPDATE student_programs

        SET
            approval_status = 'REJECTED',
            active = 0,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        program_id,
    ))

    conn.commit()
    conn.close()


def set_primary_student_program(
    user_id,
    program_id
):

    program = get_student_program(
        program_id
    )

    if (
        program is None
        or program["user_id"] != user_id
    ):

        raise ValueError(
            "Направление не найдено."
        )

    conn = connect()

    conn.execute("""
        UPDATE student_programs

        SET
            is_primary = 0,
            updated_at = ?

        WHERE user_id = ?
    """, (
        now_iso(),
        user_id,
    ))

    conn.execute("""
        UPDATE student_programs

        SET
            is_primary = 1,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        program_id,
    ))

    # Сохраняем совместимость со старым кодом.
    conn.execute("""
        UPDATE users

        SET
            study_goal = ?,
            main_subject = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        program["study_goal"],
        program["subject"],
        now_iso(),
        user_id,
    ))

    conn.commit()
    conn.close()


def disable_student_program(
    program_id
):

    program = get_student_program(
        program_id
    )

    if program is None:

        raise ValueError(
            "Направление не найдено."
        )

    conn = connect()

    active_count = conn.execute("""
        SELECT COUNT(*)
        FROM student_programs

        WHERE
            user_id = ?
            AND active = 1
    """, (
        program["user_id"],
    )).fetchone()[0]

    if active_count <= 1:

        conn.close()

        raise ValueError(
            "Нельзя удалить единственное активное направление ученика."
        )

    conn.execute("""
        UPDATE student_programs

        SET
            active = 0,
            approval_status = 'DISABLED',
            is_primary = 0,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        program_id,
    ))

    conn.commit()
    conn.close()

    primary = get_primary_student_program(
        program["user_id"]
    )

    if primary is not None:

        set_primary_student_program(
            program["user_id"],
            primary["id"]
        )


def get_program_default_rate(
    program_id
):

    program = get_student_program(
        program_id
    )

    if program is None:

        raise ValueError(
            "Направление не найдено."
        )

    return get_default_rate(
        program["study_goal"],
        program["subject"],
        program["grade"],
    )


def get_program_rate_info(
    program_id
):

    program = get_student_program(
        program_id
    )

    if program is None:

        raise ValueError(
            "Направление не найдено."
        )

    common_rate = get_default_rate(
        program["study_goal"],
        program["subject"],
        program["grade"],
    )

    custom_rate = (
        program[
            "custom_hourly_rate"
        ]
    )

    if custom_rate is not None:

        effective_rate = int(
            custom_rate
        )

        source = "CUSTOM"

    else:

        effective_rate = int(
            common_rate
        )

        source = "DEFAULT"

    return {
        "program_id":
            program_id,

        "effective_rate":
            effective_rate,

        "custom_rate":
            (
                int(custom_rate)
                if custom_rate is not None
                else None
            ),

        "common_rate":
            int(common_rate),

        "source":
            source,
    }


def set_program_custom_rate(
    program_id,
    hourly_rate
):
    program = get_student_program(program_id)
    if program is None:
        raise ValueError("Направление не найдено.")

    set_custom_rate(
        int(program["user_id"]),
        program["study_goal"],
        program["subject"],
        int(hourly_rate),
    )

    return get_program_rate_info(program_id)


def clear_program_custom_rate(
    program_id
):
    program = get_student_program(program_id)
    if program is None:
        raise ValueError("Направление не найдено.")

    clear_custom_rate(
        int(program["user_id"]),
        program["study_goal"],
        program["subject"],
    )

    return get_program_rate_info(program_id)


def get_program_balance_breakdown(
    program_id
):

    program = get_student_program(
        program_id
    )

    if program is None:

        raise ValueError(
            "Направление не найдено."
        )

    return get_balance_breakdown(
        program["user_id"],
        program["study_goal"],
        program["subject"],
    )


# ============================================================
# ADMIN BALANCE ADJUSTMENTS
# ============================================================

def get_balance_by_nominal(user_id):
    conn = connect()
    rows = conn.execute("""
        SELECT
            price_per_lesson,
            source_type,
            SUM(lessons_total - lessons_used) AS remaining
        FROM lesson_packages
        WHERE user_id = ?
          AND status = 'ACTIVE'
          AND lessons_used < lessons_total
        GROUP BY price_per_lesson, source_type
        ORDER BY price_per_lesson
    """, (user_id,)).fetchall()
    conn.close()

    result = {}
    for row in rows:
        nominal = int(row["price_per_lesson"] or 0)
        item = result.setdefault(nominal, {"paid": 0, "bonus": 0, "total": 0})
        value = int(row["remaining"] or 0)
        if row["source_type"] == "BONUS":
            item["bonus"] += value
        else:
            item["paid"] += value
        item["total"] += value
    return result


def admin_add_balance_lesson(user_id, program_id):
    program = get_student_program(program_id)
    if program is None or int(program["user_id"]) != int(user_id):
        raise ValueError("Направление ученика не найдено.")

    rate = get_program_rate_info(program_id)["effective_rate"]
    duration = 90 if program["study_goal"] in {"OGE", "EGE", "OLYMPIAD"} else 60
    nominal = calculate_lesson_price(rate, duration)

    return add_bonus_lessons(
        user_id,
        1,
        program["study_goal"],
        program["subject"],
        reason="ADMIN_ADJUSTMENT",
        price_per_lesson=nominal,
    )


def admin_remove_balance_lesson(user_id, nominal):
    return use_prepaid_lesson(
        user_id,
        price_per_lesson=int(nominal),
    )


def get_admin_statistics(start_iso=None, end_iso=None):
    conn = connect()

    lesson_where = ["lesson_status = 'COMPLETED'"]
    lesson_params = []
    payment_where = ["status = 'PAID'"]
    payment_params = []

    if start_iso:
        lesson_where.append("start_time >= ?")
        lesson_params.append(start_iso)
        payment_where.append("COALESCE(confirmed_at, created_at) >= ?")
        payment_params.append(start_iso)
    if end_iso:
        lesson_where.append("start_time < ?")
        lesson_params.append(end_iso)
        payment_where.append("COALESCE(confirmed_at, created_at) < ?")
        payment_params.append(end_iso)

    lesson_sql = " AND ".join(lesson_where)
    payment_sql = " AND ".join(payment_where)

    row = conn.execute(f"""
        SELECT COUNT(*) AS completed,
               COALESCE(SUM(actual_duration_minutes), 0) AS actual_minutes,
               COALESCE(SUM(price), 0) AS lesson_value
        FROM lessons
        WHERE {lesson_sql}
    """, tuple(lesson_params)).fetchone()

    paid_amount = conn.execute(f"""
        SELECT COALESCE(SUM(total_amount), 0)
        FROM payments
        WHERE {payment_sql}
    """, tuple(payment_params)).fetchone()[0]

    active_users = conn.execute("SELECT COUNT(*) FROM users WHERE active = 1").fetchone()[0]
    conn.close()

    return {
        "active_users": int(active_users or 0),
        "completed": int(row["completed"] or 0),
        "actual_minutes": int(row["actual_minutes"] or 0),
        "lesson_value": int(row["lesson_value"] or 0),
        "paid_amount": int(paid_amount or 0),
    }


# ============================================================
# HOMEWORK SCORES
# ============================================================

def set_homework_score(
    homework_id,
    total_tasks,
    correct_tasks,
    tutor_comment=None,
    result="REVIEWED"
):

    total_tasks = int(
        total_tasks
    )

    correct_tasks = int(
        correct_tasks
    )

    if total_tasks <= 0:

        raise ValueError(
            "Общее количество заданий должно быть больше нуля."
        )

    if correct_tasks < 0:

        raise ValueError(
            "Количество правильных заданий не может быть отрицательным."
        )

    if correct_tasks > total_tasks:

        raise ValueError(
            "Правильных заданий не может быть больше общего количества."
        )

    homework = get_homework(
        homework_id
    )

    if homework is None:

        raise ValueError(
            "Домашнее задание не найдено."
        )

    conn = connect()
    cursor = conn.cursor()

    submission = cursor.execute("""
        SELECT *
        FROM homework_submissions

        WHERE homework_id = ?

        ORDER BY
            attempt_number DESC,
            id DESC

        LIMIT 1
    """, (
        homework_id,
    )).fetchone()

    submission_id = (
        submission["id"]
        if submission is not None
        else None
    )

    accuracy = round(
        correct_tasks
        * 100.0
        / total_tasks,
        2
    )

    cursor.execute("""
        INSERT INTO homework_reviews (

            homework_id,
            submission_id,

            result,
            tutor_comment,

            total_tasks,
            correct_tasks,
            accuracy_percent,

            reviewed_at
        )

        VALUES (
            ?, ?,
            ?, ?,
            ?, ?, ?,
            ?
        )
    """, (
        homework_id,
        submission_id,
        result,
        tutor_comment,
        total_tasks,
        correct_tasks,
        accuracy,
        now_iso(),
    ))

    cursor.execute("""
        UPDATE homework

        SET
            status = 'REVIEWED',
            reviewed_at = ?,
            updated_at = ?

        WHERE id = ?
    """, (
        now_iso(),
        now_iso(),
        homework_id,
    ))

    conn.commit()
    conn.close()

    return {
        "total_tasks":
            total_tasks,

        "correct_tasks":
            correct_tasks,

        "accuracy_percent":
            accuracy,
    }


def get_homework_score_statistics(
    user_id,
    program_id=None,
    date_from=None,
    date_to=None
):

    conn = connect()

    sql = """
        SELECT
            hr.total_tasks,
            hr.correct_tasks,
            hr.accuracy_percent,
            hr.reviewed_at,
            h.program_id,
            h.study_goal,
            h.subject

        FROM homework_reviews hr

        JOIN homework h
            ON h.id = hr.homework_id

        WHERE
            h.user_id = ?
            AND hr.total_tasks IS NOT NULL
            AND hr.correct_tasks IS NOT NULL
    """

    params = [
        user_id
    ]

    if program_id is not None:

        sql += """
            AND h.program_id = ?
        """

        params.append(
            program_id
        )

    if date_from:

        sql += """
            AND DATE(hr.reviewed_at) >= ?
        """

        params.append(
            date_from
        )

    if date_to:

        sql += """
            AND DATE(hr.reviewed_at) <= ?
        """

        params.append(
            date_to
        )

    sql += """
        ORDER BY hr.reviewed_at
    """

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    total_homeworks = len(
        rows
    )

    total_tasks = sum(
        int(
            row["total_tasks"] or 0
        )
        for row in rows
    )

    correct_tasks = sum(
        int(
            row["correct_tasks"] or 0
        )
        for row in rows
    )

    accuracy = (
        round(
            correct_tasks
            * 100.0
            / total_tasks,
            2
        )
        if total_tasks > 0
        else None
    )

    trend = None

    # Динамику показываем только при достаточном количестве проверок.
    if total_homeworks >= 4:

        midpoint = (
            total_homeworks // 2
        )

        first = rows[:midpoint]
        second = rows[midpoint:]

        def weighted_accuracy(
            part
        ):

            part_total = sum(
                int(
                    row["total_tasks"] or 0
                )
                for row in part
            )

            part_correct = sum(
                int(
                    row["correct_tasks"] or 0
                )
                for row in part
            )

            if part_total <= 0:
                return None

            return (
                part_correct
                * 100.0
                / part_total
            )

        first_accuracy = (
            weighted_accuracy(
                first
            )
        )

        second_accuracy = (
            weighted_accuracy(
                second
            )
        )

        if (
            first_accuracy is not None
            and second_accuracy is not None
        ):

            difference = (
                second_accuracy
                - first_accuracy
            )

            if difference >= 5:

                trend = "IMPROVING"

            elif difference <= -5:

                trend = "DECLINING"

            else:

                trend = "STABLE"

    return {
        "checked_homeworks":
            total_homeworks,

        "total_tasks":
            total_tasks,

        "correct_tasks":
            correct_tasks,

        "accuracy_percent":
            accuracy,

        "trend":
            trend,

        "reviews": [
            dict(row)
            for row in rows
        ],
    }


# ============================================================
# MONTHLY REPORTS
# ============================================================

def _month_bounds(
    year,
    month
):

    year = int(
        year
    )

    month = int(
        month
    )

    start = date(
        year,
        month,
        1
    )

    if month == 12:

        next_month = date(
            year + 1,
            1,
            1
        )

    else:

        next_month = date(
            year,
            month + 1,
            1
        )

    end = (
        next_month
        - timedelta(days=1)
    )

    return (
        start.isoformat(),
        end.isoformat(),
    )


def _lesson_revenue(
    lesson
):

    if not lesson["charged"]:

        return 0.0

    if lesson["payment_status"] in {
        "FREE",
        "REFUNDED",
        "UNPAID",
        "UNPAID_CANCELLED",
    }:

        return 0.0

    package_id = (
        lesson["package_id"]
    )

    if package_id:

        conn = connect()

        package = conn.execute("""
            SELECT *
            FROM lesson_packages
            WHERE id = ?
        """, (
            package_id,
        )).fetchone()

        conn.close()

        if package is not None:

            if package["source_type"] == "BONUS":

                return 0.0

            lessons_total = int(
                package[
                    "lessons_total"
                ] or 0
            )

            amount_paid = float(
                package[
                    "amount_paid"
                ] or 0
            )

            if lessons_total > 0:

                return (
                    amount_paid
                    / lessons_total
                )

    return float(
        lesson["price"] or 0
    )


def get_program_monthly_statistics(
    program_id,
    year,
    month
):

    program = get_student_program(
        program_id
    )

    if program is None:

        raise ValueError(
            "Направление не найдено."
        )

    date_from, date_to = (
        _month_bounds(
            year,
            month
        )
    )

    conn = connect()

    rows = conn.execute("""
        SELECT *
        FROM lessons

        WHERE
            program_id = ?
            AND DATE(start_time)
                BETWEEN ? AND ?

        ORDER BY start_time
    """, (
        program_id,
        date_from,
        date_to,
    )).fetchall()

    conn.close()

    completed = 0
    cancelled = 0
    no_show = 0
    sickness = 0
    late_cancelled = 0

    paid_minutes = 0
    actual_minutes = 0
    extra_minutes = 0
    revenue = 0.0

    for lesson in rows:

        status = (
            lesson[
                "lesson_status"
            ]
        )

        if status == "COMPLETED":
            completed += 1

        elif status == "CANCELLED":
            cancelled += 1

        elif status == "NO_SHOW":
            no_show += 1

        elif status == "SICKNESS":
            sickness += 1

        elif status == "LATE_CANCELLED":
            late_cancelled += 1

        if lesson["charged"]:

            paid_minutes += int(
                lesson[
                    "duration_minutes"
                ] or 0
            )

        actual_minutes += int(
            lesson[
                "actual_duration_minutes"
            ] or 0
        )

        extra_minutes += int(
            lesson[
                "extra_minutes"
            ] or 0
        )

        revenue += (
            _lesson_revenue(
                lesson
            )
        )

    homework = (
        get_homework_score_statistics(
            program[
                "user_id"
            ],
            program_id=program_id,
            date_from=date_from,
            date_to=date_to,
        )
    )

    balance = (
        get_program_balance_breakdown(
            program_id
        )
    )

    return {
        "program_id":
            program_id,

        "user_id":
            program["user_id"],

        "study_goal":
            program["study_goal"],

        "subject":
            program["subject"],

        "year":
            int(year),

        "month":
            int(month),

        "revenue":
            round(
                revenue,
                2
            ),

        "completed_lessons":
            completed,

        "cancelled":
            cancelled,

        "no_show":
            no_show,

        "sickness":
            sickness,

        "late_cancelled":
            late_cancelled,

        "paid_minutes":
            paid_minutes,

        "actual_minutes":
            actual_minutes,

        "extra_minutes":
            extra_minutes,

        "balance":
            balance,

        "underworked_minutes_balance":
            int(
                program[
                    "underworked_minutes_balance"
                ] or 0
            ),

        "homework":
            homework,

        "lessons": [
            dict(row)
            for row in rows
        ],
    }


def get_student_monthly_report(
    user_id,
    year,
    month
):

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    programs = (
        get_student_programs(
            user_id,
            active_only=False,
            approved_only=False,
        )
    )

    program_reports = []

    for program in programs:

        report = (
            get_program_monthly_statistics(
                program["id"],
                year,
                month
            )
        )

        # Не захламляем отчёт полностью пустыми
        # отключёнными направлениями.
        if (
            report[
                "completed_lessons"
            ]
            or report[
                "cancelled"
            ]
            or report[
                "no_show"
            ]
            or report[
                "sickness"
            ]
            or report[
                "late_cancelled"
            ]
            or report[
                "paid_minutes"
            ]
            or report[
                "actual_minutes"
            ]
            or report[
                "homework"
            ][
                "checked_homeworks"
            ]
            or program["active"]
        ):

            program_reports.append(
                report
            )

    total = {
        "revenue": 0.0,
        "completed_lessons": 0,
        "cancelled": 0,
        "no_show": 0,
        "sickness": 0,
        "late_cancelled": 0,
        "paid_minutes": 0,
        "actual_minutes": 0,
        "extra_minutes": 0,
        "homework_checked": 0,
        "homework_total_tasks": 0,
        "homework_correct_tasks": 0,
    }

    for report in program_reports:

        total["revenue"] += (
            report["revenue"]
        )

        total["completed_lessons"] += (
            report[
                "completed_lessons"
            ]
        )

        total["cancelled"] += (
            report["cancelled"]
        )

        total["no_show"] += (
            report["no_show"]
        )

        total["sickness"] += (
            report["sickness"]
        )

        total["late_cancelled"] += (
            report[
                "late_cancelled"
            ]
        )

        total["paid_minutes"] += (
            report[
                "paid_minutes"
            ]
        )

        total["actual_minutes"] += (
            report[
                "actual_minutes"
            ]
        )

        total["extra_minutes"] += (
            report[
                "extra_minutes"
            ]
        )

        hw = report["homework"]

        total["homework_checked"] += (
            hw[
                "checked_homeworks"
            ]
        )

        total[
            "homework_total_tasks"
        ] += hw["total_tasks"]

        total[
            "homework_correct_tasks"
        ] += hw["correct_tasks"]

    total["revenue"] = round(
        total["revenue"],
        2
    )

    if total[
        "homework_total_tasks"
    ] > 0:

        total[
            "homework_accuracy_percent"
        ] = round(
            total[
                "homework_correct_tasks"
            ]
            * 100.0
            / total[
                "homework_total_tasks"
            ],
            2
        )

    else:

        total[
            "homework_accuracy_percent"
        ] = None

    return {
        "user":
            dict(user),

        "year":
            int(year),

        "month":
            int(month),

        "total":
            total,

        "programs":
            program_reports,
    }


def get_all_students_monthly_report(
    year,
    month
):

    users = get_all_users(
        active_only=False
    )

    reports = []

    total = {
        "revenue": 0.0,
        "completed_lessons": 0,
        "paid_minutes": 0,
        "actual_minutes": 0,
        "extra_minutes": 0,
        "homework_total_tasks": 0,
        "homework_correct_tasks": 0,
    }

    for user in users:

        report = (
            get_student_monthly_report(
                user["id"],
                year,
                month
            )
        )

        reports.append(
            report
        )

        student_total = (
            report["total"]
        )

        total["revenue"] += (
            student_total[
                "revenue"
            ]
        )

        total[
            "completed_lessons"
        ] += student_total[
            "completed_lessons"
        ]

        total[
            "paid_minutes"
        ] += student_total[
            "paid_minutes"
        ]

        total[
            "actual_minutes"
        ] += student_total[
            "actual_minutes"
        ]

        total[
            "extra_minutes"
        ] += student_total[
            "extra_minutes"
        ]

        total[
            "homework_total_tasks"
        ] += student_total[
            "homework_total_tasks"
        ]

        total[
            "homework_correct_tasks"
        ] += student_total[
            "homework_correct_tasks"
        ]

    total["revenue"] = round(
        total["revenue"],
        2
    )

    if total[
        "homework_total_tasks"
    ] > 0:

        total[
            "homework_accuracy_percent"
        ] = round(
            total[
                "homework_correct_tasks"
            ]
            * 100.0
            / total[
                "homework_total_tasks"
            ],
            2
        )

    else:

        total[
            "homework_accuracy_percent"
        ] = None

    return {
        "year":
            int(year),

        "month":
            int(month),

        "total":
            total,

        "students":
            reports,
    }


# ============================================================
# STUDENT / PARENT LEARNING STATISTICS
# ============================================================

def get_learning_statistics(
    user_id,
    date_from=None,
    date_to=None
):

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    programs = (
        get_student_programs(
            user_id,
            active_only=False,
            approved_only=False,
        )
    )

    per_program = []

    total = {
        "completed_lessons": 0,
        "no_show": 0,
        "late_cancelled": 0,
        "sickness": 0,
        "paid_minutes": 0,
        "actual_minutes": 0,
        "extra_minutes": 0,
        "homework_checked": 0,
        "homework_total_tasks": 0,
        "homework_correct_tasks": 0,
    }

    conn = connect()

    for program in programs:

        sql = """
            SELECT *
            FROM lessons

            WHERE
                program_id = ?
                AND lesson_status IN (
                    'COMPLETED',
                    'NO_SHOW',
                    'LATE_CANCELLED',
                    'SICKNESS'
                )
        """

        params = [
            program["id"]
        ]

        if date_from:

            sql += """
                AND DATE(start_time) >= ?
            """

            params.append(
                date_from
            )

        if date_to:

            sql += """
                AND DATE(start_time) <= ?
            """

            params.append(
                date_to
            )

        rows = conn.execute(
            sql,
            tuple(params)
        ).fetchall()

        completed = sum(
            1
            for row in rows
            if row[
                "lesson_status"
            ] == "COMPLETED"
        )

        no_show = sum(
            1
            for row in rows
            if row[
                "lesson_status"
            ] == "NO_SHOW"
        )

        late_cancelled = sum(
            1
            for row in rows
            if row[
                "lesson_status"
            ] == "LATE_CANCELLED"
        )

        sickness = sum(
            1
            for row in rows
            if row[
                "lesson_status"
            ] == "SICKNESS"
        )

        paid_minutes = sum(
            int(
                row[
                    "duration_minutes"
                ] or 0
            )
            for row in rows
            if row["charged"]
        )

        actual_minutes = sum(
            int(
                row[
                    "actual_duration_minutes"
                ] or 0
            )
            for row in rows
        )

        extra_minutes = sum(
            int(
                row[
                    "extra_minutes"
                ] or 0
            )
            for row in rows
        )

        homework = (
            get_homework_score_statistics(
                user_id,
                program_id=program[
                    "id"
                ],
                date_from=date_from,
                date_to=date_to,
            )
        )

        balance = (
            get_program_balance_breakdown(
                program["id"]
            )
        )

        item = {
            "program":
                dict(program),

            "completed_lessons":
                completed,

            "no_show":
                no_show,

            "late_cancelled":
                late_cancelled,

            "sickness":
                sickness,

            "paid_minutes":
                paid_minutes,

            "actual_minutes":
                actual_minutes,

            "extra_minutes":
                extra_minutes,

            "balance":
                balance,

            "homework":
                homework,
        }

        per_program.append(
            item
        )

        total[
            "completed_lessons"
        ] += completed

        total["no_show"] += no_show

        total[
            "late_cancelled"
        ] += late_cancelled

        total["sickness"] += sickness

        total[
            "paid_minutes"
        ] += paid_minutes

        total[
            "actual_minutes"
        ] += actual_minutes

        total[
            "extra_minutes"
        ] += extra_minutes

        total[
            "homework_checked"
        ] += homework[
            "checked_homeworks"
        ]

        total[
            "homework_total_tasks"
        ] += homework[
            "total_tasks"
        ]

        total[
            "homework_correct_tasks"
        ] += homework[
            "correct_tasks"
        ]

    conn.close()

    if total[
        "homework_total_tasks"
    ] > 0:

        total[
            "homework_accuracy_percent"
        ] = round(
            total[
                "homework_correct_tasks"
            ]
            * 100.0
            / total[
                "homework_total_tasks"
            ],
            2
        )

    else:

        total[
            "homework_accuracy_percent"
        ] = None

    return {
        "user":
            dict(user),

        "total":
            total,

        "programs":
            per_program,
    }


# ============================================================
# FULL STUDENT DELETE
# ============================================================

def get_student_delete_preview(
    user_id
):

    user = get_user(
        user_id
    )

    if user is None:

        raise ValueError(
            "Ученик не найден."
        )

    conn = connect()

    counts = {}

    for table_name in [
        "student_programs",
        "lessons",
        "payments",
        "lesson_packages",
        "regular_schedules",
        "homework",
        "promo_code_usages",
        "lesson_time_adjustments",
    ]:

        if not table_exists(
            conn,
            table_name
        ):

            counts[
                table_name
            ] = 0

            continue

        columns = table_columns(
            conn,
            table_name
        )

        if "user_id" not in columns:

            counts[
                table_name
            ] = 0

            continue

        counts[
            table_name
        ] = int(
            conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {table_name}
                WHERE user_id = ?
                """,
                (
                    user_id,
                )
            ).fetchone()[0]
        )

    conn.close()

    return {
        "user":
            dict(user),

        "counts":
            counts,

        "has_financial_history":
            bool(
                counts.get(
                    "payments",
                    0
                )
                or counts.get(
                    "lesson_packages",
                    0
                )
            ),
    }


def delete_student_completely(
    user_id
):

    preview = (
        get_student_delete_preview(
            user_id
        )
    )

    conn = connect()
    cursor = conn.cursor()

    cursor.execute(
        "BEGIN IMMEDIATE"
    )

    # Таблицы, где FK может не покрывать старые записи,
    # чистим явно.
    if table_exists(
        conn,
        "promo_code_usages"
    ):

        cursor.execute("""
            DELETE FROM promo_code_usages
            WHERE user_id = ?
        """, (
            user_id,
        ))

    if table_exists(
        conn,
        "lesson_time_adjustments"
    ):

        cursor.execute("""
            DELETE FROM lesson_time_adjustments
            WHERE user_id = ?
        """, (
            user_id,
        ))

    # Удаление users каскадно очищает большинство
    # зависимых таблиц благодаря ON DELETE CASCADE.
    cursor.execute("""
        DELETE FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    if cursor.rowcount == 0:

        conn.rollback()
        conn.close()

        raise ValueError(
            "Ученик не найден."
        )

    conn.commit()

    # Освобождаем неиспользуемые страницы SQLite.
    try:
        conn.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        )

        conn.execute(
            "VACUUM"
        )
    except Exception:
        pass

    conn.close()

    return preview


# ============================================================
# STATISTICS
# ============================================================

def get_lesson_time_history(
    user_id,
    date_from=None,
    date_to=None
):

    conn = connect()

    sql = """
        SELECT *
        FROM lessons

        WHERE
            user_id = ?

            AND lesson_status IN (
                'COMPLETED',
                'NO_SHOW',
                'LATE_CANCELLED',
                'SICKNESS'
            )
    """

    params = [
        user_id
    ]

    if date_from:

        sql += """
            AND DATE(start_time) >= ?
        """

        params.append(
            date_from
        )

    if date_to:

        sql += """
            AND DATE(start_time) <= ?
        """

        params.append(
            date_to
        )

    sql += """
        ORDER BY
            start_time
    """

    rows = conn.execute(
        sql,
        tuple(params)
    ).fetchall()

    conn.close()

    return rows


def get_student_statistics(
    user_id,
    date_from=None,
    date_to=None
):

    lessons = (
        get_lesson_time_history(
            user_id,
            date_from,
            date_to
        )
    )

    completed = 0
    no_show = 0
    late_cancelled = 0
    sickness = 0

    paid_minutes = 0
    actual_minutes = 0
    extra_minutes = 0

    lesson_details = []

    for lesson in lessons:

        status = (
            lesson[
                "lesson_status"
            ]
        )

        if status == "COMPLETED":

            completed += 1

        elif status == "NO_SHOW":

            no_show += 1

        elif status == "LATE_CANCELLED":

            late_cancelled += 1

        elif status == "SICKNESS":

            sickness += 1

        if lesson["charged"]:

            paid_minutes += int(
                lesson[
                    "duration_minutes"
                ] or 0
            )

        actual = int(
            lesson[
                "actual_duration_minutes"
            ] or 0
        )

        extra = int(
            lesson[
                "extra_minutes"
            ] or 0
        )

        actual_minutes += actual
        extra_minutes += extra

        lesson_details.append({

            "lesson_id":
                lesson["id"],

            "date":
                lesson["start_time"],

            "status":
                status,

            "paid_minutes":
                (
                    int(
                        lesson[
                            "duration_minutes"
                        ] or 0
                    )
                    if lesson[
                        "charged"
                    ]
                    else 0
                ),

            "actual_minutes":
                actual,

            "extra_minutes":
                extra,
        })

    conn = connect()

    homework_total = conn.execute("""
        SELECT COUNT(*)
        FROM homework

        WHERE user_id = ?
    """, (
        user_id,
    )).fetchone()[0]

    homework_reviewed = conn.execute("""
        SELECT COUNT(*)
        FROM homework

        WHERE
            user_id = ?

            AND status =
                'REVIEWED'
    """, (
        user_id,
    )).fetchone()[0]

    user = conn.execute("""
        SELECT
            extra_minutes_balance,
            bonus_lessons_earned

        FROM users

        WHERE id = ?
    """, (
        user_id,
    )).fetchone()

    conn.close()

    balance = (
        get_balance_breakdown(
            user_id
        )
    )

    return {

        "completed_lessons":
            completed,

        "no_show":
            no_show,

        "late_cancelled":
            late_cancelled,

        "sickness":
            sickness,

        "paid_minutes":
            paid_minutes,

        "actual_minutes":
            actual_minutes,

        "extra_minutes_total":
            extra_minutes,

        "extra_minutes_balance":
            int(
                user[
                    "extra_minutes_balance"
                ] or 0
            ),

        "bonus_lessons_earned":
            int(
                user[
                    "bonus_lessons_earned"
                ] or 0
            ),

        "homework_total":
            int(
                homework_total
            ),

        "homework_reviewed":
            int(
                homework_reviewed
            ),

        "balance_paid":
            balance["paid"],

        "balance_bonus":
            balance["bonus"],

        "balance_total":
            balance["total"],

        "lessons":
            lesson_details,
    }


# ============================================================
# BOT SETTINGS
# ============================================================

def get_setting(
    key,
    default=None,
    conn=None,
):

    own_conn = conn is None
    if own_conn:
        conn = connect()

    row = conn.execute("""
        SELECT value
        FROM bot_settings
        WHERE key = ?
    """, (
        str(key),
    )).fetchone()

    if own_conn:
        conn.close()

    if row is None:
        return default

    return row["value"]


def set_setting(
    key,
    value
):

    conn = connect()

    conn.execute("""
        INSERT INTO bot_settings (
            key,
            value,
            updated_at
        )

        VALUES (
            ?, ?, ?
        )

        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
    """, (
        str(key),
        None if value is None else str(value),
        now_iso(),
    ))

    conn.commit()
    conn.close()


def delete_setting(
    key
):

    conn = connect()

    conn.execute("""
        DELETE FROM bot_settings
        WHERE key = ?
    """, (
        str(key),
    ))

    conn.commit()
    conn.close()


# ============================================================
# DIRECT RUN
# ============================================================

if __name__ == "__main__":

    create_tables()

    print(
        "========================================"
    )

    print(
        "✅ TutorBot Database V3 готова"
    )

    print(
        "👥 Ученики: OK"
    )

    print(
        "📚 Несколько направлений ученика: OK"
    )

    print(
        "💰 Цена отдельно по направлению: OK"
    )

    print(
        "📝 Результаты ДЗ: правильно / всего: OK"
    )

    print(
        "📊 Месячные отчёты по ученику / всем: OK"
    )

    print(
        "👨‍👩‍👧 Статистика ученика и родителей: OK"
    )

    print(
        "🗑 Полное удаление ученика: OK"
    )

    print(
        "💳 Оплаты: OK"
    )

    print(
        "🎟 Абонементы: OK"
    )

    print(
        "🎁 Бонусные занятия: OK"
    )

    print(
        "📅 Заявки на занятия: OK"
    )

    print(
        "🕐 Рабочие часы: OK"
    )

    print(
        "🚫 Исключения расписания: OK"
    )

    print(
        "🔁 Постоянное расписание: OK"
    )

    print(
        "📆 Постоянное расписание до конца года: OK"
    )

    print(
        "⏸ Пауза постоянного расписания: OK"
    )

    print(
        "❌ Отмена постоянного расписания: OK"
    )

    print(
        "📚 Генерация занятий из серии: OK"
    )

    print(
        "🎟 Списание занятия серии только при проведении: OK"
    )

    print(
        "🔒 Одна PENDING-заявка ученика: OK"
    )

    print(
        "📆 Одно самостоятельное занятие в день: OK"
    )

    print(
        "👨‍🏫 Ручная запись преподавателем: OK"
    )

    print(
        "💳 Ручная неоплаченная запись: OK"
    )

    print(
        "⏰ Дедлайн оплаты −2 часа: OK"
    )

    print(
        "❌ Автоотмена неоплаченной записи: OK"
    )

    print(
        "🔁 Бесплатный перенос >2 часов: OK"
    )

    print(
        "⚠️ Поздний перенос <2 часов: OK"
    )

    print(
        "🤒 Больничные: OK"
    )

    print(
        "▶️ Фактическое начало: OK"
    )

    print(
        "⏹ Фактическое окончание: OK"
    )

    print(
        "⏱ Фактические / оплаченные минуты: OK"
    )

    print(
        "🎉 Бонусы за переработку: OK"
    )

    print(
        "📝 Домашние задания: OK"
    )

    print(
        "📊 Статистика: OK"
    )

    print(
        "========================================"
    )


# ============================================================
# PARENTS / LINKED ACCOUNTS
# ============================================================

def get_parent_by_telegram_id(telegram_id):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM parent_accounts WHERE telegram_id = ?",
        (telegram_id,),
    ).fetchone()
    conn.close()
    return row


def get_parent(parent_id):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM parent_accounts WHERE id = ?",
        (parent_id,),
    ).fetchone()
    conn.close()
    return row


def add_parent_account(telegram_id, telegram_username, name, phone=None):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO parent_accounts (
            telegram_id, telegram_username, name, phone, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            normalize_username(telegram_username),
            name,
            phone,
            now_iso(),
        ),
    )
    parent_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return parent_id


def get_or_create_student_link_code(student_id):
    conn = connect()
    row = conn.execute(
        "SELECT code FROM student_link_codes WHERE student_id = ?",
        (student_id,),
    ).fetchone()
    if row:
        code = row["code"]
        conn.close()
        return code

    # Короткий одноразово выглядящий код. Его можно перевыпустить вручную позднее.
    while True:
        code = secrets.token_hex(3).upper()
        exists = conn.execute(
            "SELECT 1 FROM student_link_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not exists:
            break

    conn.execute(
        "INSERT INTO student_link_codes (student_id, code, created_at) VALUES (?, ?, ?)",
        (student_id, code, now_iso()),
    )
    conn.commit()
    conn.close()
    return code


def regenerate_student_link_code(student_id):
    conn = connect()
    while True:
        code = secrets.token_hex(3).upper()
        exists = conn.execute(
            "SELECT 1 FROM student_link_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not exists:
            break
    conn.execute(
        """
        INSERT INTO student_link_codes (student_id, code, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id) DO UPDATE SET code = excluded.code, created_at = excluded.created_at
        """,
        (student_id, code, now_iso()),
    )
    conn.commit()
    conn.close()
    return code


def link_parent_to_student_by_code(parent_id, code, max_parents=2):
    code = (code or "").strip().upper()
    conn = connect()
    row = conn.execute("SELECT student_id FROM student_link_codes WHERE code = ?", (code,)).fetchone()
    if not row:
        conn.close()
        return {"status": "invalid_code", "student": None}
    student_id = row["student_id"]
    existing = conn.execute(
        "SELECT 1 FROM parent_student_links WHERE parent_id = ? AND student_id = ?",
        (parent_id, student_id),
    ).fetchone()
    student = conn.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()
    if existing:
        conn.close()
        return {"status": "already_linked", "student": student}
    count = conn.execute(
        """SELECT COUNT(*) AS cnt
           FROM parent_student_links l
           JOIN parent_accounts p ON p.id = l.parent_id
           WHERE l.student_id = ? AND p.active = 1""",
        (student_id,),
    ).fetchone()["cnt"]
    if count >= max_parents:
        conn.close()
        return {"status": "limit_reached", "student": student}
    conn.execute(
        """INSERT INTO parent_student_links
           (parent_id, student_id, notify_schedule, created_at)
           VALUES (?, ?, 1, ?)""",
        (parent_id, student_id, now_iso()),
    )
    conn.commit(); conn.close()
    return {"status": "linked", "student": student}


def unlink_parent_from_student(parent_id, student_id):
    conn = connect()
    cur = conn.execute(
        "DELETE FROM parent_student_links WHERE parent_id = ? AND student_id = ?",
        (parent_id, student_id),
    )
    conn.commit(); conn.close()
    return cur.rowcount > 0


def get_parent_students(parent_id):
    conn = connect()
    rows = conn.execute(
        """
        SELECT u.*, l.notify_schedule
        FROM parent_student_links l
        JOIN users u ON u.id = l.student_id
        WHERE l.parent_id = ? AND u.active = 1
        ORDER BY u.name COLLATE NOCASE
        """,
        (parent_id,),
    ).fetchall()
    conn.close()
    return rows


def get_student_parents(student_id, schedule_only=False):
    conn = connect()
    sql = """
        SELECT p.*, l.notify_schedule
        FROM parent_student_links l
        JOIN parent_accounts p ON p.id = l.parent_id
        WHERE l.student_id = ? AND p.active = 1
    """
    params = [student_id]
    if schedule_only:
        sql += " AND l.notify_schedule = 1"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


# ============================================================
# ADMIN: PARENTS DIRECTORY
# ============================================================

def get_all_parents(active_only=False):
    conn = connect()
    sql = """
        SELECT p.*, COUNT(l.student_id) AS students_count
        FROM parent_accounts p
        LEFT JOIN parent_student_links l ON l.parent_id = p.id
    """
    params = []
    if active_only:
        sql += " WHERE p.active = 1"
    sql += " GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_parent_students_admin(parent_id):
    conn = connect()
    rows = conn.execute(
        """
        SELECT u.*, l.notify_schedule
        FROM parent_student_links l
        JOIN users u ON u.id = l.student_id
        WHERE l.parent_id = ?
        ORDER BY u.name COLLATE NOCASE
        """,
        (int(parent_id),),
    ).fetchall()
    conn.close()
    return rows


# ============================================================
# PAYMENT METHODS
# ============================================================

def ensure_payment_method(title, details):
    """Create the first/default payment method only when the directory is empty."""
    conn = connect()
    row = conn.execute("SELECT id FROM payment_methods ORDER BY id LIMIT 1").fetchone()
    if row:
        conn.close()
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO payment_methods(title, details, active, is_default, created_at)
        VALUES(?, ?, 1, 1, ?)
        """,
        (str(title).strip(), str(details).strip(), now_iso()),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return int(rid)


def get_payment_methods(active_only=False):
    conn = connect()
    sql = "SELECT * FROM payment_methods"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY is_default DESC, active DESC, title COLLATE NOCASE, id"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return rows


def get_payment_method(method_id):
    conn = connect()
    row = conn.execute("SELECT * FROM payment_methods WHERE id = ?", (int(method_id),)).fetchone()
    conn.close()
    return row


def get_default_payment_method():
    conn = connect()
    row = conn.execute(
        """
        SELECT * FROM payment_methods
        WHERE active = 1
        ORDER BY is_default DESC, id ASC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row


def add_payment_method(title, details, make_default=False):
    title = str(title or "").strip()
    details = str(details or "").strip()
    if not title or not details:
        raise ValueError("Название и реквизиты обязательны.")
    conn = connect()
    if make_default:
        conn.execute("UPDATE payment_methods SET is_default = 0")
    cur = conn.execute(
        """
        INSERT INTO payment_methods(title, details, active, is_default, created_at)
        VALUES(?, ?, 1, ?, ?)
        """,
        (title, details, 1 if make_default else 0, now_iso()),
    )
    # Если это первый способ, автоматически делаем его основным.
    if conn.execute("SELECT COUNT(*) FROM payment_methods").fetchone()[0] == 1:
        conn.execute("UPDATE payment_methods SET is_default = 1 WHERE id = ?", (cur.lastrowid,))
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return int(rid)


def set_payment_method_default(method_id):
    conn = connect()
    row = conn.execute("SELECT id FROM payment_methods WHERE id = ?", (int(method_id),)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE payment_methods SET is_default = 0")
    conn.execute(
        "UPDATE payment_methods SET is_default = 1, active = 1, updated_at = ? WHERE id = ?",
        (now_iso(), int(method_id)),
    )
    conn.commit()
    conn.close()
    return True


def toggle_payment_method(method_id):
    conn = connect()
    row = conn.execute("SELECT active, is_default FROM payment_methods WHERE id = ?", (int(method_id),)).fetchone()
    if not row:
        conn.close()
        return None
    new_active = 0 if int(row["active"] or 0) else 1
    conn.execute(
        "UPDATE payment_methods SET active = ?, updated_at = ? WHERE id = ?",
        (new_active, now_iso(), int(method_id)),
    )
    if not new_active and int(row["is_default"] or 0):
        conn.execute("UPDATE payment_methods SET is_default = 0 WHERE id = ?", (int(method_id),))
        replacement = conn.execute("SELECT id FROM payment_methods WHERE active = 1 AND id != ? ORDER BY id LIMIT 1", (int(method_id),)).fetchone()
        if replacement:
            conn.execute("UPDATE payment_methods SET is_default = 1 WHERE id = ?", (replacement["id"],))
    conn.commit()
    conn.close()
    return bool(new_active)


def delete_payment_method(method_id):
    conn = connect()
    row = conn.execute("SELECT is_default FROM payment_methods WHERE id = ?", (int(method_id),)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("DELETE FROM payment_methods WHERE id = ?", (int(method_id),))
    if int(row["is_default"] or 0):
        replacement = conn.execute("SELECT id FROM payment_methods WHERE active = 1 ORDER BY id LIMIT 1").fetchone()
        if replacement:
            conn.execute("UPDATE payment_methods SET is_default = 1 WHERE id = ?", (replacement["id"],))
    conn.commit()
    conn.close()
    return True


# ============================================================
# AUTOMATION DELIVERY HISTORY
# ============================================================
def _ensure_automation_delivery_log():
    c = connect()
    try:
        c.execute("""
            CREATE TABLE IF NOT EXISTS automation_delivery_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                recipient_type TEXT,
                recipient_id TEXT,
                status TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_automation_delivery_created ON automation_delivery_log(created_at DESC)")
        c.commit()
    finally:
        c.close()


def log_automation_delivery(kind, status, recipient_type=None, recipient_id=None, detail=None):
    _ensure_automation_delivery_log()
    c = connect()
    try:
        c.execute(
            "INSERT INTO automation_delivery_log(kind,recipient_type,recipient_id,status,detail,created_at) VALUES(?,?,?,?,?,datetime('now'))",
            (str(kind), recipient_type, str(recipient_id) if recipient_id is not None else None, str(status), (str(detail)[:700] if detail else None)),
        )
        c.commit()
    finally:
        c.close()


def get_automation_delivery_history(limit=20):
    _ensure_automation_delivery_log()
    c = connect()
    try:
        return c.execute(
            "SELECT * FROM automation_delivery_log ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
    finally:
        c.close()


# ============================================================
# USER TIMEZONES / REGION MIGRATION
# ============================================================

def get_user_timezone(telegram_id):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM user_timezones WHERE telegram_id = ?",
        (int(telegram_id),),
    ).fetchone()
    conn.close()
    return row


def set_user_timezone(telegram_id, msk_offset, zone_name=None, configured=True):
    conn = connect()
    now = now_iso()
    conn.execute(
        """
        INSERT INTO user_timezones (telegram_id, msk_offset, zone_name, configured, configured_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            msk_offset=excluded.msk_offset,
            zone_name=excluded.zone_name,
            configured=excluded.configured,
            configured_at=CASE WHEN excluded.configured=1 THEN excluded.configured_at ELSE user_timezones.configured_at END,
            updated_at=excluded.updated_at
        """,
        (int(telegram_id), int(msk_offset), zone_name, 1 if configured else 0, now if configured else None, now),
    )
    conn.commit(); conn.close()

def mark_timezone_notified(telegram_id):
    conn = connect(); now = now_iso()
    conn.execute(
        """
        INSERT INTO user_timezones (telegram_id, msk_offset, configured, notified_at, updated_at)
        VALUES (?, 0, 0, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET notified_at=excluded.notified_at, updated_at=excluded.updated_at
        """,
        (int(telegram_id), now, now),
    )
    conn.commit(); conn.close()

def timezone_notification_pending(telegram_id):
    row = get_user_timezone(telegram_id)
    return row is None or not row['notified_at']

def timezone_configured(telegram_id):
    row = get_user_timezone(telegram_id)
    return bool(row and int(row['configured'] or 0))

def get_timezone_migration_stats():
    conn = connect()
    row = conn.execute(
        "SELECT SUM(CASE WHEN configured=1 THEN 1 ELSE 0 END) AS configured, SUM(CASE WHEN configured=0 THEN 1 ELSE 0 END) AS pending FROM user_timezones"
    ).fetchone()
    conn.close()
    return {'configured': int((row['configured'] if row else 0) or 0), 'pending': int((row['pending'] if row else 0) or 0)}


def freeze_legacy_lesson_timezones():
    """Attach the current teacher timezone to legacy naive lesson timestamps once.

    Older TutorBot builds could store local ISO strings without an offset. If the
    teacher later changes region, interpreting those strings in the *new* zone
    would move the real lesson. This migration freezes existing start/end
    timestamps to the timezone that was active before personal regions existed.
    """
    if get_setting('lesson_timezone_canonicalized_v1', '0') == '1':
        return 0
    from datetime import datetime
    from zoneinfo import ZoneInfo
    zone_name = get_setting('bot_timezone', 'Europe/Samara') or 'Europe/Samara'
    try:
        tz = ZoneInfo(zone_name)
    except Exception:
        tz = ZoneInfo('Europe/Samara')
    conn = connect()
    rows = conn.execute("SELECT id,start_time,end_time FROM lessons").fetchall()
    changed = 0
    for row in rows:
        updates = {}
        for field in ('start_time','end_time'):
            value = row[field]
            if not value:
                continue
            try:
                dt = datetime.fromisoformat(str(value))
            except Exception:
                continue
            if dt.tzinfo is None:
                updates[field] = dt.replace(tzinfo=tz).isoformat()
        if updates:
            sets = ', '.join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE lessons SET {sets} WHERE id=?", (*updates.values(), int(row['id'])))
            changed += 1
    conn.commit(); conn.close()
    set_setting('lesson_timezone_canonicalized_v1', '1')
    return changed
