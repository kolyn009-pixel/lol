from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import install_teacher_auth_loop as setup


class Tests(unittest.TestCase):
    def fixture(self, folder):
        root=Path(folder)/'live';(root/'web').mkdir(parents=True)
        js=root/'web/teacher_dashboard_week.js';html=root/'web/teacher.html'
        js.write_text('// keep other improvements\n'+setup.OLD,encoding='utf-8')
        html.write_text('<script src="/app/sport.js"></script><script src="/app/teacher_dashboard_week.js?v=old"></script>',encoding='utf-8')
        return root,js,html

    def test_apply_and_repeat_preserve_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,js,html=self.fixture(tmp)
            setup.install(root,True)
            self.assertIn('// keep other improvements',js.read_text(encoding='utf-8'))
            self.assertIn(setup.NEW,js.read_text(encoding='utf-8'))
            self.assertIn('sport.js',html.read_text(encoding='utf-8'))
            self.assertIn('authfix1',html.read_text(encoding='utf-8'))
            self.assertTrue(list(Path(tmp).glob('teacher-auth-loop-*/manifest.json')))
            after=[js.read_bytes(),html.read_bytes()];setup.install(root,True)
            self.assertEqual(after,[js.read_bytes(),html.read_bytes()])

    def test_check_and_unknown_version_do_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,js,html=self.fixture(tmp);before=[js.read_bytes(),html.read_bytes()]
            setup.install(root)
            self.assertEqual(before,[js.read_bytes(),html.read_bytes()])
            js.write_text('other dashboard',encoding='utf-8')
            with self.assertRaises(RuntimeError):setup.install(root,True)
            self.assertEqual(before[1],html.read_bytes())

    def test_second_write_failure_restores_first_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,js,html=self.fixture(tmp);before=[js.read_bytes(),html.read_bytes()]
            original=setup.atomic
            def write(path,data,mode):
                if path==html:raise RuntimeError('simulated write error')
                original(path,data,mode)
            with patch.object(setup,'atomic',side_effect=write):
                with self.assertRaisesRegex(RuntimeError,'simulated'):setup.install(root,True)
            self.assertEqual(before,[js.read_bytes(),html.read_bytes()])


if __name__=='__main__':unittest.main(verbosity=2)
