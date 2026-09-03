import os, tempfile
from datetime import datetime
from pathlib import Path

import database
from core import user_timezone

fd, path = tempfile.mkstemp(prefix='adelia_tz_', suffix='.db')
os.close(fd)
try:
    database.DB_NAME = path
    database.create_tables()

    # Student in Irkutsk-like MСК+5 sees Moscow 15:00 as 20:00.
    database.set_user_timezone(1001, 5, 'Asia/Irkutsk', True)
    assert user_timezone.user_label(1001, 'Europe/Moscow') == 'МСК +5'
    dt = user_timezone.convert_for_user('2026-08-29T15:00:00+03:00', 1001, 'Europe/Moscow')
    assert dt.strftime('%Y-%m-%d %H:%M') == '2026-08-29 20:00'

    # Custom MСК-2 fixed offset.
    database.set_user_timezone(1002, -2, None, True)
    dt2 = user_timezone.convert_for_user('2026-08-29T15:00:00+03:00', 1002, 'Europe/Moscow')
    assert dt2.strftime('%H:%M') == '13:00'
    assert user_timezone.user_label(1002) == 'МСК -2'

    # Date rollover must be visible to users.
    database.set_user_timezone(1003, 5, 'Asia/Irkutsk', True)
    dt3 = user_timezone.convert_for_user('2026-08-29T19:30:00+03:00', 1003, 'Europe/Moscow')
    assert dt3.strftime('%Y-%m-%d %H:%M') == '2026-08-30 00:30'

    # Legacy naive lesson timestamps are frozen before teacher timezone changes.
    conn = database.connect()
    conn.execute("INSERT INTO users(telegram_id,name,grade,study_goal,main_subject,created_at) VALUES(?,?,?,?,?,?)", (2001,'Test',9,'GOAL','SUBJ',database.now_iso()))
    uid = conn.execute('SELECT id FROM users WHERE telegram_id=2001').fetchone()[0]
    conn.execute("INSERT INTO lessons(user_id,study_goal,subject,start_time,end_time,duration_minutes,created_at) VALUES(?,?,?,?,?,?,?)", (uid,'GOAL','SUBJ','2026-08-29T15:00:00','2026-08-29T16:00:00',60,database.now_iso()))
    conn.commit(); conn.close()
    database.set_setting('bot_timezone','Europe/Moscow')
    database.set_setting('lesson_timezone_canonicalized_v1','0')
    changed = database.freeze_legacy_lesson_timezones()
    assert changed == 1
    row = database.connect().execute('SELECT start_time FROM lessons WHERE user_id=?',(uid,)).fetchone()
    frozen = datetime.fromisoformat(row['start_time'])
    assert frozen.utcoffset().total_seconds() == 3*3600

    # UI and migration features must physically exist in the build.
    root = Path(__file__).parent
    bot = (root/'bot.py').read_text()
    jobs = (root/'crm_plus/jobs.py').read_text()
    tz_handlers = (root/'handlers/timezone_handlers.py').read_text()
    ux = (root/'ux_final/handlers.py').read_text()
    for token in ['🌍 Сменить часовой пояс','timezone_handlers.handlers()','user_timezone.format_day_time_for_user']:
        assert token in bot, token
    for token in ['timezone_migration_job','student_day_brief_job(context, force=False)','user_timezone.user_tz']:
        assert token in jobs, token
    for token in ['Напишите разницу с московским временем','tz_confirm_custom','МСК']:
        assert token in tz_handlers, token
    assert "callback_data='tz_menu'" in ux

    print('TIMEZONE REGION SELFTEST: OK')
finally:
    try: os.remove(path)
    except FileNotFoundError: pass
