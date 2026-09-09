"""Read-only diagnostics for external lesson integrations."""
from __future__ import annotations

import json
import sys


def main():
    from integrations.lesson_sync import status

    data = status()
    print(json.dumps(data, ensure_ascii=False, indent=2))

    google = data.get("google") or {}
    if google.get("connected") and not google.get("refresh_token"):
        print("ERROR: Google is connected without a refresh token", file=sys.stderr)
        return 2
    if not google.get("connected"):
        print("INFO: Google Calendar needs one-time connection", file=sys.stderr)
    telemost = data.get("telemost") or {}
    if telemost.get("enabled") and not telemost.get("configured"):
        print("ERROR: Telemost is enabled but token is missing", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
