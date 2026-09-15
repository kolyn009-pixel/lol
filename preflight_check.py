from pathlib import Path
import compileall
import py_compile
import sys

ROOT = Path(__file__).resolve().parent
required = [
    'bot.py', 'admin.py', 'database.py', 'channel_admin.py', 'schedule_admin.py', 'schedule_parity_selftest.py',
    'handlers/musthave_admin.py', 'handlers/musthave_jobs.py', 'handlers/adelia_content.py',
    'handlers/calendar_runtime.py',