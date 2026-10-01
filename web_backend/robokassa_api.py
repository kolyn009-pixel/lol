"""Narrow routes for authenticated checkout and signed server callbacks."""
from urllib.parse import parse_qs, urlparse
from web_backend import robokassa

PREFIX = '/api/payments/robokassa/'


class RobokassaMixin:
    def _robo_text(self, status, text, content_type='text/plain; charset=utf-8'):
        data = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def robokassa_get(self, path):
        if path in {PREFIX + 'success', PREFIX + 'fail'}:
            # No supplied parameter here is evidence of payment; no DB writes.
            text = ('Возвращайтесь в кабинет. Статус обновится после подтверждения Робокассы.'
                    if path.endswith('success') else 'Оплата не завершена. Проверьте статус в кабинете перед повторной оплатой.')
            self._robo_text(200, '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Оплата Аделии</title><body><main><h1>Оплата Аделии</h1><p>' + text + '</p><p><a href="/app/parent/">Кабинет родителя</a></p><p><a href="/app/">Кабинет ученика</a></p></main></body></html>', 'text/html; charset=utf-8')
            return True
        if path == PREFIX + 'status':
            if not self._auth(): self._json(401, {'error': 'unauthorized'})
            else: self._json(200, robokassa.availability())
            return True
        if path == '/api/teacher/finance/robokassa':
            if not self._teacher(): self._json(401, {'error': 'unauthorized'})
            else: self._json(200, robokassa.teacher_status())
            return True
        return False

    def robokassa_post(self, path):
        if path == PREFIX + 'result':
            try:
                if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/x-www-form-urlencoded':
                    raise ValueError('invalid_content_type')
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 16384: raise ValueError('invalid_body_size')
                pairs = parse_qs(self.rfile.read(size).decode('utf-8'), keep_blank_values=True, max_num_fields=32)
                if any(len(v) != 1 for v in pairs.values()): raise ValueError('duplicate_parameter')
                params = {k: v[0] for k, v in pairs.items()}
                self._robo_text(200, robokassa.result(params))
            except PermissionError: self._robo_text(403, 'invalid_signature')
            except (ValueError, UnicodeError): self._robo_text(400, 'invalid_callback')
            except Exception: self._robo_text(503, 'retry_later')
            return True
        if path != PREFIX + 'checkout': return False
        if not self._same_origin_write():
            self._json(403, {'error': 'cross_origin_forbidden'}); return True
        auth = self._auth()
        if not auth or auth.get('role') not in {'student', 'parent'}:
            self._json(401, {'error': 'unauthorized'}); return True
        body = self._body()
        if not isinstance(body, dict):
            self._json(400, {'error': 'invalid_json'}); return True
        try:
            uid = int(auth['id'])
            if auth['role'] == 'parent':
                from web_backend.payment_hub import _linked
                uid = _linked(uid, int(body.get('student_id') or 0))
            self._json(200, robokassa.checkout(uid, int(body.get('payment_id') or 0)))
        except PermissionError: self._json(404, {'error': 'payment_not_found'})
        except (ValueError, TypeError) as exc: self._json(409, {'error': str(exc)})
        except Exception: self._json(503, {'error': 'payment_unavailable'})
        return True
