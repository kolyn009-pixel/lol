"""Verify stable publication, beta bridge and coordinated rollback with tiny fixtures."""
import hashlib,importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SHA='a'*40
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  spec=importlib.util.spec_from_file_location('pub',ROOT/'scripts/publish_uploaded_desktop.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
  self.m.WEB_ROOT=self.root/'site';self.m.WEB_ROOT.mkdir();self.m.BACKUPS=self.root/'backups'
  self.upload=self.root/'upload';self.upload.mkdir();self.stage=self.root/'stage';self.stage.mkdir();checks=[]
  for channel in ('stable','beta'):
   p=self.m.WEB_ROOT/channel;p.mkdir();(p/'old-marker').write_text(channel)
  for target,alias in self.m.TARGETS.items():
   (self.m.WEB_ROOT/alias).write_text('old')
   files={alias:b'installer',self.m.metadata(target,'stable'):b'version: 0.3.0\n'}
   meta={'schema':2,'version':'0.3.0','git_sha':SHA,'channel':'stable','files':[{'name':n,'size':len(v),'sha512':hashlib.sha512(v).hexdigest()} for n,v in files.items()]}
   with zipfile.ZipFile(self.upload/(target+'.zip'),'w') as z:
    for n,v in files.items():z.writestr(n,v)
    for n in ('manifest.json','release.json'):z.writestr(n,json.dumps(meta))
   checks.append(hashlib.sha256((self.upload/(target+'.zip')).read_bytes()).hexdigest()+'  '+target+'.zip')
  (self.upload/'SHA256SUMS').write_text('\n'.join(checks))
 def tearDown(self):self.tmp.cleanup()
 def http(self,url,head=False):
  p=self.m.WEB_ROOT/url.split('/desktop-updates/',1)[1]
  if head:return ('Content-Type: application/octet-stream\r\nContent-Length: '+str(p.stat().st_size)+'\r\n').encode()
  return p.read_bytes()
 def test_stable_and_old_beta_clients_receive_same_binary(self):
  self.m.verify_upload(self.upload,self.stage,'0.3.0',SHA,'stable');self.m.get=self.http;self.m.publish(self.stage,'0.3.0',SHA,'stable',True)
  for target,alias in self.m.TARGETS.items():
   stable=self.m.WEB_ROOT/'stable'/target;beta=self.m.WEB_ROOT/'beta'/target
   self.assertEqual((stable/alias).read_bytes(),(beta/alias).read_bytes());self.assertEqual((beta/self.m.metadata(target,'beta')).read_bytes(),(stable/self.m.metadata(target,'stable')).read_bytes());self.assertEqual(json.loads((beta/'manifest.json').read_text())['channel'],'beta')
 def test_http_failure_restores_both_legacy_feeds_and_aliases(self):
  self.m.verify_upload(self.upload,self.stage,'0.3.0',SHA,'stable')
  def fail(url,head=False):
   if '/beta/macos-x64/' in url:raise RuntimeError('simulated HTTP failure')
   return self.http(url,head)
  self.m.get=fail
  with self.assertRaisesRegex(RuntimeError,'simulated'):self.m.publish(self.stage,'0.3.0',SHA,'stable',True)
  for channel in ('stable','beta'):self.assertEqual((self.m.WEB_ROOT/channel/'old-marker').read_text(),channel)
  for alias in self.m.TARGETS.values():self.assertEqual((self.m.WEB_ROOT/alias).read_text(),'old')
 def test_wrong_source_identity_refused(self):
  with self.assertRaisesRegex(RuntimeError,'identity'):self.m.verify_upload(self.upload,self.stage,'0.3.0','b'*40,'stable')
  self.assertEqual((self.m.WEB_ROOT/'stable'/'old-marker').read_text(),'stable')
if __name__=='__main__':unittest.main()
