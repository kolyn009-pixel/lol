"""Read-only first-visit context for a teacher's learning-plan screen."""
import database


def first_visit(user_id):
    conn = database.connect()
    try:
        return conn.execute("SELECT 1 FROM lessons WHERE user_id=? AND lesson_status='COMPLETED' LIMIT 1",
                            (int(user_id),)).fetchone() is None
    finally:
        conn.close()
