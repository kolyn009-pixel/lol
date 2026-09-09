"""Adelia web API v4: student booking routes on top of hardened v3."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from web_backend import api as v1, api_v3, otp_secret
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_booking import (
    programs as booking_programs,
    free_slots as booking_free_slots,
    request_one_off,
    cancel_pending,
)


class Handler(api_v3.Handler):
    server_version = 'AdeliaWeb/4.0'

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if path in {'/api/student/booking/programs', '/api/student/booking/free-slots'}:
            auth = self._student()
            if not auth:
                return self._json(401, {'error': 'unauthorized'})
            try:
                uid = int(auth['id'])
                if path.endswith('/programs'):
                    return self._json(200, {'items': booking_programs(uid)})
                return self._json(200, {
                    'items': booking_free_slots(
                        uid,
                        int(q.get('program_id', ['0'])[0]),
                        int(q.get('days', ['14'])[0]),
                        int(q.get('duration_minutes', ['60'])[0]),
                    )
                })
            except PermissionError as exc:
                return self._json(404, {'error': str(exc) or 'not_found'})
            except (TypeError, ValueError) as exc:
                return self._json(409, {'error': str(exc) or 'invalid_request'})
            except Exception as exc:
                print('[web-api] student booking GET error:', type(exc).__name__, flush=True)
                return self._json(500, {'error': 'server_error'})
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path in {'/api/student/booking/request', '/api/student/booking/cancel'}:
            if not self._same_origin_write():
                return self._json(403, {'error': 'cross_origin_forbidden'})
            auth = self._student()
            if not auth:
                return self._json(401, {'error': 'unauthorized'})
            body = self._body()
            if body is None:
                return self._json(400, {'error': 'invalid_json'})
            try:
                uid = int(auth['id'])
                if path.endswith('/request'):
                    result = request_one_off(
                        uid,
                        int(body.get('program_id')),
                        body.get('start_time'),
                        int(body.get('duration_minutes') or 60),
                    )
                else:
                    result = cancel_pending(uid, int(body.get('lesson_id')))
                return self._json(200, result)
            except PermissionError as exc:
                return self._json(404, {'error': str(exc) or 'not_found'})
            except (TypeError, ValueError) as exc:
                return self._json(409, {'error': str(exc) or 'invalid_request'})
            except Exception as exc:
                print('[web-api] student booking POST error:', type(exc).__name__, flush=True)
                return self._json(500, {'error': 'server_error'})
        return super().do_POST()


def main():
    if not otp_secret.configured():
        raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
    ensure_indexes()
    print(f'Adelia web API v4 listening on http://{v1.HOST}:{v1.PORT}')
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
