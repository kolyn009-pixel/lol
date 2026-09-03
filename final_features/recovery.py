from __future__ import annotations
from pathlib import Path
from datetime import datetime
import shutil,sqlite3,os
import database
from core import backup_manager


def health():
    out=[]
    try:
        c=database.connect(); ok=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close(); out.append(('SQLite',ok=='ok',ok))
    except Exception as e: out.append(('SQLite',False,repr(e)))
    db=Path(database.DB_PATH if hasattr(database,'DB_PATH') else 'tutor.db'); out.append(('DB file',db.exists() and db.stat().st_size>0,f'{db.stat().st_size if db.exists() else 0} bytes'))
    try:
        backups=sorted(Path(backup_manager.BACKUP_DIR).glob('*.db'),key=lambda p:p.stat().st_mtime,reverse=True) if hasattr(backup_manager,'BACKUP_DIR') else []
        out.append(('Backup',bool(backups),backups[0].name if backups else 'нет'))
    except Exception as e: out.append(('Backup',False,repr(e)))
    return out
