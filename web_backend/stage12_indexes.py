"""Small additive indexes for privacy-scoped web queries.

These indexes match the high-frequency WHERE clauses used by student/parent PWA
screens and security ownership checks. They are additive and safe to create on
existing SQLite databases.
"""
from database import connect


def ensure_indexes():
    conn = connect()
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_parent_links_parent_student
            ON parent_student_links(parent_id, student_id);
        CREATE INDEX IF NOT EXISTS idx_parent_links_student
            ON parent_student_links(student_id, parent_id);

        CREATE INDEX IF NOT EXISTS idx_payments_user_status_created
            ON payments(user_id, status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_receipts_user_created
            ON receipts(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_receipts_payment
            ON receipts(payment_id, id DESC);

        CREATE INDEX IF NOT EXISTS idx_homework_user_status_deadline
            ON homework(user_id, status, deadline);
        CREATE INDEX IF NOT EXISTS idx_homework_submissions_user_homework
            ON homework_submissions(user_id, homework_id, attempt_number);

        CREATE INDEX IF NOT EXISTS idx_lessons_user_status_start
            ON lessons(user_id, lesson_status, start_time);
        """
    )
    conn.commit()
    conn.close()
