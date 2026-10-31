"""Apply only the reviewed teacher layout delta to the active static web files."""
import argparse
import difflib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

BASE = 'e4a1d07993253aaa7ae0a05b6009b2adf20c7867'
PATCH = '7c6a5544800504d1a4cacf0481a704e3041de4db'
REPO = '/opt/tutorbot'
FILES = ['web/teacher_dashboard_week.css', 'web/teacher_clean_runtime.js',
         'web/teacher_receipt_review_tools.css', 'web/teacher.html']
ASSETS = ['teacher_dashboard_week.css', 'teacher_clean_runtime.js',
          'teacher_receipt_review_tools.css']


def delta(live, old, new, label):
    if live == new:
        return live
    groups = list(difflib.SequenceMatcher(None, old.splitlines(True),
                  new.splitlines(True), autojunk=False).get_grouped_opcodes(2))
    a, b = old.splitlines(True), new.splitlines(True)
    for group in groups:
        before = ''.join(a[group[0][1]:group[-1][2]])
        after = ''.join(b[group[0][3]:group[-1][4]])
        if after and live.count(after) == 1:
            continue
        if not before or live.count(before) != 1:
            raise RuntimeError('Code differs from reviewed version; no update: ' + label)
        live = live.replace(before, after, 1)
    return live


def html_versions(live):
    for asset in ASSETS:
        pattern = r'(?P<q>[\"\'])/app/' + re.escape(asset) + r'(?:\?[^\"\']*)?(?P=q)'
        live, count = re.subn(pattern, lambda m: m['q'] + '/app/' + asset +
                             '?v=20261025-layout1' + m['q'], live)
        if count != 1:
            raise RuntimeError('Expected exactly one asset reference: ' + asset)
    return live


def atomic(path, data, stat):
    fd, name = tempfile.mkstemp(prefix='.adelia-layout-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chown(name, stat.st_uid, stat.st_gid)
        os.chmod(name, stat.st_mode & 0o777)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def served(relative):
    return subprocess.check_output([
        'curl', '--resolve', 'adeliatutor.ru:443:127.0.0.1', '--noproxy', '*',
        '--max-time', '12', '-fsS', '-H', 'Cache-Control: no-cache',
        'https://adeliatutor.ru/app/' + relative.removeprefix('web/') +
        '?layout_check=20261025'], timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install after preflight')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo or as root in the server SSH session.')
    with open('/run/adelia-learning-deploy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = Path('/opt/adelia-current').resolve(strict=True)
        if root.parent != Path('/opt/adelia-releases'):
            raise RuntimeError('Unexpected active release')
        pid = int(subprocess.check_output(['systemctl', 'show', 'tutorbot-web',
                  '-p', 'MainPID', '--value'], text=True).strip())
        if pid <= 0 or Path(f'/proc/{pid}/cwd').resolve() != root:
            raise RuntimeError('Web process does not use the active release')
        original, candidate, stats = {}, {}, {}
        for name in FILES:
            path = root / name
            if not path.is_file() or path.is_symlink() or path.resolve() != path:
                raise RuntimeError('Missing file or unexpected symlink: ' + name)
            original[name], stats[name] = path.read_bytes(), path.stat()
            live = original[name].decode('utf-8')
            if name.endswith('.html'):
                candidate[name] = html_versions(live).encode('utf-8')
            else:
                def git(ref):
                    return subprocess.check_output(['git', '-C', REPO, 'show',
                                                    ref + ':' + name]).decode('utf-8')
                candidate[name] = delta(live, git(BASE), git(PATCH), name).encode('utf-8')
            if served(name) != original[name]:
                raise RuntimeError('Nginx serves a different file: ' + name)
        print('PREFLIGHT_OK', root, flush=True)
        changed = [name for name in FILES if candidate[name] != original[name]]
        if not changed:
            print('ALREADY_INSTALLED')
            return
        if not args.apply:
            print('Ready to update:', ', '.join(changed))
            print('Run with --apply to install.')
            return
        if Path('/opt/adelia-current').resolve() != root:
            raise RuntimeError('Release changed during preflight')
        for name in FILES:
            if (root / name).read_bytes() != original[name]:
                raise RuntimeError('File changed during preflight: ' + name)
        backups = Path('/opt/tutorbot/backups')
        backups.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='teacher-layout-20261025-', dir=backups))
        os.chmod(backup, 0o700)
        for name in changed:
            dest = backup / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / name, dest)
        manifest = {'release': str(root), 'patch': PATCH, 'files': changed,
                    'before': {n: hashlib.sha256(original[n]).hexdigest() for n in changed}}
        (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        written = []
        try:
            for name in changed:
                atomic(root / name, candidate[name], stats[name])
                written.append(name)
            for name in FILES:
                if served(name) != candidate[name]:
                    raise RuntimeError('Updated asset verification failed: ' + name)
        except BaseException:
            for name in reversed(written):
                atomic(root / name, original[name], stats[name])
            print('UPDATE_FAILED; original files restored. Backup:', backup, flush=True)
            raise
        print('TEACHER_LAYOUT_OK')
        print('Backup:', backup)
        print('Only static files updated; no database changes or service restarts.')


if __name__ == '__main__':
    main()
