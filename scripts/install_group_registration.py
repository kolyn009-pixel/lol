"""Install only group recruitment; preserve other additions to the live release.

Default is read-only. --apply backs up code and SQLite, restarts only the web
service and rolls code back on failed checks. SQLite is never restored automatically.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SOURCE = Path(__file__).resolve().parents[1]
IMPORT = 'from web_backend.public_group_registration_api import PublicGroupRegistrationMixin'
REDIRECT = '<script>if(new URLSearchParams(location.search).has("group_id")){location.replace("/start/group.html"+location.search+location.hash)}</script>'
STAMP = '20261111-group-registration'
NEW_FILES = ['web_backend/public_group_registration.py',
             'web_backend/public_group_registration_api.py',
             'web/start/group.html', 'web/start/group.css', 'web/start/group.js']
PREVIOUS_HASHES = {
    'web_backend/public_group_registration.py': {'a38a8e1a9a8116c63bfb35e902424e554082c82cfe1e70c8f2a704c5f59e4592'},
    'web/start/group.html': {'427300ff46bd8f9d72d32e41112906c0edb70b6541aee668b94659b798d7663b'},
    'web/start/group.js': {'acd409be3f90fe9fac557e99d2cc976c89cd436a8bdae551852c35ea4ad3f970'},
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, before, after):
    if after in text:
        return text
    if text.count(before) != 1:
        raise RuntimeError('Integration anchor missing or ambiguous; no files changed')
    return text.replace(before, after, 1)


def patch_api(text):
    if IMPORT in text:
        if not re.search(r'^class Handler\(PublicGroupRegistrationMixin, ', text, re.M):
            raise RuntimeError('Partial group API integration')
        return text
    text = replace_once(text, 'class Handler(', IMPORT + '\n\nclass Handler(PublicGroupRegistrationMixin, ')
    ast.parse(text)
    return text


def patch_requests(text):
    if 'group_registrations=public_group_registration.list_for_teacher(limit)' in text:
        return text
    text = replace_once(text, 'def list_all(limit=100):',
        'def list_all(limit=100):\n from web_backend import public_group_registration\n group_registrations=public_group_registration.list_for_teacher(limit)')
    return replace_once(text, "return {'counts':{'trial':", "return {'group_registrations':group_registrations,'counts':{'group':len(group_registrations),'trial':")


def patch_teacher_html(text):
    pattern = r'(/app/teacher_request_center\.js)(?:\?[^\"\x27]*)?'
    text, n = re.subn(pattern, lambda m: m[1] + '?v=' + STAMP, text)
    if n != 1:
        raise RuntimeError('Teacher request-center asset missing or duplicated')
    return text


def patch_landing(text):
    old = '/start/?group_id=${encodeURIComponent(x.id)}'
    new = '/start/group.html?group_id=${encodeURIComponent(x.id)}'
    return replace_once(text, old, new)


def patch_start(text):
    if REDIRECT in text:
        return text
    return replace_once(text, '</head>', REDIRECT + '</head>')


def patch_home(text):
    return re.sub(r'(\blanding\.js)(?:\?[^\"\x27<>\s]*)?', lambda m: m[1] + '?v=' + STAMP, text)


def merge_request_js(current):
    before = (SOURCE / 'scripts/group_registration_request_center_base.js').read_text(encoding='utf-8')
    after = (SOURCE / 'web/teacher_request_center.js').read_text(encoding='utf-8')
    # Patch only the three reviewed group UI functions. Keep the live API error
    # helper, translated subjects, accessibility labels and any other functions.
    current = current.replace("'&quot'", "'&quot;'")
    for prefix in ['function css(', 'async function render(', 'function wire(']:
        old = [line for line in before.splitlines() if line.startswith(prefix)]
        new = [line for line in after.splitlines() if line.startswith(prefix)]
        if len(old) != 1 or len(new) != 1:
            raise RuntimeError('Unexpected request-center source layout')
        current = replace_once(current, old[0] + '\n', new[0] + '\n')
    added = [line for line in after.splitlines() if line.startswith('function groupRegistration(')]
    if len(added) != 1:
        raise RuntimeError('Group card function missing')
    if added[0] not in current:
        current = replace_once(current, 'async function render(){', added[0] + '\nasync function render(){')
    return current


def candidates(root, static):
    result = {}
    def put(path, data):
        path = path.resolve()
        if not any(path.is_relative_to(base) for base in [root, static]):
            raise RuntimeError('Target escapes configured directories')
        if path in result and result[path] != data:
            raise RuntimeError('Conflicting static/application targets')
        result[path] = data
    for name in NEW_FILES:
        data = (SOURCE / name).read_bytes()
        target = root / name
        if target.exists() and target.read_bytes() != data and digest(target.read_bytes()) not in PREVIOUS_HASHES.get(name, set()):
            raise RuntimeError('Existing new module differs: ' + name)
        put(target, data)
    patches = {'web_backend/api_v7.py': patch_api,
               'web_backend/teacher_request_center.py': patch_requests,
               'web/teacher.html': patch_teacher_html,
               'web/teacher_request_center.js': merge_request_js,
               'web/landing.js': patch_landing,
               'web/start/index.html': patch_start}
    for name, fn in patches.items():
        put(root / name, fn((root / name).read_text(encoding='utf-8')).encode())
    for name in ['start/group.html', 'start/group.css', 'start/group.js']:
        target = static / name
        data = (SOURCE / 'web' / name).read_bytes()
        if target.exists() and target.read_bytes() != data and digest(target.read_bytes()) not in PREVIOUS_HASHES.get('web/' + name, set()):
            raise RuntimeError('Existing group page differs: ' + str(target))
        put(target, data)
    for name, fn in [('start/index.html', patch_start), ('landing.js', patch_landing), ('index.html', patch_home)]:
        target = static / name
        if not target.is_file():
            raise RuntimeError('Static website file missing: ' + str(target))
        put(target, fn(target.read_text(encoding='utf-8')).encode())
    for path, data in result.items():
        if path.suffix == '.py':
            ast.parse(data, filename=str(path))
        if path.suffix == '.js' and shutil.which('node'):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'check.js'; p.write_bytes(data)
                subprocess.run(['node', '--check', str(p)], check=True, capture_output=True, timeout=20)
    return result


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.group-update-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_get(url):
    with urlopen(url, timeout=4) as response:
        return json.load(response)


def health(base, new=False):
    if json_get(base + '/api/health').get('ok') is not True:
        raise RuntimeError('Web health check failed')
    if not new:
        return
    try:
        json_get(base + '/api/public/group-registration?group_id=0')
        raise RuntimeError('Invalid group unexpectedly available')
    except HTTPError as exc:
        if exc.code != 404 or json.load(exc).get('error') != 'group_not_available':
            raise RuntimeError('Group API check failed')
    # An invalid group id makes this write-free even if old code is still live.
    invalid = {'group_id': 0, 'name': 'Validation check', 'grade': 11,
               'contact': 'not a contact', 'timezone': 'Europe/Moscow', 'consent': True}
    validation_request = Request(base + '/api/public/group-registration',
        data=json.dumps(invalid).encode(), headers={'Host': 'adeliatutor.ru',
        'Origin': 'https://adeliatutor.ru', 'Content-Type': 'application/json'})
    try:
        urlopen(validation_request, timeout=4)
        raise RuntimeError('Invalid contact unexpectedly accepted')
    except HTTPError as exc:
        if exc.code != 400 or json.load(exc).get('error') != 'invalid_contact':
            raise RuntimeError('Contact validation is not active')
    request = Request(base + '/api/teacher/group-registration/review', data=b'{}',
                      headers={'Host': 'adeliatutor.ru', 'Origin': 'https://adeliatutor.ru', 'Content-Type': 'application/json'})
    try:
        urlopen(request, timeout=4)
        raise RuntimeError('Teacher endpoint allowed an anonymous request')
    except HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError('Teacher authentication check failed: ' + str(exc.code))


def restart(service, base, new=False):
    subprocess.run(['systemctl', 'restart', service], check=True, timeout=45)
    for attempt in range(12):
        try:
            health(base, new)
            return
        except (OSError, ValueError, RuntimeError):
            if attempt == 11:
                raise
            time.sleep(1)


def install(root, static, database, service, base, apply=False):
    root, static, database = root.resolve(), static.resolve(), database.resolve()
    if root == SOURCE or not root.is_dir() or not static.is_dir():
        raise RuntimeError('Source and existing deployment directories must differ')
    if not re.fullmatch(r'[a-zA-Z0-9_.@-]+', service) or not re.fullmatch(r'http://127\.0\.0\.1:\d+', base):
        raise RuntimeError('Invalid service or loopback health URL')
    if not database.is_file():
        raise RuntimeError('Existing database not found')
    cwd = subprocess.check_output(['systemctl', 'show', service, '-p', 'WorkingDirectory', '--value'], text=True).strip()
    if Path(cwd).resolve() != root:
        raise RuntimeError('Service uses a different deployment directory')
    plan = candidates(root, static)
    before = {p: (p.read_bytes() if p.exists() else None) for p in plan}
    changed = {p: data for p, data in plan.items() if before[p] != data}
    print(json.dumps({'mode': 'apply' if apply else 'check', 'changed_files': [str(p) for p in changed]}, indent=2), flush=True)
    health(base)
    if not apply or not changed:
        if apply:
            health(base, True)
            print('GROUP_REGISTRATION_ALREADY_INSTALLED', flush=True)
        return
    backup = Path(tempfile.mkdtemp(prefix='group-registration-', dir=root.parent))
    os.chmod(backup, 0o700)
    modes = {p: (p.stat().st_mode & 0o777 if p.exists() else 0o644) for p in changed}
    manifest = {'release': str(root), 'files': []}
    for index, p in enumerate(changed):
        saved = str(index) + '.original'
        if before[p] is not None:
            (backup / saved).write_bytes(before[p])
        manifest['files'].append({'target': str(p), 'backup': saved if before[p] is not None else None,
                                  'mode': modes[p], 'installed_sha256': digest(changed[p])})
    src = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(backup / 'database.sqlite')
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('BACKUP: ' + str(backup), flush=True)
    written = []
    try:
        for p, data in changed.items():
            if (p.read_bytes() if p.exists() else None) != before[p]:
                raise RuntimeError('Concurrent file change: ' + str(p))
            atomic(p, data, modes[p]); written.append(p)
        restart(service, base, True)
        with urlopen('https://adeliatutor.ru/start/group.html?v=' + STAMP, timeout=15) as response:
            if b'id="groupForm"' not in response.read():
                raise RuntimeError('Public group page is not served by nginx')
    except Exception:
        for p in reversed(written):
            if p.read_bytes() != changed[p]:
                raise RuntimeError('Rollback conflict; inspect backup: ' + str(backup))
            if before[p] is None:
                p.unlink()
            else:
                atomic(p, before[p], modes[p])
        restart(service, base)
        print('CODE_ROLLED_BACK; database left intact; backup: ' + str(backup), flush=True)
        raise
    print('GROUP_REGISTRATION_INSTALLED_OK', flush=True)
    print('https://adeliatutor.ru/start/group.html?group_id=1', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/opt/adelia-current'))
    parser.add_argument('--static-root', type=Path, default=Path('/var/www/adeliatutor.ru'))
    parser.add_argument('--database', type=Path, default=Path('/opt/tutorbot/tutor.db'))
    parser.add_argument('--service', default='tutorbot-web.service')
    parser.add_argument('--health-url', default='http://127.0.0.1:8876')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    install(args.root, args.static_root, args.database, args.service, args.health_url, args.apply)


if __name__ == '__main__':
    main()
