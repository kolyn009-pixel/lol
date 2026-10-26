"""Expose previous channel results without resending a successful notification."""
import database

def previous_individual(result, lesson_id):
    if result.get('status') != 'already_sent':
        return result
    conn = database.connect()
    try:
        row = conn.execute("SELECT message_id FROM lesson_link_deliveries WHERE object_type='INDIVIDUAL' AND object_id=? AND user_id=?", (int(lesson_id), int(result['user_id']))).fetchone()
        if not row or not row['message_id']:
            return result
        mid = int(row['message_id'])
        rows = conn.execute("SELECT channel,status,error_code FROM unified_message_deliveries WHERE message_id=? AND recipient_type='STUDENT' ORDER BY id", (mid,)).fetchall()
        return {**result, 'message_id': mid, 'deliveries': {str(x['channel']).lower(): {'status': x['status'], 'error': x['error_code']} for x in rows if x['channel'] != 'WEB'}}
    finally:
        conn.close()
