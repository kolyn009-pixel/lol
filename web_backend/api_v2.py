"""Adelia web API v2.

Extends the proven v1 handler without duplicating its teacher/homework routes.
This layer exposes real student dashboard, schedule, finance, profile and chat
read models and keeps the existing authentication/session implementation.
"""
from __future__ import annotations

import json
from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from web_backend import api as v1
from web_backend.student_portal import (
    dashboard as student_dashboard,
    schedule as student_schedule,
    payments as student_payments,
    profile as student_profile,
    conversation_for_student,
)
from web_backend.unified_messages import add_message


class Handler(v1.Handler):
    server_version = "AdeliaWeb/1.0"

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        q = parse_qs(u.query)

        if path.startswith("/api/student/"):
            auth = self._student()
            if not auth:
                return self._json(401, {"error": "unauthorized"})
            uid = int(auth["id"])
            try:
                if path == "/api/student/dashboard":
                    item = student_dashboard(uid)
                    return self._json(200, item) if item else self._json(404, {"error": "student_not_found"})
                if path == "/api/student/schedule":
                    return self._json(200, {"items": student_schedule(uid, q.get("limit", [40])[0])})
                if path == "/api/student/payments":
                    item = student_payments(uid, q.get("limit", [50])[0])
                    return self._json(200, item) if item else self._json(404, {"error": "student_not_found"})
                if path == "/api/student/profile":
                    item = student_profile(uid)
                    return self._json(200, item) if item else self._json(404, {"error": "student_not_found"})
                if path == "/api/student/messages":
                    return self._json(200, {"items": conversation_for_student(uid, q.get("limit", [100])[0])})
            except (TypeError, ValueError):
                return self._json(400, {"error": "invalid_request"})
            except Exception as exc:
                print("[web-api] student GET error:", repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/student/message":
            auth = self._student()
            if not auth:
                return self._json(401, {"error": "unauthorized"})
            body = self._body()
            if body is None:
                return self._json(400, {"error": "invalid_json"})
            text = str(body.get("text") or "").strip()
            if not text:
                return self._json(400, {"error": "text_required"})
            if len(text) > 4000:
                return self._json(400, {"error": "text_too_long"})
            try:
                mid = add_message(
                    int(auth["id"]),
                    "IN",
                    "STUDENT",
                    "WEB",
                    text=text,
                )
                return self._json(200, {"status": "ok", "message_id": mid})
            except Exception as exc:
                print("[web-api] student message error:", repr(exc), flush=True)
                return self._json(500, {"error": "server_error"})

        return super().do_POST()


def main():
    print(f"Adelia web API v2 listening on http://{v1.HOST}:{v1.PORT}")
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
