"""Controlled one-shot backfill for receipts that predate Stage 13.

Default mode is dry-run and performs no cloud upload:
  python -m web_backend.receipt_archive_backfill
Explicit execution:
  python -m web_backend.receipt_archive_backfill --apply --limit 25
Repeat in small batches until untracked reaches zero.
"""
from __future__ import annotations
import argparse
from database import connect
from web_backend import receipt_cloud_archive as archive

def candidates(limit=25):
 archive.ensure_table();limit=max(1,min(int(limit),100));conn=connect();rows=conn.execute("SELECT r.id,r.user_id,r.payment_id,r.source_platform,r.created_at FROM receipts r LEFT JOIN receipt_cloud_archives a ON a.receipt_id=r.id WHERE a.receipt_id IS NULL ORDER BY r.id LIMIT ?",(limit,)).fetchall();conn.close();return [dict(r) for r in rows]
def main():
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--limit',type=int,default=25);args=p.parse_args();rows=candidates(args.limit);print({'mode':'apply' if args.apply else 'dry-run','candidates':len(rows),'queue':archive.queue_stats()})
 if not args.apply:
  for r in rows:print({'receipt_id':r['id'],'payment_id':r['payment_id'],'source':r['source_platform'],'created_at':r['created_at']})
  print('Dry-run only. Re-run with --apply to archive this bounded batch.');return
 if not archive.configured():raise SystemExit('YANDEX_DISK_OAUTH_TOKEN is required')
 ok=retry=failed=0
 for r in rows:
  result=archive.archive_receipt(int(r['id']));status=result.get('status');ok+=status=='ok';retry+=status=='retry';failed+=status=='failed';print({'receipt_id':r['id'],'status':status})
 print({'processed':len(rows),'ok':ok,'retry':retry,'failed':failed,'queue':archive.queue_stats()})
if __name__=='__main__':main()
