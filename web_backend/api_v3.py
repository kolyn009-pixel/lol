"""Adelia web API v3: Stage 12 E2E fixes on top of api_v2."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import urlparse

from web_backend import api as v1
from web_backend import api_v2
from web_backend.lesson_join import student_join


class Handler(api_v2.Handler):
    server_version = "AdeliaWeb/3.0"

    def do_POST(self):
        path = urlparse(self.path).path
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
                print("[web-api] student lesson join error:", repr(exc), flush=True)
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
