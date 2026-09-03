import sqlite3
from datetime import datetime
import database


def initialize():
    conn = database.connect()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS waiting_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT,
        study_goal TEXT,
        preferred_date TEXT,
        preferred_from TEXT,
        preferred_to TEXT,
        note TEXT,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        notified_at TEXT,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_waiting_list_active ON waiting_list(status, preferred_date);

    CREATE TABLE IF NOT EXISTS student_pauses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        reason TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_student_pauses_dates ON student_pauses(student_id, date_from, date_to, active);

    CREATE TABLE IF NOT EXISTS parent_notification_settings (
        parent_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        remind_24h INTEGER NOT NULL DEFAULT 1,
        remind_2h INTEGER NOT NULL DEFAULT 1,
        remind_30m INTEGER NOT NULL DEFAULT 0,
        remind_10m INTEGER NOT NULL DEFAULT 0,
        schedule_changes INTEGER NOT NULL DEFAULT 1,
        payments INTEGER NOT NULL DEFAULT 1,
        monthly_report INTEGER NOT NULL DEFAULT 1,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(parent_id, student_id)
    );

    CREATE TABLE IF NOT EXISTS teacher_inbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        parent_id INTEGER,
        sender_telegram_id INTEGER,
        category TEXT NOT NULL DEFAULT 'ORGANIZATIONAL',
        subject TEXT,
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        created_at TEXT NOT NULL,
        closed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_teacher_inbox_status ON teacher_inbox(status, created_at);

    CREATE TABLE IF NOT EXISTS scheduled_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_by INTEGER NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER,
        segment_json TEXT,
        text TEXT NOT NULL,
        send_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at TEXT NOT NULL,
        sent_at TEXT,
        error_text TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_scheduled_messages_due ON scheduled_messages(status, send_at);

    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_student_id INTEGER NOT NULL,
        invited_student_id INTEGER,
        code TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        reward_lessons INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        rewarded_at TEXT,
        FOREIGN KEY(referrer_student_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(invited_student_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS student_timeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        title TEXT NOT NULL,
        details TEXT,
        source_type TEXT,
        source_id INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_student_timeline_student ON student_timeline(student_id, created_at DESC);

    CREATE TABLE IF NOT EXISTS lesson_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        subject TEXT,
        study_goal TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS lesson_group_members (
        group_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        individual_price INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY(group_id, student_id),
        FOREIGN KEY(group_id) REFERENCES lesson_groups(id) ON DELETE CASCADE,
        FOREIGN KEY(student_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS teacher_absences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        reason TEXT,
        mode TEXT NOT NULL DEFAULT 'SICK',
        active INTEGER NOT NULL DEFAULT 1,
        created_by INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS student_tags (
        student_id INTEGER NOT NULL,
        tag TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(student_id, tag)
    );

    CREATE TABLE IF NOT EXISTS message_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        text TEXT NOT NULL,
        created_by INTEGER,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS academic_periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        date_from TEXT NOT NULL,
        date_to TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS monthly_reports_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        report_text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'DRAFT',
        created_by INTEGER,
        created_at TEXT NOT NULL,
        sent_at TEXT
    );
    ''')
    conn.commit(); conn.close()
