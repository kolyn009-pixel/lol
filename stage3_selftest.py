import os, shutil, tempfile
import database
from automation import schema, balance_forecast, student_history, operations


def main():
    source=database.DB_NAME
    fd,tmp=tempfile.mkstemp(prefix='tutor_stage3_',suffix='.db'); os.close(fd)
    shutil.copy2(source,tmp)
    old=database.DB_NAME
    try:
        database.DB_NAME=tmp
        database.create_tables(); schema.initialize()
        conn=database.connect()
        required={'waiting_list','student_pauses','parent_notification_settings','teacher_inbox','scheduled_messages','referrals','student_timeline','lesson_groups','teacher_absences','student_tags','message_templates','academic_periods','monthly_reports_log'}
        have={r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}; conn.close()
        missing=required-have
        if missing: raise RuntimeError('Missing tables: '+', '.join(sorted(missing)))
        conn=database.connect(); user=conn.execute('SELECT id FROM users LIMIT 1').fetchone(); conn.close()
        if user:
            balance_forecast.forecast(user['id']); student_history.rebuild_basic(user['id'])
        operations.today_dashboard(); operations.attention_items()
        print('STAGE3 SELFTEST: OK')
    finally:
        database.DB_NAME=old
        try: os.remove(tmp)
        except OSError: pass

if __name__=='__main__': main()
