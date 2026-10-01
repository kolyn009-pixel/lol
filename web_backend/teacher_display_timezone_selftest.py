"""Isolated regression for the display-only teacher preference."""
import sqlite3
import sys
import types
from unittest.mock import patch

sys.modules.setdefault('database', types.SimpleNamespace(connect=lambda: None, get_setting=lambda *_: 'Europe/Samara'))
from web_backend import teacher_display_timezone as clock


class Connection:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row

    def execute(self, *args):
        return self.db.execute(*args)

    def commit(self):
        return self.db.commit()

    def close(self):
        pass


conn = Connection()
with patch.object(clock, 'connect', return_value=conn), patch.object(clock, 'get_setting', return_value='Europe/Samara'):
    assert clock.preference(101)['timezone'] == {'zone': 'Europe/Samara', 'selected': False, 'schedule_zone': 'Europe/Samara'}
    assert clock.set_preference(101, 'Europe/Moscow')['timezone']['selected']
    assert clock.preference(101)['timezone']['zone'] == 'Europe/Moscow'
    assert clock.preference(102)['timezone']['zone'] == 'Europe/Samara'
    assert clock.set_preference(101, 'schedule')['timezone']['selected'] is False
    with patch.object(clock, 'get_setting', return_value='Europe/Moscow'):
        assert clock.preference(101)['timezone']['zone'] == 'Europe/Moscow'
        clock.set_preference(101, 'Europe/Samara')
        assert clock.preference(101)['timezone']['zone'] == 'Europe/Samara'
        assert clock.set_preference(101, 'schedule')['timezone']['zone'] == 'Europe/Moscow'
    assert clock.get_setting('bot_timezone', 'Europe/Samara') == 'Europe/Samara'
    try:
        clock.set_preference(101, 'Not/AZone')
    except ValueError:
        pass
    else:
        raise AssertionError('invalid timezone accepted')
    sample = {'week': {'timezone': 'Europe/Samara'},
              'today_lessons': [{'start_time': '2026-09-27T20:00:00', 'end_time': '2026-09-27T21:00:00'}],
              'week_lessons': [], 'next_lessons': []}
    with patch.dict(sys.modules, {'web_backend.teacher_portal': types.SimpleNamespace(dashboard=lambda: sample)}):
        enriched = clock.dashboard_with_instants()
    assert enriched['today_lessons'][0]['start_at'] == '2026-09-27T20:00:00+04:00'
    assert enriched['today_lessons'][0]['end_at'] == '2026-09-27T21:00:00+04:00'
    assert 'start_at' not in sample['today_lessons'][0]
print('TEACHER_DISPLAY_TIMEZONE_BACKEND=PASS')
