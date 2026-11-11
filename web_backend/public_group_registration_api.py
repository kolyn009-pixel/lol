"""Recruitment routes without changing individual-trial onboarding."""
from urllib.parse import urlparse, parse_qs
from web_backend import public_group_registration as registrations
from web_backend import api as v1


class PublicGroupRegistrationMixin:
    def do_GET(self):
        u = urlparse(self.path)
        if u.path != '/api/public/group-registration':
            return super().do_GET()
        try:
            return self._json(200, registrations.preview(parse_qs(u.query).get('group_id', ['0'])[0]))
        except (TypeError, ValueError):
            return self._json(404, {'error': 'group_not_available'})
        except Exception as exc:
            print('[group-registration] preview:', type(exc).__name__, flush=True)
            return self._json(500, {'error': 'server_error'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {'/api/public/group-registration', '/api/teacher/group-registration/review'}:
            return super().do_POST()
        if not self._same_origin_write():
            return self._json(403, {'error': 'cross_origin_forbidden'})
        teacher = None
        if path.startswith('/api/teacher/'):
            teacher = self._teacher()
            if not teacher:
                return self._json(401, {'error': 'unauthorized'})
        elif not v1._allowed(self.client_address[0]):
            return self._json(429, {'error': 'too_many_attempts'})
        body = self._body()
        if not isinstance(body, dict):
            return self._json(400, {'error': 'invalid_json'})
        try:
            if teacher:
                result = registrations.review(body.get('request_id'), body.get('status'), teacher['admin_telegram_id'])
            else:
                result = registrations.register(body)
            return self._json(200, result)
        except (TypeError, ValueError) as exc:
            return self._json(400, {'error': str(exc) if isinstance(exc, ValueError) else 'invalid_fields'})
        except Exception as exc:
            print('[group-registration] save:', type(exc).__name__, flush=True)
            return self._json(500, {'error': 'server_error'})
