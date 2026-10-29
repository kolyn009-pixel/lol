from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import contextlib
import io
import json
from unittest.mock import patch
import install_self_study as install


class Tests(unittest.TestCase):
    def setUp(self):
        capture=contextlib.redirect_stdout(io.StringIO());capture.__enter__();self.addCleanup(capture.__exit__,None,None,None)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'live';self.root.mkdir()
        (self.root/'web_backend').mkdir();(self.root/'web').mkdir()
        text=(install.SOURCE/'web_backend/api_v7.py').read_text()
        text=text.replace(install.IMPORT+'\n','').replace('Handler(SelfStudyMixin, ','Handler(')
        text=text.replace(install.GET+'\n','').replace(install.POST+'\n','')
        (self.root/'web_backend/api_v7.py').write_text(text)
        (self.root/'web/teacher.html').write_text('<html><head></head><body>Existing teacher tools</body></html>')
        self.db=self.root/'tutor.db';conn=sqlite3.connect(self.db)
        conn.execute('CREATE TABLE preserved (value TEXT)');conn.execute("INSERT INTO preserved VALUES('original')");conn.commit();conn.close()

    def run_install(self,apply=True):
        return install.install(self.root,self.db,'tutorbot-web','http://127.0.0.1:8876',apply)

    def test_dry_run_does_not_write(self):
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_install(False)
        self.assertEqual(before,{p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    @patch.object(install,'restart')
    @patch.object(install,'health')
    def test_install_backup_idempotence_and_rollback_preserve_data(self,health,restart):
        old=(self.root/'web_backend/api_v7.py').read_bytes()
        backup=self.run_install();self.assertTrue((backup/'database.sqlite').exists())
        self.assertIn('Existing teacher tools',(self.root/'web/teacher.html').read_text())
        self.assertIsNone(self.run_install())
        conn=sqlite3.connect(self.db);conn.execute("INSERT INTO preserved VALUES('after installation')");conn.commit();conn.close()
        install.restore(self.root,backup)
        self.assertEqual(old,(self.root/'web_backend/api_v7.py').read_bytes())
        self.assertFalse((self.root/'web_backend/self_study.py').exists())
        conn=sqlite3.connect(self.db);self.assertEqual(2,conn.execute('SELECT COUNT(*) FROM preserved').fetchone()[0]);conn.close()

    @patch.object(install,'restart')
    @patch.object(install,'health',side_effect=RuntimeError('health failed'))
    def test_failed_health_restores_code(self,health,restart):
        old=(self.root/'web_backend/api_v7.py').read_bytes()
        with self.assertRaisesRegex(RuntimeError,'health failed'):self.run_install()
        self.assertEqual(old,(self.root/'web_backend/api_v7.py').read_bytes())
        self.assertFalse((self.root/'web/self_study.js').exists())

    @patch.object(install,'restart')
    @patch.object(install,'health')
    def test_upgrade_managed_previous_version_preserves_work_files(self,health,restart):
        self.run_install()
        old=b'/* previously installed language UI */'
        (self.root/'web/self_study_workshop.js').write_bytes(old)
        marker=json.loads((self.root/install.MARKER).read_text())
        marker['hashes']['web/self_study_workshop.js']=install.digest(old)
        (self.root/install.MARKER).write_text(json.dumps(marker))
        (self.root/'web/work-untouched.js').write_text('existing work')
        backup=self.run_install()
        self.assertEqual(old,(backup/'files/web/self_study_workshop.js').read_bytes())
        self.assertEqual('existing work',(self.root/'web/work-untouched.js').read_text())
        self.assertEqual((install.SOURCE/'web/self_study_workshop.js').read_bytes(),(self.root/'web/self_study_workshop.js').read_bytes())
        self.assertTrue((self.root/'web_backend/self_study_tutor.py').exists())
        self.assertTrue((self.root/'web_backend/self_study_series.py').exists())

    def test_unreviewed_api_is_rejected_before_writes(self):
        (self.root/'web_backend/api_v7.py').write_text('class Other: pass')
        with self.assertRaisesRegex(RuntimeError,'differs'):self.run_install()
        self.assertFalse((self.root/'web/self_study.js').exists())

    def test_unknown_existing_module_is_not_overwritten(self):
        (self.root/'web_backend/self_study.py').write_text('custom = True')
        with self.assertRaisesRegex(RuntimeError,'outside this installer'):self.run_install()

    @patch.object(install,'restart')
    @patch.object(install,'health')
    def test_rollback_rejects_subsequent_changes(self,health,restart):
        backup=self.run_install();(self.root/'web/self_study.js').write_text('later work')
        with self.assertRaisesRegex(RuntimeError,'Rollback conflict'):install.restore(self.root,backup)

    def test_missing_database_and_external_health_rejected(self):
        with self.assertRaises(RuntimeError):install.install(self.root,self.db,'tutorbot-web','https://outside.example',False)
        with self.assertRaises(RuntimeError):install.install(self.root,self.root/'missing.db','tutorbot-web','http://127.0.0.1:8876',False)


if __name__=='__main__':unittest.main()
