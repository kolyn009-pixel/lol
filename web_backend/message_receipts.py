"""Normalize server event timestamps before sending them to browsers."""
from datetime import datetime, timezone


def utc_timestamp(value):
    if not value:
        return None
    try:
        stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        # Legacy now_iso() values were generated in the server's local timezone,
        # never in the student's selected region. New read timestamps carry UTC.
        return stamp.astimezone(timezone.utc).isoformat(timespec='seconds')
    except (TypeError,ValueError,OverflowError):
        return None


def receipt(row):
    read=utc_timestamp(row.get('read_at'))
    status=str(row.get('status') or 'SENT').upper()
    return {'status':'READ' if read else ('DELIVERED' if status=='DELIVERED' else 'FAILED' if status=='FAILED' else 'SENT'),
            'read_at':read,'created_at':utc_timestamp(row.get('created_at'))}
