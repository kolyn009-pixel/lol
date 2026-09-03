from __future__ import annotations
from pathlib import Path
import re

SUSPICIOUS = re.compile(r'USER_ID|PROGRAM_ID|MOCK_ID|LESSON_ID|TARGET_SCORE|TEST_SCORE|PRIMARY_SCORE|MINUTES_PER_WEEK|/mockassign|/mockresult|/examplan')
VISIBLE_HINT = re.compile(r'InlineKeyboardButton|reply_text|edit_message_text|send_message|text\s*=')

def run(base_dir=None):
    base=Path(base_dir or Path(__file__).resolve().parents[1]); hits=[]
    for folder in ('final_features','crm_plus','handlers','admin.py','students_admin.py','bot.py'):
        p=base/folder
        files=[p] if p.is_file() else list(p.rglob('*.py')) if p.exists() else []
        for f in files:
            if '__pycache__' in f.parts: continue
            try: lines=f.read_text(errors='ignore').splitlines()
            except Exception: continue
            for n,line in enumerate(lines,1):
                if SUSPICIOUS.search(line) and VISIBLE_HINT.search(line):
                    hits.append((str(f.relative_to(base)),n,line.strip()[:180]))
    return hits
