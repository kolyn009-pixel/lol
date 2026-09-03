
NETWORK ERROR HOTFIX:
- NetworkError/TimedOut are no longer reported to the administrator as critical failures.
- Transient Telegram/httpx read failures remain in systemd logs only.
- Real application/database errors are still reported as critical.
