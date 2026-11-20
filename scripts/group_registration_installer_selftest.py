import contextlib
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_group_registration as setup


class InstallerTests(unittest.TestCase):
    def fixture(self, folder):
        root, static = Path(folder) / 'live', Path(folder) / 'static'
        for name in ['web_backend', 'web/start']:
            (root / name).mkdir(parents=True)
        (static / 'start').mkdir(parents=True)
        (root / 'web_backend/api_v7.py').write_text(
            'class Handler(SportMixin, AcquisitionMixin, StudentAccountsMixin, SelfStudyMixin, Base):\n    pass\n')
        (root / 'web_backend/teacher_request_center.py').write_text(
            "def list_all(limit=100):\n return {'counts':{'trial':1},'custom':True}\n")
        (root / 'web/teacher.html').write_text(
            '<script src="/app/sport.js"></script><script src="/app/teacher_request_center.js?v=old"></script>')
        baseline = (setup.SOURCE / 'scripts/group_registration_request_center_base.js').read_text(encoding='utf-8')
        (root / 'web/teacher_request_center.js').write_text(baseline, encoding='utf-8')
        for path in [root / 'web/landing.js', static / 'landing.js']:
            path.write_text('const url=`/start/?group_id=${encodeURIComponent(x.id)}`;\n// newer marketing code\n')
        for path in [root / 'web/start/index.html', static / 'start/index.html']:
            path.write_text('<head></head><body>Current booking flow</body>')
        (static / 'index.html').write_text('<script src="/landing.js?v=old"></script>')
        db = Path(folder) / 'live.sqlite'
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute('CREATE TABLE live_data(value TEXT)')
            conn.execute("INSERT INTO live_data VALUES('preserve')")
            conn.commit()
        return root, static, db

    def test_preserves_latest_mixins_and_is_idempotent(self):
        text = 'class Handler(SportMixin, AcquisitionMixin, StudentAccountsMixin, SelfStudyMixin, Base):\n    pass\n'
        updated = setup.patch_api(text)
        self.assertIn('PublicGroupRegistrationMixin, SportMixin, AcquisitionMixin, StudentAccountsMixin, SelfStudyMixin', updated)
        self.assertEqual(updated, setup.patch_api(updated))
        with self.assertRaises(RuntimeError):
            setup.patch_api('class SomethingElse: pass')

    def test_all_targets_and_static_assets_then_second_plan_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, static, db = self.fixture(tmp)
            plan = setup.candidates(root, static)
            self.assertIn(static / 'start/group.html', plan)
            self.assertIn(b'newer marketing code', plan[root / 'web/landing.js'])
            self.assertIn(b'sport.js', plan[root / 'web/teacher.html'])
            self.assertIn(b"'custom':True", plan[root / 'web_backend/teacher_request_center.py'])
            for p, data in plan.items():
                p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
            self.assertEqual(plan, setup.candidates(root, static))

    def test_merge_conflict_fails_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, static, db = self.fixture(tmp)
            target = root / 'web/teacher_request_center.js'
            target.write_text('new incompatible request center')
            before = {p:p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
            with patch.object(setup.subprocess, 'run') as run:
                run.return_value.returncode = 1
                with self.assertRaisesRegex(RuntimeError, 'anchor missing or ambiguous'):
                    setup.candidates(root, static)
            self.assertEqual(before, {p:p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()})

    def test_live_friendly_errors_survive_group_ui_update(self):
        baseline = (setup.SOURCE / 'scripts/group_registration_request_center_base.js').read_text(encoding='utf-8')
        current = baseline.replace("'&quot'", "'&quot;'").replace(
            "new Error(j.error||j.detail||'Ошибка')", "new Error('Friendly slot_unavailable message')") + '\n'
        with patch.object(setup.subprocess, 'run', side_effect=AssertionError('No Git merge needed')):
            merged = setup.merge_request_js(current)
        self.assertEqual(current.splitlines()[1], merged.splitlines()[1])
        self.assertIn('function groupRegistration(x)', merged)
        expected = (setup.SOURCE / 'web/teacher_request_center.js').read_text(encoding='utf-8').splitlines()
        actual = merged.rstrip('\n').splitlines()
        self.assertEqual(expected[:1] + expected[2:], actual[:1] + actual[2:])
        with patch.object(setup.subprocess, 'run', side_effect=AssertionError('No Git merge needed')):
            self.assertEqual(merged, setup.merge_request_js(merged))

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, static, db = self.fixture(tmp)
            before = {p:p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()}
            with patch.object(setup.subprocess, 'check_output', return_value=str(root)), patch.object(setup, 'health'), contextlib.redirect_stdout(io.StringIO()):
                setup.install(root, static, db, 'tutorbot-web.service', 'http://127.0.0.1:8876')
            self.assertEqual(before, {p:p.read_bytes() for p in Path(tmp).rglob('*') if p.is_file()})

    def test_reviewed_previous_modules_upgrade_but_unknown_changes_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, static, db = self.fixture(tmp)
            target = root / 'web_backend/public_group_registration.py'
            original = b'# reviewed previous version\n'
            target.write_bytes(original)
            hashes = {**setup.PREVIOUS_HASHES, 'web_backend/public_group_registration.py': {setup.digest(original)}}
            with patch.object(setup, 'PREVIOUS_HASHES', hashes):
                self.assertIn(target, setup.candidates(root, static))
                target.write_bytes(b'# different change\n')
                with self.assertRaisesRegex(RuntimeError, 'Existing new module differs'):
                    setup.candidates(root, static)

    def test_failed_restart_restores_files_and_preserves_live_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, static, db = self.fixture(tmp)
            before = {p:p.read_bytes() for base in [root, static] for p in base.rglob('*') if p.is_file()}
            def restart(service, base, new=False):
                if new:
                    with contextlib.closing(sqlite3.connect(db)) as conn:
                        conn.execute("INSERT INTO live_data VALUES('arrived during update')")
                        conn.commit()
                    raise RuntimeError('simulated failed health check')
            with patch.object(setup.subprocess, 'check_output', return_value=str(root)), patch.object(setup, 'health'), patch.object(setup, 'restart', side_effect=restart), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'simulated failed'):
                    setup.install(root, static, db, 'tutorbot-web.service', 'http://127.0.0.1:8876', True)
            self.assertEqual(before, {p:p.read_bytes() for base in [root, static] for p in base.rglob('*') if p.is_file()})
            with contextlib.closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM live_data').fetchone()[0], 2)
            self.assertTrue(list(Path(tmp).glob('group-registration-*/database.sqlite')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
