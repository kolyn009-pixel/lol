"""Guarded two-line hotfix of the running Telegram release. No DB changes."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def patch(source):
    for field in ('day_s', 'start_s'):
        before = f"_,_,lid_s,{field}=d.split('|',3)"
        after = f"_,lid_s,{field}=d.split('|',2)"
        if source.count(before) == 1 and after not in source:
            source = source.replace(before, after)
        elif source.count(after) == 1 and before not in source:
            pass
        else:
            raise RuntimeError(f'Unexpected callback source ({field}); no files changed')
    compile(source, 'final_features/handlers.py', 'exec')
    return source


def install():
    if os.geteuid() != 0:
        raise SystemExit('Run on the Ubuntu server as root')
    with open('/run/adelia-learning-deploy.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        release = Path('/opt/adelia-current').resolve(strict=True)
        if release.parent != Path('/opt/adelia-releases'):
            raise RuntimeError('Unexpected active release')
        pid = int(subprocess.check_output(['systemctl', 'show', 'tutorbot', '-p', 'MainPID', '--value'], text=True).strip())
        if pid < 1 or Path(f'/proc/{pid}/cwd').resolve() != release:
            raise RuntimeError('Bot is not running from the active release')
        target = release / 'final_features/handlers.py'
        if target.is_symlink() or target.resolve().parent != release / 'final_features':
            raise RuntimeError('Unexpected handler path')
        original = target.read_bytes()
        updated = patch(original.decode()).encode()
        if original == updated:
            print('RESCHEDULE_HOTFIX_ALREADY_INSTALLED')
            return
        backup = Path(tempfile.mkdtemp(prefix='reschedule-20261021-', dir='/opt/tutorbot/backups'))
        os.chmod(backup, 0o700)
        saved = backup / 'handlers.py'
        shutil.copy2(target, saved)

        def replace(data):
            fd, name = tempfile.mkstemp(prefix='.handlers-hotfix-', dir=target.parent)
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(data)
                    out.flush()
                    os.fsync(out.fileno())
                shutil.copystat(target, name)
                st = target.stat()
                os.chown(name, st.st_uid, st.st_gid)
                os.replace(name, target)
            finally:
                if os.path.exists(name):
                    os.unlink(name)

        try:
            replace(updated)
            subprocess.run(['systemctl', 'restart', 'tutorbot'], check=True, timeout=60)
            # A restart returning successfully alone does not prove startup.
            for _ in range(10):
                time.sleep(1)
                subprocess.run(['systemctl', 'is-active', '--quiet', 'tutorbot'], check=True)
                new_pid = int(subprocess.check_output(['systemctl', 'show', 'tutorbot', '-p', 'MainPID', '--value'], text=True).strip())
                if new_pid <= 0 or Path(f'/proc/{new_pid}/cwd').resolve() != release:
                    raise RuntimeError('Unexpected bot process after restart')
        except BaseException:
            replace(original)
            subprocess.run(['systemctl', 'restart', 'tutorbot'], timeout=60, check=False)
            print('HOTFIX_FAILED; original handler restored. Backup:', saved)
            raise
        print('RESCHEDULE_HOTFIX_OK')
        print('Release:', release)
        print('Backup:', saved)


if __name__ == '__main__':
    install()
