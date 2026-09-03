from pathlib import Path
import database
from crm_plus import schema, service

schema.initialize()
conn=database.connect()
cols={r['name'] for r in conn.execute('PRAGMA table_info(crm_student_messages)').fetchall()}
assert {'inbox_id','delivered_at','read_at'} <= cols, cols
for key in ('reception_enabled','reception_start','reception_end','reception_days'):
    assert service.get_setting(key) is not None, key
conn.close()

accepting,next_dt=service.reception_state()
assert isinstance(accepting,bool)
assert next_dt is not None

student_src=Path('handlers/student_message_handlers.py').read_text()
center_src=Path('handlers/message_center_handlers.py').read_text()
bot_src=Path('bot.py').read_text()
admin_src=Path('admin.py').read_text()
assert '↩️ Ответить преподавателю' in Path('crm_plus/messenger.py').read_text()
assert 'student_chat' in student_src
assert 'msg_settings' in center_src
assert 'Часы приёма' in center_src
assert 'student_more_menu' in bot_src
assert '⚙️ Настройки' in admin_src
print('MESSENGER UX SELFTEST: OK')
