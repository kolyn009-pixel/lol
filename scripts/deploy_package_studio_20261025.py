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

BASE = '9ac1c56bf383bf1ffc5a4c84d6850453dbd547eb'
PATCH = None
REPO = '/opt/tutorbot'
FILES = ['web/package_studio.css','web/package_studio.js','web/teacher.html']
NEW = {'web/package_studio.css','web/package_studio.js'}
OPTIONAL = set()
ASSETS = ['package_studio.css','package_studio.js']


def formula_delta(live, old, new):
    # Preserve the existing server-only empty-state buttons and their handlers.
    def surrounding(text):
        return ''.join(line for line in text.splitlines(True)
                       if not line.startswith('function cards(s){')
                       and not line.lstrip().startswith("box.querySelector('[data-fx-empty-new]')")).rstrip() + '\n'
    if surrounding(live) not in (surrounding(old), surrounding(new)):
        raise RuntimeError('Unrecognized formula implementation; no update')
    a, b = old.splitlines(True), new.splitlines(True)
    for tag, i, j, k, end in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        before, after = ''.join(a[i:j]), ''.join(b[k:end])
        if before.startswith('function cards(s){') and after.startswith('function cards(s){'):
            continue  # the live empty state already provides richer actions
        if not before.strip() and not after.strip():
            continue  # terminal blank-line differences carry no code changes
        if tag != 'replace':
            raise RuntimeError('Unexpected formula patch structure')
        if after and live.count(after) == 1:
            continue
        if not before or live.count(before) != 1:
            raise RuntimeError('Formula change does not match reviewed code')
        live = live.replace(before, after, 1)
    return live


def delta(live, old, new, label):
    if label == 'web/formula_explorer.js' and all(x in live for x in
            ('data-fx-empty-new', 'data-fx-empty-import', 'data-fx-empty-reset')):
        return formula_delta(live, old, new)

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
        url = '/app/' + asset + '?v=20261025-packages1'
        live, count = re.subn(pattern, lambda m: m['q'] + url + m['q'], live)
        if count > 1:
            raise RuntimeError('Duplicate asset reference: ' + asset)
        if not count:
            if live.count('</head>') != 1:
                raise RuntimeError('Missing unique HTML head')
            tag = ('<link rel="stylesheet" href="' + url + '">' if asset.endswith('.css')
                   else '<script defer src="' + url + '"></script>')
            live = live.replace('</head>', tag + '</head>', 1)
    # Place final overrides after every legacy stylesheet.
    pattern = r'<link[^>]+href="/app/package_studio\.css[^" ]*"[^>]*>'
    tags = re.findall(pattern, live)
    if len(tags) != 1:
        raise RuntimeError('Final stylesheet reference is ambiguous')
    live = re.sub(pattern, '', live).replace('</head>', tags[0] + '</head>', 1)
    return live


def atomic(path, data, stat):
    fd, name = tempfile.mkstemp(prefix='.adelia-layout-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if stat:
            os.chown(name, stat.st_uid, stat.st_gid)
        os.chmod(name, (stat.st_mode & 0o777) if stat else 0o644)
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
    global PATCH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install after preflight')
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.commit):
        raise SystemExit('A full pinned commit is required')
    PATCH = args.commit
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
            if path.is_symlink() or path.resolve() != path:
                raise RuntimeError('Unexpected symlink: ' + name)
            def git(ref):
                return subprocess.check_output(['git', '-C', REPO, 'show', ref + ':' + name])
            exists = path.is_file()
            if not exists and name not in NEW | OPTIONAL:
                raise RuntimeError('Missing required live file: ' + name)
            original[name] = path.read_bytes() if exists else None
            stats[name] = path.stat() if exists else None
            if name in NEW:
                candidate[name] = git(PATCH)
                if exists and original[name] != candidate[name]:
                    raise RuntimeError('Unknown existing override file: ' + name)
            elif not exists:
                candidate[name] = git(PATCH)
            elif name.endswith('.html'):
                candidate[name] = html_versions(original[name].decode()).encode()
            else:
                candidate[name] = delta(original[name].decode(), git(BASE).decode(),
                                        git(PATCH).decode(), name).encode()
            if exists and served(name) != original[name]:
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
            if ((root / name).read_bytes() if (root / name).exists() else None) != original[name]:
                raise RuntimeError('File changed during preflight: ' + name)
        backups = Path('/opt/tutorbot/backups')
        backups.mkdir(parents=True, exist_ok=True)
        backup = Path(tempfile.mkdtemp(prefix='package-studio-20261025-', dir=backups))
        os.chmod(backup, 0o700)
        for name in changed:
            dest = backup / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if original[name] is not None:
                shutil.copy2(root / name, dest)
        manifest = {'release': str(root), 'patch': PATCH, 'files': changed,
                    'before': {n: (hashlib.sha256(original[n]).hexdigest() if original[n] is not None else None) for n in changed}}
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
                if original[name] is None:
                    (root / name).unlink(missing_ok=True)
                else:
                    atomic(root / name, original[name], stats[name])
            print('UPDATE_FAILED; original files restored. Backup:', backup, flush=True)
            raise
        print('PACKAGE_STUDIO_OK')
        print('Backup:', backup)
        print('Only static files updated; no database changes or service restarts.')


if __name__ == '__main__':
    main()
