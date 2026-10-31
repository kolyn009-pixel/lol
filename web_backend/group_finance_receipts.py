"""Authenticated, size-limited receipt reader. Never fetch arbitrary URLs."""
from pathlib import Path
import database
ROOTS=(Path('/opt/tutorbot/data/receipts'),Path('/opt/tutorbot/data/receipt_files'),Path('/opt/tutorbot/data/receipt_view_cache'))
MAX=20*1024*1024

def mime(data):
    if data.startswith(b'%PDF-'):return 'application/pdf'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP':return 'image/webp'
    raise ValueError('receipt_format_not_supported')

def read(group_id,payment_id):
    c=database.connect()
    try:p=c.execute('SELECT user_id,receipt_ref FROM group_payments WHERE id=? AND group_id=?',(int(payment_id),int(group_id))).fetchone()
    finally:c.close()
    if not p:raise ValueError('group_payment_not_found')
    ref=str(p['receipt_ref'] or '').strip()
    if ref.startswith('receipt:') and ref[8:].isdigit():
        from web_backend import receipt_cloud_archive as archive
        receipt=archive._receipt(int(ref[8:]))
        if not receipt or int(receipt['user_id'])!=int(p['user_id']):raise ValueError('receipt_not_found')
        data=archive._receipt_bytes(receipt)
    else:
        # Only persisted local receipt references are supported by this adapter.
        # Opaque Telegram/VK references need their source metadata; do not guess.
        path=Path(ref).resolve() if ref.startswith('/') else None
        if not path or not any(path.is_relative_to(root.resolve()) for root in ROOTS):raise ValueError('receipt_source_not_supported')
        if not path.is_file() or path.stat().st_size>MAX:raise ValueError('receipt_not_found_or_too_large')
        data=path.read_bytes()
    if not data or len(data)>MAX:raise ValueError('receipt_not_found_or_too_large')
    return data,mime(data)
