"""Non-destructive Stage 13 receipt archive preflight.
Run: python -m web_backend.stage13_archive_selftest
Use --online to also validate Yandex Disk credentials with a metadata request.
"""
from __future__ import annotations
import sys
from database import connect
from web_backend import receipt_cloud_archive as archive

def run(online=False):
 checks=[]
 def check(name,ok,detail=''):checks.append((name,bool(ok),str(detail or '')))
 archive.ensure_table();conn=connect();cols={str(r['name']) for r in conn.execute('PRAGMA table_info(receipt_cloud_archives)').fetchall()};indexes={str(r['name']) for r in conn.execute('PRAGMA index_list(receipt_cloud_archives)').fetchall()};conn.close()
 for col in {'receipt_id','remote_path','sha256','size_bytes','status','attempts','archived_at','verified_at','updated_at'}:check('column '+col,col in cols)
 check('status index','idx_receipt_cloud_archive_status' in indexes)
 check('archive root absolute',archive.ARCHIVE_ROOT.startswith('/'),archive.ARCHIVE_ROOT)
 check('receipt size bounded',0<archive.MAX_RECEIPT_BYTES<=25*1024*1024,archive.MAX_RECEIPT_BYTES)
 check('retry attempts bounded',1<=archive.MAX_ATTEMPTS<=20,archive.MAX_ATTEMPTS)
 check('queue stats readable',all(k in archive.queue_stats() for k in ('receipts_total','untracked','pending','retry','archived','failed')))
 check('Yandex token configured',archive.configured())
 if online and archive.configured():
  try:
   info=archive._disk_request('GET','/',None);check('Yandex Disk API reachable',isinstance(info,dict) and bool(info))
  except Exception as exc:check('Yandex Disk API reachable',False,type(exc).__name__+': '+str(exc)[:80])
 elif online:check('Yandex Disk API reachable',False,'token missing')
 failed=[]
 for name,ok,detail in checks:
  print(('OK   ' if ok else 'FAIL ')+name+((' - '+detail) if detail else ''))
  if not ok:failed.append(name)
 print('queue',archive.queue_stats())
 if failed:raise SystemExit('Stage 13 archive selftest failed: '+', '.join(failed))
 print(f'Stage 13 archive selftest passed: {len(checks)} checks')
if __name__=='__main__':run('--online' in sys.argv[1:])
