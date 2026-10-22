import importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('release_tool',Path(__file__).with_name('publish_adelia_release.py'));r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def bundles(self,versions=None):
  for index,(target,(alias,_)) in enumerate(r.p.TARGETS.items()):
   m={'schema':2,'channel':'beta','version':(versions or ['0.3.0-beta.5']*3)[index],'git_sha':'a'*40,'files':[{'name':alias}]}
   with zipfile.ZipFile(self.root/(target+'.zip'),'w') as z:z.writestr('manifest.json',json.dumps(m))
 def test_identify(self):
  self.bundles();identity,archives=r.inspect_bundles(self.root);self.assertEqual(identity,('0.3.0-beta.5','a'*40));self.assertEqual(len(archives),3)
 def test_mixed_rejected(self):
  self.bundles(['0.3.0-beta.4','0.3.0-beta.5','0.3.0-beta.5'])
  with self.assertRaises(ValueError):r.inspect_bundles(self.root)
 def test_missing_rejected(self):
  self.bundles();next(self.root.glob('*.zip')).unlink()
  with self.assertRaises(ValueError):r.inspect_bundles(self.root)
 def test_semver(self):
  values=['0.3.0-beta.4','0.3.0-beta.5','0.3.0-beta.10','0.3.0-rc.1','0.3.0','0.4.0-beta.1']
  self.assertEqual(sorted(values,key=r.semver),values)
 def test_downgrade_rejected(self):
  self.bundles();live=self.root/'site/beta/win-x64';live.mkdir(parents=True);(live/'release.json').write_text(json.dumps({'version':'0.4.0-beta.1','git_sha':'b'*40}))
  with patch.object(r.p,'SITE_ROOT',self.root/'site'),self.assertRaises(ValueError):r.validate(self.root)
 def test_same_version_other_commit_rejected(self):
  self.bundles();live=self.root/'site/beta/win-x64';live.mkdir(parents=True);(live/'release.json').write_text(json.dumps({'version':'0.3.0-beta.5','git_sha':'b'*40}))
  with patch.object(r.p,'SITE_ROOT',self.root/'site'),self.assertRaises(ValueError):r.validate(self.root)
if __name__=='__main__':unittest.main()
