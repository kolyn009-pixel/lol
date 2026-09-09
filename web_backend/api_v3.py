"""Adelia web API v3: Stage 12 privacy/security hardening on top of api_v2."""
from __future__ import annotations

import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from core import admin_roles
from web_backend import api as v1
from web_backend import api_v2
from web_backend.lesson_join import student_join

_AUTH_LIMITS = {}
_AUTH_WINDOW = 300
_AUTH_MAX = 8
_OWNER_ONLY_POST = {
    "/api/teacher/finance/price",
    "/api/teacher/finance/override",
    "/api/teacher/finance/override/delete",
    "/api/teacher/finance/package",
}


def _auth_allowed(ip, route):
    now = time.time()
    key = (str(ip or ""), str(route or ""))
    start, count = _AUTH_LIMITS.get(key, (now, 0))
    if now - start > _AUTH_WINDOW:
        start, count = now, 0
    count += 1
    _AUTH_LIMITS[key] = (start, count)
    if len(_AUTH_LIMITS) > 5000:
        for k, v in list(_AUTH_LIMITS.items()):
            if now - v[0] > _AUTH_WINDOW:
                _AUTH_LIMITS.pop(k, None)
    return count <= _AUTH_MAX


class Handler(api_v2.Handler):
    server_version = "AdeliaWeb/3.3"

    def log_message(self, fmt, *args):
        try:
            path = urlparse(self.path).path
        except Exception:
            path = "?"
        print("[web-api]", self.client_address[0], self.command, path, flush=True)

    def end_headers(self):
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; connect-src 'self'",
        )
        super().end_headers()

    def _same_origin_write(self):
        origin = str(self.headers.get("Origin") or "").strip()
        if not origin:
            return True
        host = str(self.headers.get("Host") or "").strip().lower()
        if not host:
            return False
        try:
            parsed = urlparse(origin)
        except Exception:
            return False
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            return False
        return parsed.netloc.lower() == host

    def _owner(self):
        auth = self._teacher()
        if not auth:
            return None
        try:
            return auth if admin_roles.role_for(int(auth["id"])) == "OWNER" else None
        except Exception:
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/auth/me":
            auth = self._auth()
            if not auth:
                return self._json(200, {"authenticated": False, "session": None})
            return self._json(
                200,
                {
                    "authenticated": True,
                    "role": auth.get("role"),
                    "session": {"role": auth.get("role")},
                },
            )
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if not self._same_origin_write():
            return self._json(403, {"error": "cross_origin_forbidden"})

        if path in _OWNER_ONLY_POST and not self._owner():
            # Do not reveal whether the current teacher is merely an ADMIN or
            # unauthenticated; both are forbidden from changing global pricing.
            return self._json(403, {"error": "owner_required"})

        if path in {"/api/auth/student/code", "/api/auth/teacher/code", "/api/auth/parent/code"}:
            if not _auth_allowed(self.client_address[0], path):
                return self._json(429, {"error": "too_many_attempts"})

        if path == "/api/student/lesson/join":
            auth = self._student()
            if not auth:
                return self._json(401, {"error": "unauthorized"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "invalid_json"})
            try:
                result = student_join(int(body.get("lesson_id")), int(auth["id"]))
            except (TypeError, ValueError):
                return self._json(400, {"error": "invalid_request"})
            except Exception as exc:
                print("[web-api] student lesson join error:", type(exc).__name__, flush=True)
                return self._json(500, {"error": "server_error"})

            status = result.get("status")
            if status == "ok":
                return self._json(200, result)
            if status == "not_found":
                return self._json(404, {"error": status})
            if status in {"entry_closed", "invalid_status"}:
                return self._json(409, {"error": status, **{k: v for k, v in result.items() if k != "status"}})
            return self._json(400, {"error": status or "join_failed"})

        return super().do_POST()


def main():
    print(f"Adelia web API v3 listening on http://{v1.HOST}:{v1.PORT}")
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
