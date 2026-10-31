"""Fill a completely empty formula handbook; preserve every existing formula."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile

FIELDS = {'subject','education_level','section','topic','title','formula_latex',
          'formula_plain','description','variables_json','conditions','units',
          'example','exam_note','grade_min','grade_max','course_min','course_max',
          'tags_json','sort_order'}


def populate(conn, items):
    columns = {x[1] for x in conn.execute('PRAGMA table_info(formula_book)')}
    if not FIELDS | {'created_at', 'updated_at', 'active'} <= columns:
        raise RuntimeError('Formula schema needs separate review; database unchanged')
    if not items:
        raise RuntimeError('Reviewed catalog is empty')
    prepared = []
    for item in items:
        if not all(item.get(k) for k in ('subject', 'title', 'formula_latex')):
            raise RuntimeError('Invalid catalog entry')
        row = {k: v for k, v in item.items() if k in FIELDS}
        for name in ('variables_json', 'tags_json'):
            value = row.get(name, [])
            if isinstance(value, str):
                value = json.loads(value)
            row[name] = json.dumps(value, ensure_ascii=False)
        row.update(active=1, created_at=datetime.now(timezone.utc).isoformat(),
                   updated_at=datetime.now(timezone.utc).isoformat())
        prepared.append(row)
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute('SELECT COUNT(*) FROM formula_book').fetchone()[0]:
            conn.rollback()
            return 0
        for row in prepared:
            names = list(row)
            conn.execute('INSERT INTO formula_book(' + ','.join(names) + ') VALUES (' +
                         ','.join('?' for _ in names) + ')', [row[k] for k in names])
        assert conn.execute('SELECT COUNT(*) FROM formula_book WHERE active=1').fetchone()[0] == len(prepared)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    return len(prepared)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    if os.geteuid() != 0 or not re.fullmatch('[0-9a-f]{40}', args.commit):
        raise SystemExit('Run as root with a full pinned commit')
    with open('/run/adelia-learning-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = Path('/opt/adelia-current').resolve(strict=True)
        if root.parent != Path('/opt/adelia-releases'):
            raise RuntimeError('Unexpected active release')
        pid = int(subprocess.check_output(['systemctl', 'show', 'tutorbot-web', '-p', 'MainPID', '--value']))
        if pid <= 0 or Path(f'/proc/{pid}/cwd').resolve() != root:
            raise RuntimeError('Unexpected web service release')
        env = dict(x.split(b'=', 1) for x in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in x)
        db = Path(os.fsdecode(env.get(b'ADELIA_DB_PATH', b'/opt/tutorbot/tutor.db'))).resolve(strict=True)
        if db != Path('/opt/tutorbot/tutor.db'):
            raise RuntimeError('Unexpected database path')
        catalog = json.loads(subprocess.check_output(['git', '-C', '/opt/tutorbot', 'show',
            args.commit + ':data/formulas/physics_handbook_20261015.json']))
        with sqlite3.connect('file:' + str(db) + '?mode=rw', uri=True, timeout=30) as conn:
            if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database integrity check failed')
            if conn.execute('SELECT COUNT(*) FROM formula_book').fetchone()[0]:
                print('FORMULAS_PRESERVED: handbook is not empty; no changes')
                return
            backups = Path('/opt/tutorbot/backups')
            backups.mkdir(exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix='formula-catalog-20261025-', dir=backups))
            os.chmod(folder, 0o700)
            saved = folder / 'database.sqlite'
            with sqlite3.connect(saved) as dest:
                conn.backup(dest)
            os.chmod(saved, 0o600)
            count = populate(conn, catalog['items'])
            print('FORMULAS_READY:', count, 'added')
            print('Database backup:', saved)


if __name__ == '__main__':
    main()
