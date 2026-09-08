"""Minimal HTTP API for adeliatutor.ru.

Runs as a separate process and reuses TutorBot's database helpers. It does not
modify Telegram/VK handlers. Nginx can proxy /api/ to this service.
"""

import json
import os
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from web_backend.parent_linking import find_student_by_username, link_parent_to_student_by_username
from web_backend.public_catalog import get_public_price_catalog
from web_backend.public_reviews import list_public_reviews
from web_backend.student_auth import consume_student_login_code

HOST = os.getenv("ADELIA_WEB_HOST", "127.0.0.1")
PORT = int(os.getenv("ADELIA_WEB_PORT", "8765"))
SESSION_TTL = 60 * 60 * 24 * 30
_sessions = {}
_attempts = {}


def _session(role, entity_id):
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"role": role, "id": int(entity_id), "expires": time.time() + SESSION_TTL}
    return token


def _clean():
    now = time.time()
    for token in [k for k, v in _sessions.items() if v["expires"] < now]:
        _sessions.pop(token, None)
    for ip in [k for k, v in _attempts.items() if now - v[0] > 60]:
        _attempts.pop(ip, None)


def _allowed(ip):
    _clean(); now=time.time(); start,count=_attempts.get(ip,(now,0))
    if now-start>60: start,count=now,0
    count+=1; _attempts[ip]=(start,count)
    return count <= 12


class Handler(BaseHTTPRequestHandler):
    server_version = "AdeliaWeb/0.1"

    def log_message(self, fmt, *args):
        print("[web-api]", self.address_string(), fmt % args)

    def _json(self, status, payload, cookie=None):
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", f"adelia_session={cookie}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _body(self):
        try:
            n=min(int(self.headers.get("Content-Length","0")), 16384)
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return None

    def _auth(self):
        raw=self.headers.get("Cookie","")
        token=next((p.split("=",1)[1] for p in raw.split("; ") if p.startswith("adelia_session=")),None)
        item=_sessions.get(token)
        if not item or item["expires"] < time.time(): return None
        return item

    def do_GET(self):
        path=urlparse(self.path).path
        if path == "/api/health": return self._json(200,{"ok":True,"service":"adelia-web"})
        if path == "/api/public/prices": return self._json(200,{"items":get_public_price_catalog()})
        if path == "/api/public/reviews": return self._json(200,{"items":list_public_reviews(12)})
        if path == "/api/auth/me":
            auth=self._auth()
            return self._json(200,{"authenticated":bool(auth),"session":auth if auth else None})
        return self._json(404,{"error":"not_found"})

    def do_POST(self):
        path=urlparse(self.path).path
        body=self._body()
        if body is None: return self._json(400,{"error":"invalid_json"})
        if path == "/api/auth/student/code":
            if not _allowed(self.client_address[0]): return self._json(429,{"error":"too_many_attempts"})
            result=consume_student_login_code(body.get("code"))
            if result["status"] != "ok": return self._json(401,{"error":result["status"]})
            student=result["student"]; token=_session("student",student["id"])
            return self._json(200,{"ok":True,"student":student},token)
        if path == "/api/parent/student/find":
            auth=self._auth()
            if not auth or auth["role"] != "parent": return self._json(401,{"error":"unauthorized"})
            student=find_student_by_username(body.get("username"))
            return self._json(200,{"found":bool(student),"student":student})
        if path == "/api/parent/student/link":
            auth=self._auth()
            if not auth or auth["role"] != "parent": return self._json(401,{"error":"unauthorized"})
            return self._json(200,link_parent_to_student_by_username(auth["id"],body.get("username")))
        return self._json(404,{"error":"not_found"})


def main():
    print(f"Adelia web API listening on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
