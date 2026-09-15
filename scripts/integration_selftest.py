"""Read-only diagnostics for external lesson integrations.

This script is safe to run on production: it never creates/deletes events. It
checks local credentials and performs a lightweight read probe against Google
Calendar so an expired/revoked grant is detected before release. It also checks
that payment lifecycle hooks can be installed idempotently in-process.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_runtime_env():
    """Load missing runtime variables for diagnostics without printing secrets."""
    path = Path(os.getenv("ADELIA_ENV_FILE", "/etc/tutorbot/adelia.env"))
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


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


def _payment_runtime_probe():
    import database
    from core import payment_sync_runtime
    from final_features import jobs as final_jobs

    wired = getattr(final_jobs, "payment_sync_runtime", None) is payment_sync_runtime
    payment_sync_runtime.install()
    first = database.approve_payment
    markers = {
        "approve_payment": bool(getattr(database.approve_payment, "_adelia_payment_sync", False)),
        "approve_paid_booking_draft_payment": bool(getattr(database.approve_paid_booking_draft_payment, "_adelia_payment_sync", False)),
        "charge_reserved_lesson": bool(getattr(database.charge_reserved_lesson, "_adelia_payment_sync", False)),
    }
    payment_sync_runtime.install()
    idempotent = database.approve_payment is first
    return {
        "ok": wired and idempotent and all(markers.values()),
        "wired": wired,
        "idempotent": idempotent,
        "markers": markers,
    }


def main():
    _load_runtime_env()
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

    try:
        data["payment_runtime"] = _payment_runtime_probe()
    except Exception as exc:
        data["payment_runtime"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }

    print(json.dumps(data, ensure_ascii=False, indent=2))

    if not (data.get("payment_runtime") or {}).get("ok"):
        print("ERROR: payment integration runtime is not wired correctly", file=sys.stderr)
        return 5
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
