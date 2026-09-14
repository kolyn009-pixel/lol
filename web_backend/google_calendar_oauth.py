"""Teacher-only Google Calendar OAuth reconnect helpers.

The running calendar integration continues to use integrations.google_calendar.
This module only creates a browser OAuth flow for reconnecting the production
calendar grant through adeliatutor.ru. OAuth client secrets and tokens remain
server-side.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

from integrations import google_calendar
from web_backend import otp_secret

DEFAULT_REDIRECT_URI = "https://adeliatutor.ru/api/integrations/google/callback"
STATE_TTL_SECONDS = 10 * 60


def redirect_uri():
    return str(
        os.environ.get("GOOGLE_CALENDAR_REDIRECT_URI")
        or DEFAULT_REDIRECT_URI
    ).strip()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    raw = str(value or "")
    raw += "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw.encode("ascii"))


def _sign(payload: bytes) -> str:
    return _b64encode(
        hmac.new(
            otp_secret._key(),
            payload,
            hashlib.sha256,
        ).digest()
    )


def make_state(teacher_id, now=None):
    payload = json.dumps(
        {
            "teacher_id": int(teacher_id),
            "iat": int(now if now is not None else time.time()),
            "nonce": secrets.token_urlsafe(18),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = _b64encode(payload)
    return encoded + "." + _sign(payload)


def verify_state(state, now=None):
    try:
        encoded, signature = str(state or "").split(".", 1)
        payload = _b64decode(encoded)
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError("invalid_oauth_state")
        data = json.loads(payload.decode("utf-8"))
        issued = int(data["iat"])
        current = int(now if now is not None else time.time())
        if issued > current + 60 or current - issued > STATE_TTL_SECONDS:
            raise ValueError("expired_oauth_state")
        teacher_id = int(data["teacher_id"])
        if teacher_id <= 0:
            raise ValueError("invalid_oauth_state")
        return data
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("invalid_oauth_state") from exc


def status():
    calendar = google_calendar.connection_status()
    return {
        "connected": bool(calendar.get("connected")),
        "refresh_token": bool(calendar.get("refresh_token")),
        "calendar_id": calendar.get("calendar_id"),
        "error": calendar.get("error"),
        "oauth_configured": google_calendar.CREDENTIALS_PATH.exists(),
        "redirect_uri": redirect_uri(),
    }


def authorization_url(teacher_id):
    if not otp_secret.configured():
        raise RuntimeError("adelia_otp_secret_missing")
    if not google_calendar.CREDENTIALS_PATH.exists():
        raise FileNotFoundError("google_oauth_credentials_missing")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError("google_auth_oauthlib_missing") from exc

    state = make_state(teacher_id)
    flow = Flow.from_client_secrets_file(
        str(google_calendar.CREDENTIALS_PATH),
        scopes=google_calendar.SCOPES,
        state=state,
        redirect_uri=redirect_uri(),
    )
    url, returned_state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    if returned_state != state:
        raise RuntimeError("google_oauth_state_mismatch")
    return {
        "authorization_url": url,
        "state": state,
        "redirect_uri": redirect_uri(),
    }


def complete_callback(query_string):
    from urllib.parse import parse_qs

    params = parse_qs(str(query_string or ""), keep_blank_values=True)
    if params.get("error"):
        raise PermissionError(str(params["error"][0] or "google_oauth_denied"))
    state = str((params.get("state") or [""])[0])
    verify_state(state)

    if not google_calendar.CREDENTIALS_PATH.exists():
        raise FileNotFoundError("google_oauth_credentials_missing")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise RuntimeError("google_auth_oauthlib_missing") from exc

    flow = Flow.from_client_secrets_file(
        str(google_calendar.CREDENTIALS_PATH),
        scopes=google_calendar.SCOPES,
        state=state,
        redirect_uri=redirect_uri(),
    )
    callback_url = redirect_uri() + ("?" + str(query_string) if query_string else "")
    flow.fetch_token(authorization_response=callback_url)
    creds = flow.credentials
    if not creds or not creds.refresh_token:
        raise RuntimeError("google_refresh_token_missing")
    google_calendar._atomic_write(
        google_calendar.TOKEN_PATH,
        creds.to_json(),
    )
    return status()


def teacher_redirect(status_code, message=None):
    query = {"google": status_code}
    if message:
        query["message"] = str(message)[:120]
    return "/teacher/?" + urlencode(query)
