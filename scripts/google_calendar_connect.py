"""One-time Google Calendar OAuth setup.

Run manually on a trusted machine/server terminal. The production bot never
opens OAuth by itself. This requests offline access and forces the consent
screen so Google returns a refresh token that can be reused after restarts.
"""
from __future__ import annotations

from integrations.google_calendar import CREDENTIALS_PATH, SCOPES, TOKEN_PATH, _atomic_write


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit("Install google-auth-oauthlib and google-api-python-client first") from exc

    if not CREDENTIALS_PATH.exists():
        raise SystemExit(f"Missing OAuth client file: {CREDENTIALS_PATH}")

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )
    if not creds.refresh_token:
        raise SystemExit("Google did not return a refresh token; revoke old grant and reconnect")
    _atomic_write(TOKEN_PATH, creds.to_json())
    print("Google Calendar connected")
    print("Token:", TOKEN_PATH)
    print("Refresh token: yes")


if __name__ == "__main__":
    main()
