"""Exercise the production callback branches without Telegram/network/DB writes."""
import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'final_features/handlers.py'


class CallbackTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, payload, admin=True):
        tree = ast.parse(SOURCE.read_text())
        callback = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'callbacks')
        callback.args.args[0].annotation = callback.args.args[1].annotation = None
        events = []
        lesson = dict(id=46, user_id=22, duration_minutes=60, start_time='2026-10-22T10:00:00')

        async def answer(*args, **kw):
            events.append(('answer', args, kw))

        async def edit(text, **kw):
            events.append(('edit', text, kw))

        async def refresh(context, ids):
            events.append(('refresh', ids))

        async def notify(context, uid, text):
            events.append(('notify', uid))

        def slots(day, duration, lid):
            events.append(('slots', day.isoformat(), duration, lid))
            return [datetime.fromisoformat('2026-10-22T12:30:00+03:00')]

        def move(lid, start, end):
            events.append(('move', lid, start, end))
            return 99

        bot = SimpleNamespace(get_free_slots=slots, TIMEZONE=timezone.utc)
        old = sys.modules.get('bot')
        sys.modules['bot'] = bot
        ns = dict(_admin=lambda uid: admin, database=SimpleNamespace(get_lesson=lambda lid: lesson, free_reschedule_lesson=move),
                  datetime=datetime, InlineKeyboardButton=lambda text, **kw: (text, kw), InlineKeyboardMarkup=lambda rows: rows,
                  _refresh_calendar_and_reminders=refresh, _notify_family=notify, student_menu=lambda uid: [],
                  _dt_text=lambda value: value)
        try:
            exec(compile(ast.Module(body=[callback], type_ignores=[]), str(SOURCE), 'exec'), ns)
            q = SimpleNamespace(data=payload, from_user=SimpleNamespace(id=913246612), answer=answer, edit_message_text=edit)
            await ns['callbacks'](SimpleNamespace(callback_query=q), SimpleNamespace())
        finally:
            if old is None:
                sys.modules.pop('bot', None)
            else:
                sys.modules['bot'] = old
        return events

    async def test_reported_day_buttons(self):
        for lid, day in [(37, '2026-10-21'), (136, '2026-10-28'), (46, '2026-10-22')]:
            events = await self.exercise(f'ff_swap_day|{lid}|{day}')
            self.assertIn(('slots', day, 60, lid), events)
            self.assertFalse(any(x[0] == 'move' for x in events))
            rendered = repr(events)
            self.assertIn(f'ff_swap_free|{lid}|2026-10-22T12:30:00+03:00', rendered)

    async def test_free_button_keeps_offset_and_duration(self):
        events = await self.exercise('ff_swap_free|46|2026-10-22T12:30:00+03:00')
        self.assertIn(('move', 46, '2026-10-22T12:30:00+03:00', '2026-10-22T13:30:00+03:00'), events)
        self.assertIn(('refresh', [99]), events)
        self.assertIn(('notify', 22), events)

    async def test_student_cannot_use_teacher_buttons(self):
        for payload in ['ff_swap_day|46|2026-10-22', 'ff_swap_free|46|2026-10-22T12:30:00+03:00']:
            events = await self.exercise(payload, admin=False)
            self.assertFalse(any(x[0] in {'move', 'slots', 'notify'} for x in events))


if __name__ == '__main__':
    unittest.main()
