import os, shutil
from datetime import datetime
import database
from .schema import ensure_schema

BACKUP_DIR=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'backups')

def create_backup(reason='manual', actor_id=None):
    ensure_schema(); os.makedirs(BACKUP_DIR,exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); path=os.path.join(BACKUP_DIR,f'tutor_{stamp}.db')
    src=database.connect(); dst=__import__('sqlite3').connect(path); src.backup(dst); dst.close(); src.close()
    size=os.path.getsize(path); conn=database.connect(); conn.execute("INSERT INTO system_backups(file_name,file_path,reason,created_at,created_by,size_bytes,status) VALUES(?,?,?,?,?,?,'OK')",(os.path.basename(path),path,reason,datetime.now().isoformat(timespec='seconds'),actor_id,size)); conn.commit(); conn.close(); return path

def prune(keep=14):
    os.makedirs(BACKUP_DIR,exist_ok=True); files=sorted([os.path.join(BACKUP_DIR,x) for x in os.listdir(BACKUP_DIR) if x.endswith('.db')],key=os.path.getmtime,reverse=True)
    for p in files[int(keep):]:
        try: os.remove(p)
        except OSError: pass
