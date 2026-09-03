from __future__ import annotations
import database


def _cols(conn, table):
    return {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _add(conn, table, name, definition):
    if name not in _cols(conn, table):
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')


def initialize():
    conn = database.connect()
    # A few additive columns only. Existing Stage1/2/3 tables stay untouched.
    _add(conn, 'student_programs', 'exam_date', 'TEXT')
    _add(conn, 'student_programs', 'exam_target_score', 'REAL')
    _add(conn, 'student_programs', 'discount_profile', "TEXT DEFAULT 'STANDARD'")
    _add(conn, 'lessons', 'post_lesson_reviewed', 'INTEGER DEFAULT 0')
    _add(conn, 'lessons', 'teacher_planned_minutes', 'INTEGER')

    conn.executescript('''
    CREATE TABLE IF NOT EXISTS minute_ledger (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      program_id INTEGER,
      lesson_id INTEGER,
      payment_id INTEGER,
      package_id INTEGER,
      operation TEXT NOT NULL,
      paid_minutes_delta INTEGER NOT NULL DEFAULT 0,
      bonus_minutes_delta INTEGER NOT NULL DEFAULT 0,
      money_rubles INTEGER NOT NULL DEFAULT 0,
      hourly_rate INTEGER,
      reason TEXT,
      actor_id INTEGER,
      idempotency_key TEXT UNIQUE,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_minute_ledger_user ON minute_ledger(user_id,created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_minute_ledger_lesson ON minute_ledger(lesson_id);

    CREATE TABLE IF NOT EXISTS tariff_discount_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      study_goal TEXT NOT NULL,
      subject TEXT NOT NULL DEFAULT '',
      base_duration_minutes INTEGER NOT NULL,
      equivalent_lessons INTEGER NOT NULL,
      discount_percent INTEGER NOT NULL DEFAULT 0,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(study_goal,subject,base_duration_minutes,equivalent_lessons)
    );

    CREATE TABLE IF NOT EXISTS smart_actions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      action_type TEXT NOT NULL,
      priority TEXT NOT NULL DEFAULT 'INFO',
      title TEXT NOT NULL,
      details TEXT,
      status TEXT NOT NULL DEFAULT 'OPEN',
      source_type TEXT,
      source_id INTEGER,
      created_at TEXT NOT NULL,
      resolved_at TEXT,
      UNIQUE(user_id,action_type,source_type,source_id,status)
    );
    CREATE INDEX IF NOT EXISTS idx_smart_actions_status ON smart_actions(status,priority,created_at);

    CREATE TABLE IF NOT EXISTS reschedule_exchange_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id INTEGER NOT NULL,
      lesson_id INTEGER,
      desired_date TEXT,
      desired_from TEXT,
      desired_to TEXT,
      min_duration_minutes INTEGER,
      status TEXT NOT NULL DEFAULT 'OPEN',
      matched_request_id INTEGER,
      created_at TEXT NOT NULL,
      matched_at TEXT
    );

    CREATE TABLE IF NOT EXISTS post_lesson_reviews (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      lesson_id INTEGER NOT NULL UNIQUE,
      user_id INTEGER NOT NULL,
      rating INTEGER,
      summary TEXT,
      homework_note TEXT,
      created_by INTEGER,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS post_lesson_topic_marks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      review_id INTEGER NOT NULL,
      topic_id INTEGER NOT NULL,
      level TEXT NOT NULL,
      comment TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(review_id,topic_id)
    );

    CREATE TABLE IF NOT EXISTS exam_prep_plans (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      program_id INTEGER NOT NULL,
      exam_type TEXT NOT NULL,
      exam_date TEXT NOT NULL,
      target_score REAL,
      minutes_per_week INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'ACTIVE',
      generated_summary TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(user_id,program_id,status)
    );

    CREATE TABLE IF NOT EXISTS mock_tests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      program_id INTEGER,
      subject TEXT NOT NULL,
      exam_type TEXT NOT NULL,
      title TEXT NOT NULL,
      deadline TEXT,
      file_id TEXT,
      url TEXT,
      teacher_comment TEXT,
      status TEXT NOT NULL DEFAULT 'ASSIGNED',
      primary_score REAL,
      test_score REAL,
      duration_minutes INTEGER,
      result_comment TEXT,
      assigned_by INTEGER,
      assigned_at TEXT NOT NULL,
      submitted_at TEXT,
      reviewed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_mock_tests_user ON mock_tests(user_id,status,assigned_at DESC);

    CREATE TABLE IF NOT EXISTS mock_test_topic_errors (
      mock_test_id INTEGER NOT NULL,
      topic_id INTEGER NOT NULL,
      severity TEXT NOT NULL DEFAULT 'WEAK',
      note TEXT,
      PRIMARY KEY(mock_test_id,topic_id)
    );

    CREATE TABLE IF NOT EXISTS progress_report_drafts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      period_from TEXT NOT NULL,
      period_to TEXT NOT NULL,
      audience TEXT NOT NULL DEFAULT 'STUDENT',
      report_text TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'DRAFT',
      created_by INTEGER,
      created_at TEXT NOT NULL,
      sent_at TEXT
    );

    CREATE TABLE IF NOT EXISTS health_check_runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      check_type TEXT NOT NULL,
      status TEXT NOT NULL,
      details TEXT,
      created_at TEXT NOT NULL
    );
    ''')
    conn.commit(); conn.close()
