"""Patch dashboard authorization recovery, preserving the live release."""
import argparse
import json
import os
from pathlib import Path
import re
import tempfile

OLD = "if(e.message==='AUTH'){if(typeof window.show==='function')return window.show('dashboard');location.reload();return}"
NEW = "if(e.message==='AUTH'){lastSignature='';if(typeof window.login==='function'){window.login();return}title.textContent='Вход';app.innerHTML='<section class=\"error\"><b>Для продолжения войдите в кабинет преподавателя.</b><p>Форма входа ещё загружается. Обновите страницу.</p></section>';return}"


def patched(source):
    if NEW in source:
        return source
    if source.count(OLD) != 1:
        raise RuntimeError('Dashboard differs from reviewed version; no files changed')
    return source.replace(OLD, NEW, 1)


def atomic(path, data, mode):
    fd, name = tempfile.mkstemp(prefix='.teacher-auth-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.chmod(name, mode); os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def install(root, apply=False):
    root = root.resolve()
    js = root / 'web/teacher_dashboard_week.js'
    html = root / 'web/teacher.html'
    if not js.is_file() or not html.is_file():
        raise RuntimeError('Existing teacher deployment not found')
    if not js.resolve().is_relative_to(root) or not html.resolve().is_relative_to(root):
        raise RuntimeError('Target escapes selected release')
    before = {p: p.read_bytes() for p in [js, html]}
    modes = {p: p.stat().st_mode & 0o777 for p in before}
    updated, count = re.subn(r'(/app/teacher_dashboard_week\.js)(?:\?[^\"\x27]*)?',
                            lambda m: m[1] + '?v=20261111-authfix1', before[html].decode('utf-8'))
    if count != 1:
        raise RuntimeError('Dashboard asset missing or duplicated; no files changed')
    plan = {js: patched(before[js].decode('utf-8')).encode(), html: updated.encode()}
    changed = {p: b for p, b in plan.items() if b != before[p]}
    print(json.dumps({'mode': 'apply' if apply else 'check', 'changed_files': [str(p) for p in changed]}, indent=2))
    if not apply or not changed:
        if apply: print('TEACHER_AUTH_LOOP_ALREADY_FIXED')
        return
    backup = Path(tempfile.mkdtemp(prefix='teacher-auth-loop-', dir=root.parent))
    os.chmod(backup, 0o700)
    for p in changed: (backup / p.name).write_bytes(before[p])
    (backup / 'manifest.json').write_text(json.dumps({'root': str(root), 'files': [str(p) for p in changed]}, indent=2))
    print('BACKUP: ' + str(backup), flush=True)
    written = []
    try:
        for p, data in changed.items():
            if p.read_bytes() != before[p]: raise RuntimeError('Concurrent change: ' + str(p))
            atomic(p, data, modes[p]); written.append(p)
    except Exception:
        for p in reversed(written):
            if p.read_bytes() != changed[p]: raise RuntimeError('Rollback conflict; inspect ' + str(backup))
            atomic(p, before[p], modes[p])
        raise
    print('TEACHER_AUTH_LOOP_FIXED_OK')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('/opt/adelia-current'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    install(args.root, args.apply)
