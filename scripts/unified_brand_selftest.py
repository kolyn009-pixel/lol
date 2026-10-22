import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

path=Path(__file__).with_name('unify_brand_20261022.py')
spec=importlib.util.spec_from_file_location('branding',path);brand=importlib.util.module_from_spec(spec);spec.loader.exec_module(brand)

class BrandTests(unittest.TestCase):
 def test_desktop_download_page_with_implicit_head(self):
  source='<!doctype html><html lang="ru"><meta charset="utf-8"><title>Скачать Аделию</title><style>main{padding:32px}</style><main><a href="/desktop-updates/app.dmg">Скачать</a></main></html>'
  updated=brand.transform_html(source)
  self.assertIn(brand.ICON_TAGS,updated)
  self.assertIn('/desktop-updates/app.dmg',updated)
  self.assertEqual(updated,brand.transform_html(updated))

 def test_live_download_symlink_is_preserved(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)/'site';active=root/'desktop-updates/releases/beta/current';active.mkdir(parents=True)
   page=active/'index.html';page.write_text('<html><title>Download</title><main>App</main></html>')
   live=root/'desktop-updates/beta';live.symlink_to(active,target_is_directory=True)
   alias=root/'desktop-updates/index.html';alias.symlink_to('beta/index.html')
   target=brand.resolve_site_file(alias,(root,))
   self.assertEqual(target,page)
   target.write_text(brand.transform_html(target.read_text()))
   self.assertTrue(alias.is_symlink());self.assertTrue(live.is_symlink())
   self.assertIn(brand.ICON_TAGS,alias.read_text())

 def test_foreign_site_symlink_is_refused(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)/'adelia';root.mkdir();other=Path(directory)/'other.html';other.write_text('Other site')
   alias=root/'index.html';alias.symlink_to(other)
   with self.assertRaises(RuntimeError):brand.resolve_site_file(alias,(root,))
   self.assertEqual(other.read_text(),'Other site');self.assertTrue(alias.is_symlink())

 def test_all_icon_relations_replaced_with_one_family(self):
  source='''<!doctype html><html><head><meta charset="utf-8"><link rel="shortcut icon" href="/old.ico"><link rel="apple-touch-icon-precomposed" href="/old.png"><link rel="stylesheet" href="/app.css"><script>const text='<link rel="icon" href="do-not-touch">';</script></head><body><img src="/adelia-apple-touch-icon-180.png?v=old" alt="Аделия"><img src="/assets/nikolay-adelia-hero.webp"></body></html>'''
  result=brand.transform_html(source)
  self.assertIn(brand.ICON_TAGS,result)
  self.assertNotIn('/old.ico',result);self.assertNotIn('/old.png',result)
  self.assertIn("const text='<link rel=\"icon\" href=\"do-not-touch\">'",result)
  self.assertIn('/app.css',result);self.assertIn('/assets/nikolay-adelia-hero.webp',result)
  self.assertIn('src="'+brand.icon_url(180)+'"',result)
  self.assertEqual(result,brand.transform_html(result))

 def test_page_without_icon_gets_the_same_family(self):
  source='<html><head><title>Документы</title></head><body>Условия</body></html>'
  self.assertIn(brand.ICON_TAGS,brand.transform_html(source))

 def test_teacher_boot_inline_code_is_preserved(self):
  source=(Path(__file__).resolve().parents[1]/'web/teacher.html').read_text()
  before=source[source.index('<script data-adelia-boot-guard'):source.index('</script>')+9]
  result=brand.transform_html(source)
  self.assertIn(before,result)

 def test_role_manifest_identity_preserved(self):
  old={'id':'/teacher/','scope':'/teacher/','start_url':'/teacher/','name':'Аделия — преподаватель','shortcuts':[{'name':'Сегодня','url':'/teacher/#dashboard'}],'icons':[{'src':'old.png'}]}
  updated=json.loads(brand.transform_manifest(json.dumps(old)))
  for key in ('id','scope','start_url','name','shortcuts'):self.assertEqual(updated[key],old[key])
  self.assertTrue(all('/app/assets/icons/adelia-mark-' in x['src'] for x in updated['icons']))

 def test_ico_keeps_exact_png_pixels(self):
  png=b'\x89PNG\r\n\x1a\n'+b'\x00\x00\x00\x0dIHDR'+struct.pack('>II',32,32)+b'fixture'
  ico=brand.favicon(png)
  self.assertEqual(ico[22:],png)
  self.assertEqual(struct.unpack('<HHH',ico[:6]),(0,1,1))

if __name__=='__main__':unittest.main()
