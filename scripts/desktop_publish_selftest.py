"""Verify Finder ZIP handling, integrity checks and publication rollback."""
import hashlib,importlib.util,json,os,stat,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('publisher',Path(__file__).with_name('publish_desktop_site.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
    def archive(self,target,tamper=False,badname=False):
        alias,metadata=p.TARGETS[target];files={alias:b'installer bytes',metadata:b'updater metadata'}
        if target.startswith('macos-'):files['Adelia-0.3.0-beta.2-mac-'+target.split('-')[-1]+'.zip']=b'native ZIP bytes'
        manifest={'schema':2,'channel':'beta','version':p.VERSION,'git_sha':p.SHA,'files':[{'name':name,'size':len(data),'sha512':hashlib.sha512(data).hexdigest()} for name,data in files.items()]}
        if badname:manifest['files'][0]['name']='../outside.exe'
        release={k:manifest[k] for k in ['channel','version','git_sha']}
        file=self.folder/(target+'.zip');prefix='Finder folder/'
        with zipfile.ZipFile(file,'w') as z:
            z.writestr(prefix+'manifest.json',json.dumps(manifest));z.writestr(prefix+'release.json',json.dumps(release))
            z.writestr('__MACOSX/Finder folder/._manifest.json',b'Apple metadata')
            for name,data in files.items():z.writestr(prefix+name,b'changed content' if tamper and name==alias else data)
        return file
    def test_finder_folder_and_appledouble_are_supported(self):
        target='macos-arm64';dest=self.folder/'verified';p.extract_bundle(self.archive(target),dest,target)
        self.assertTrue((dest/p.TARGETS[target][0]).is_file());self.assertFalse((dest/'__MACOSX').exists());self.assertEqual(stat.S_IMODE(dest.stat().st_mode),0o755)
    def test_modified_file_is_rejected(self):
        with self.assertRaises(ValueError):p.extract_bundle(self.archive('win-x64',tamper=True),self.folder/'bad','win-x64')
    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):p.extract_bundle(self.archive('win-x64',badname=True),self.folder/'bad','win-x64')
        self.assertFalse((self.folder/'outside.exe').exists())
    def test_config_preserves_other_routes(self):
        old='server {\n    root /var/www/adeliatutor.ru;\n    location /api/ { proxy_pass http://127.0.0.1:8876; }\n}\n'
        new=p.nginx_config(old);self.assertIn('location ^~ /desktop-updates/',new);self.assertIn('proxy_pass http://127.0.0.1:8876',new)
        with self.assertRaises(ValueError):p.nginx_config(new)
    def test_failed_http_check_restores_config_and_all_links(self):
        root=self.folder/'public';root.mkdir();old=self.folder/'old';old.mkdir();(root/'beta').symlink_to(old)
        (root/'index.html').write_text('previous page');config=self.folder/'site.conf';original='server {\n    root /var/www/adeliatutor.ru;\n}\n';config.write_text(original)
        archives=[self.archive(target) for target in p.TARGETS]
        with patch.object(p,'SITE_ROOT',root),patch.object(p,'SITE_CONFIG',config),patch.object(p,'BACKUP_DIR',str(self.folder)),patch.object(p,'run'),patch.object(p,'verify_http',side_effect=RuntimeError('HTTP failure')):
            with self.assertRaises(RuntimeError):p.publish(archives)
        self.assertEqual(config.read_text(),original);self.assertEqual((root/'beta').resolve(),old);self.assertEqual((root/'index.html').read_text(),'previous page')
        self.assertFalse(os.path.lexists(root/'Adelia-latest-windows-x64.exe'))
    def test_success_publishes_three_platforms_with_readable_permissions(self):
        root=self.folder/'public';config=self.folder/'site.conf';config.write_text('server {\n    root /var/www/adeliatutor.ru;\n}\n')
        archives=[self.archive(target) for target in p.TARGETS]
        with patch.object(p,'SITE_ROOT',root),patch.object(p,'SITE_CONFIG',config),patch.object(p,'BACKUP_DIR',str(self.folder)),patch.object(p,'run'),patch.object(p,'verify_http'):p.publish(archives)
        for target,(alias,_) in p.TARGETS.items():
            self.assertTrue((root/alias).is_file());self.assertEqual((root/alias).read_bytes(),b'installer bytes');self.assertEqual(stat.S_IMODE((root/alias).stat().st_mode),0o644)
        self.assertIn(p.VERSION,(root/'index.html').read_text())

if __name__=='__main__':unittest.main()
