"""Read-only diagnostics for external lesson integrations.

This script is safe to run on production: it never creates/deletes events. It
checks local credentials and performs a lightweight read probe against Google
Calendar so an expired/revoked grant is detected before release.
"""
from __future__ import annotations

import json
import sys


def _google_probe():
    from integrations.google_calendar import CALENDAR_ID, _service

    service = _service()
    data = service.calendars().get(calendarId=CALENDAR_ID).execute()
    return {
        "ok": True,
        "id": data.get("id"),
        "summary": data.get("summary"),
        "time_zone": data.get("timeZone"),
    }


def main():
    from integrations.lesson_sync import status

    data = status()
    google = data.get("google") or {}
    telemost = data.get("telemost") or {}

    if google.get("connected"):
        try:
            google["remote_probe"] = _google_probe()
        except Exception as exc:
            google["remote_probe"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
    data["google"] = google

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if google.get("connected") and not google.get("refresh_token"):
        print("ERROR: Google is connected without a refresh token", file=sys.stderr)
        return 2
    if not google.get("connected"):
        print("ERROR: Google Calendar is not connected", file=sys.stderr)
        return 2
    if not (google.get("remote_probe") or {}).get("ok"):
        print("ERROR: Google credentials exist but Calendar API probe failed", file=sys.stderr)
        return 4
    if telemost.get("enabled") and not telemost.get("configured"):
        print("ERROR: Telemost is enabled but token is missing", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
