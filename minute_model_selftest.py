"""Safe post-update self-check for minute subscriptions.
Does not create lessons or payments. It only runs schema migration and read checks.
"""
import database
from core import minute_balance, admin_inbox


def main():
    minute_balance.ensure_schema()
    conn=database.connect()
    try:
        required={
            'student_programs': {'default_duration_minutes'},
            'payments': {'minutes_total','base_duration_minutes','hourly_rate'},
            'lesson_packages': {'minutes_total','minutes_used','base_duration_minutes','hourly_rate'},
            'lessons': {'reserved_minutes','reserved_paid_minutes','reserved_bonus_minutes'},
        }
        for table,cols in required.items():
            actual={r['name'] for r in conn.execute(f'PRAGMA table_info({table})')}
            missing=cols-actual
            if missing:
                raise RuntimeError(f'{table}: missing {sorted(missing)}')
        if not conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lesson_minute_charges'").fetchone():
            raise RuntimeError('lesson_minute_charges table missing')
        bad=conn.execute("""
            SELECT COUNT(*) c FROM lesson_packages
            WHERE COALESCE(minutes_used,0)<0 OR COALESCE(minutes_total,0)<0
               OR COALESCE(minutes_used,0)>COALESCE(minutes_total,0)
        """).fetchone()['c']
        if bad:
            raise RuntimeError(f'invalid minute packages: {bad}')
    finally:
        conn.close()
    counts=admin_inbox.counts()
    print('MINUTE MODEL: OK')
    print('Unified inbox:',counts)
    print('Reminder chain expected: 24h / 2h / 30m / 10m')


if __name__=='__main__':
    main()
