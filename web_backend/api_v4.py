"""Adelia web API v4: booking, reschedule, exchange and student finance."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from web_backend import api as v1, api_v3, otp_secret
from web_backend.stage12_indexes import ensure_indexes
from web_backend.student_booking import programs as booking_programs, free_slots as booking_free_slots, request_one_off, cancel_pending
from web_backend.student_reschedule import (
    free_slots_for_lesson, create_request as create_slot_change,
    outgoing as outgoing_slot_changes, incoming as incoming_exchanges,
    respond_to_exchange, cancel_request as cancel_slot_change,
)
from web_backend.student_finance import (
    overview as finance_overview, quote as finance_quote,
    create_package_payment, create_lesson_payment,
    history as finance_history, attach_receipt,
)


class Handler(api_v3.Handler):
    server_version = 'AdeliaWeb/4.2'

    def do_GET(self):
        u = urlparse(self.path); path, q = u.path, parse_qs(u.query)
        booking = {'/api/student/booking/programs', '/api/student/booking/free-slots'}
        changes = {'/api/student/reschedule/free-slots', '/api/student/reschedule/outgoing', '/api/student/exchanges/incoming'}
        finance = {'/api/student/finance/overview', '/api/student/finance/history', '/api/student/finance/quote'}
        if path in booking | changes | finance:
            auth = self._student()
            if not auth: return self._json(401, {'error': 'unauthorized'})
            try:
                uid = int(auth['id'])
                if path.endswith('/booking/programs'):
                    result = {'items': booking_programs(uid)}
                elif path.endswith('/booking/free-slots'):
                    result = {'items': booking_free_slots(uid, int(q.get('program_id',['0'])[0]), int(q.get('days',['14'])[0]), int(q.get('duration_minutes',['60'])[0]))}
                elif path.endswith('/reschedule/free-slots'):
                    result = {'items': free_slots_for_lesson(uid, int(q.get('lesson_id',['0'])[0]), int(q.get('days',['14'])[0]))}
                elif path.endswith('/reschedule/outgoing'):
                    result = {'items': outgoing_slot_changes(uid)}
                elif path.endswith('/exchanges/incoming'):
                    result = {'items': incoming_exchanges(uid)}
                elif path.endswith('/finance/overview'):
                    result = finance_overview(uid)
                elif path.endswith('/finance/history'):
                    result = {'items': finance_history(uid, int(q.get('limit',['30'])[0]))}
                else:
                    result = finance_quote(uid, int(q.get('selection_key',['0'])[0]), int(q.get('lessons_count',['1'])[0]), q.get('promo_code',[None])[0])
                return self._json(200, result)
            except PermissionError as exc: return self._json(404, {'error': str(exc) or 'not_found'})
            except (TypeError, ValueError) as exc: return self._json(409, {'error': str(exc) or 'invalid_request'})
            except Exception as exc:
                print('[web-api] student GET error:', type(exc).__name__, flush=True)
                return self._json(500, {'error': 'server_error'})
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        routes = {
            '/api/student/booking/request','/api/student/booking/cancel',
            '/api/student/reschedule/request','/api/student/reschedule/cancel','/api/student/exchanges/respond',
            '/api/student/finance/package','/api/student/finance/lesson','/api/student/finance/receipt',
        }
        if path in routes:
            if not self._same_origin_write(): return self._json(403, {'error': 'cross_origin_forbidden'})
            auth = self._student()
            if not auth: return self._json(401, {'error': 'unauthorized'})
            body = self._body()
            if body is None: return self._json(400, {'error': 'invalid_json'})
            try:
                uid = int(auth['id'])
                if path.endswith('/booking/request'):
                    result = request_one_off(uid, int(body.get('program_id')), body.get('start_time'), int(body.get('duration_minutes') or 60))
                elif path.endswith('/booking/cancel'):
                    result = cancel_pending(uid, int(body.get('lesson_id')))
                elif path.endswith('/reschedule/request'):
                    result = create_slot_change(uid, int(body.get('lesson_id')), body.get('desired_start'), body.get('note'))
                elif path.endswith('/reschedule/cancel'):
                    result = cancel_slot_change(uid, int(body.get('request_id')))
                elif path.endswith('/exchanges/respond'):
                    result = respond_to_exchange(uid, int(body.get('request_id')), bool(body.get('accepted')))
                elif path.endswith('/finance/package'):
                    result = create_package_payment(uid, int(body.get('selection_key')), int(body.get('lessons_count')), body.get('promo_code'))
                elif path.endswith('/finance/lesson'):
                    result = create_lesson_payment(uid, int(body.get('lesson_id')), body.get('promo_code'))
                else:
                    result = attach_receipt(uid, int(body.get('payment_id')), body.get('filename'), body.get('mime_type'), body.get('content_b64'))
                return self._json(200, result)
            except PermissionError as exc: return self._json(404, {'error': str(exc) or 'not_found'})
            except (TypeError, ValueError) as exc: return self._json(409, {'error': str(exc) or 'invalid_request'})
            except Exception as exc:
                print('[web-api] student POST error:', type(exc).__name__, flush=True)
                return self._json(500, {'error': 'server_error'})
        return super().do_POST()


def main():
    if not otp_secret.configured(): raise SystemExit('ADELIA_OTP_SECRET must be set to at least 32 bytes')
    ensure_indexes(); print(f'Adelia web API v4.2 listening on http://{v1.HOST}:{v1.PORT}')
    ThreadingHTTPServer((v1.HOST, v1.PORT), Handler).serve_forever()


if __name__ == '__main__': main()
