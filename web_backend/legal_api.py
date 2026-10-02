"""Legal routes and parent gate shared by all API v7 client entry points."""
from web_backend import legal_documents as legal
import json


class LegalMixin:
    def _legal_body(self):
        try:
            if self.headers.get('Content-Type', '').split(';')[0].lower() != 'application/json':
                return None
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 262144:
                return None
            return json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            return None

    def legal_get(self, path, query):
        if path == '/api/public/legal':
            version = query.get('version', [None])[0]
            edition = legal.public(version)
            self._json(200 if edition or not version else 404, {'edition': edition})
            return True
        if path == '/api/teacher/legal':
            if not self._owner(): self._json(403, {'error': 'owner_required'})
            else: self._json(200, legal.editor())
            return True
        if path == '/api/parent/legal/status':
            auth = self._auth()
            if not auth or auth.get('role') != 'parent': self._json(401, {'error': 'unauthorized'})
            else: self._json(200, legal.status(auth['id']))
            return True
        return False

    def legal_post(self, path):
        if path not in {'/api/teacher/legal/draft', '/api/teacher/legal/publish', '/api/parent/legal/accept'}:
            return False
        if not self._same_origin_write():
            self._json(403, {'error': 'cross_origin_forbidden'}); return True
        auth = self._auth()
        role = 'parent' if path.endswith('/accept') else 'teacher'
        if not auth or auth.get('role') != role:
            self._json(401, {'error': 'unauthorized'}); return True
        if role == 'teacher' and not self._owner():
            self._json(403, {'error': 'owner_required'}); return True
        body = self._legal_body()
        if not isinstance(body, dict):
            self._json(400, {'error': 'invalid_json'}); return True
        try:
            result = legal.accept(auth['id'], body) if role == 'parent' else legal.save(body, auth['id'], path.endswith('/publish'))
            self._json(200, result)
        except ValueError as exc:
            self._json(409, {'error': str(exc)})
        return True

    def legal_parent_gate(self, path):
        if not path.startswith('/api/') or path.startswith(('/api/public/', '/api/auth/', '/api/parent/legal/')):
            return False
        # Provider callbacks remain independent of a browser's acceptance.
        if path == '/api/payments/robokassa/result':
            return False
        auth = self._auth()
        if auth and auth.get('role') == 'parent' and legal.status(auth['id'])['required']:
            self._json(428, {'error': 'legal_acceptance_required', 'url': '/app/parent/consent.html'})
            return True
        return False
