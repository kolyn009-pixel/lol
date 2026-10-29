import unittest,json,tempfile,tarfile
from pathlib import Path
from unittest.mock import patch
import self_study_selftest as f
import build_self_study_bundle as bundle
import self_study_server_probe as probe

class Tests(unittest.TestCase):
 def test_bundle_is_allowlisted_and_has_no_database_credentials_or_git(self):
  files=bundle.files();self.assertIn('scripts/install_self_study.py',files);self.assertIn('handlers/self_study_family.py',files)
  self.assertFalse(any(name.endswith(('.db','.sqlite','.env')) or '/.git/' in name or 'node_modules/' in name or 'repo_git/' in name for name in files))
 def test_archive_extract_verify_and_tamper_detection(self):
  with tempfile.TemporaryDirectory() as tmp:
   archive=Path(tmp)/'source.tar.gz';bundle.build(archive,'a'*40)
   with tarfile.open(archive) as t:t.extractall(Path(tmp)/'unpacked',filter='data')
   root=Path(tmp)/'unpacked/adelia-family-languages';self.assertEqual('a'*40,bundle.verify(root)['revision'])
   (root/'web/self_study.js').write_text('changed')
   with self.assertRaises(RuntimeError):bundle.verify(root)
 def test_bundle_rejects_fake_revision(self):
  with self.assertRaises(ValueError):bundle.build(Path('unused.tar.gz'),'main')
 def test_probe_prints_only_selected_metadata(self):
  with patch.object(probe,'command',return_value='MainPID=0\nWorkingDirectory=/srv/live\nFragmentPath=/etc/systemd/system/test.service\n') as command:
   result=probe.inspect_service('test.service');self.assertEqual('/srv/live',result['working_directory']);self.assertEqual({'service','pid','working_directory','unit_file','has_language_installer'},set(result));self.assertNotIn('Environment',str(command.call_args))
if __name__=='__main__':unittest.main()
