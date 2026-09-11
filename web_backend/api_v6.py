"""Adelia web API v6: explicit non-consuming student code verification."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from web_backend import api as v1
from web_backend import api_v5, otp_secret, open_event_admin, event_campaign, student_social_profile, group_portal
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_auth import peek_student_login_code


class Handler(api_v5.Handler):
    server_version = "AdeliaWeb/6.0"

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/auth/student/code/verify":
            if not self._same_origin_write():
                return self._json(403, {"error": "cross_origin_forbidden"})
            if not v1._allowed(self.client_address[0]):
                return self._json(429, {"error": "too_many_attempts"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "invalid_json"})
            result = peek_student_login_code(body.get("code"))
            if result.get("status") != "ok":
                return self._json(401, {"error": result.get("status", "invalid")})
            student = result.get("student") or {}
            return self._json(200, {
                "ok": True,
                "student": {
                    "id": student.get("id"),
                    "name": student.get("name"),
                    "telegram_username": student.get("telegram_username"),
                    "grade": student.get("grade"),
                },
            })
        return super().do_POST()


def main():
    if not otp_secret.configured():
        raise SystemExit("ADELIA_OTP_SECRET must be set to at least 32 bytes")
    ensure_indexes()
    open_event_admin.choices()
    event_campaign.ensure_schema()
    student_social_profile.ensure_schema()
    group_portal.ensure_schema()
    print(f"Adelia web API v6.0 listening on http://{v1.HOST}:{v1.PORT}")
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
