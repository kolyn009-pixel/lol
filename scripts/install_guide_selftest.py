"""Check narrow homepage edits and safe handling of the existing download symlink."""
from pathlib import Path
import tempfile,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from deploy_install_guide_20261022 import patch_homepage,atomic,restore

class Guide(unittest.TestCase):
 def test_homepage_links_are_idempotent_and_preserve_content(self):
  original='<html><main><div class="hero-actions"><a href="/start/">Записаться</a></div><p>Мой текст</p></main><footer><div>Бренд</div><div><a href="/app/">Кабинет</a></div></footer></html>'
  changed=patch_homepage(original);self.assertEqual(patch_homepage(changed),changed)
  self.assertEqual(changed.count('id="adelia-install-link"'),1);self.assertEqual(changed.count('id="adelia-install-footer"'),1)
  self.assertIn('<p>Мой текст</p>',changed);self.assertIn('<a href="/start/">Записаться</a>',changed)

 def test_unknown_page_is_rejected(self):
  with self.assertRaises(RuntimeError):patch_homepage('<html><body>Unexpected page</body></html>')

 def test_guide_replaces_only_index_symlink_and_can_restore_it(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);target=root/'old-index.html';target.write_text('old published page');index=root/'index.html';index.symlink_to('old-index.html');backup=root/'backup';backup.mkdir()
   rows=[{'path':str(index),'kind':'link','target':'old-index.html'}]
   atomic(index,b'new guide');self.assertFalse(index.is_symlink());self.assertEqual(index.read_text(),'new guide');self.assertEqual(target.read_text(),'old published page')
   restore(backup,rows);self.assertTrue(index.is_symlink());self.assertEqual(index.read_text(),'old published page')

 def test_all_platforms_and_instructions_are_present(self):
  text=(Path(__file__).resolve().parents[1]/'web/desktop_install.html').read_text()
  for name in ['Adelia-latest-windows-x64.exe','Adelia-latest-macos-arm64.dmg','Adelia-latest-macos-x64.dmg','id="windows"','id="mac"','id="phone"','/app/parent/','/teacher/']:
   self.assertIn(name,text)

if __name__=='__main__':unittest.main()
