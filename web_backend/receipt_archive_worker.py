"""Small isolated worker for Stage 13 receipt cloud archiving.

Run as its own systemd service. It never serves HTTP and never participates in
payment acceptance, so cloud outages cannot slow the site or TutorBot.
"""
from __future__ import annotations
import os
import signal
import time
from web_backend.receipt_cloud_archive import archive_pending,configured,queue_stats,verify_archived

POLL_SECONDS=max(30,min(int(os.getenv('ADELIA_RECEIPT_ARCHIVE_POLL','60')),3600))
BATCH_SIZE=max(1,min(int(os.getenv('ADELIA_RECEIPT_ARCHIVE_BATCH','10')),50))
VERIFY_INTERVAL=max(3600,min(int(os.getenv('ADELIA_RECEIPT_VERIFY_INTERVAL','86400')),7*86400))
VERIFY_BATCH=max(1,min(int(os.getenv('ADELIA_RECEIPT_VERIFY_BATCH','10')),50))
_running=True

def _stop(*_):
 global _running;_running=False

def main():
 if not configured():raise SystemExit('YANDEX_DISK_OAUTH_TOKEN is required for receipt archive worker')
 signal.signal(signal.SIGTERM,_stop);signal.signal(signal.SIGINT,_stop)
 print('[receipt-archive] started',queue_stats(),flush=True);next_verify=time.monotonic()+60
 while _running:
  try:
   results=archive_pending(BATCH_SIZE)
   if results:print('[receipt-archive] batch',{'processed':len(results),**queue_stats()},flush=True)
   if time.monotonic()>=next_verify:
    verified=verify_archived(VERIFY_BATCH);bad=sum(1 for x in verified if x.get('status') not in {'ok','not_archived'})
    if verified:print('[receipt-archive] verify',{'checked':len(verified),'issues':bad},flush=True)
    next_verify=time.monotonic()+VERIFY_INTERVAL
  except Exception as exc:
   print('[receipt-archive] error',type(exc).__name__,str(exc)[:120],flush=True)
  for _ in range(POLL_SECONDS):
   if not _running:break
   time.sleep(1)
 print('[receipt-archive] stopped',flush=True)

if __name__=='__main__':main()
