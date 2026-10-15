"""Exercise production request parsing and parent finance routing without live data."""
import ast
import io
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]

def production_class(path, name, methods=None, env=None):
    module = ast.parse((ROOT / path).read_text())
    node = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == name)
    node.bases = []
    if methods:
        node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    scope = dict(env or {})
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, 'exec'), scope)
    return scope[name]

Parser = production_class('web_backend/api_v3.py', 'Handler', {'_json_body_limit', '_body'},
                          {'json': json, 'urlparse': urlparse, 'MAX_JSON_BODY': 256*1024})

class WeeklyPayments(unittest.TestCase):
    def parser(self, path, content):
        p = Parser(); p.path = path
        p.headers = {'Content-Length': str(len(content))}; p.rfile = io.BytesIO(content)
        return p

    def test_large_parent_receipt(self):
        raw = json.dumps({'content_b64': 'A'*(11*1024*1024)}).encode()
        p = self.parser('/api/parent/finance/receipt', raw)
        self.assertEqual(len(p._body()['content_b64']), 11*1024*1024)

    def test_student_receipt_same_limit(self):
        self.assertEqual(self.parser('/api/student/finance/receipt', b'{}')._json_body_limit(), 12*1024*1024)

    def test_other_routes_keep_small_limit(self):
        for path in ['/api/parent/finance/package', '/api/teacher/settings', '/api/parent/finance/receipt/other']:
            p = self.parser(path, b' '*(256*1024+1))
            self.assertIsNone(p._body()); self.assertTrue(p._body_too_large)
            self.assertEqual(p.rfile.tell(), 0)

    def test_receipt_oversize_rejected_before_read(self):
        p = self.parser('/api/parent/finance/receipt', b'')
        p.headers['Content-Length'] = str(12*1024*1024+1)
        self.assertIsNone(p._body()); self.assertTrue(p._body_too_large)

    def route(self, data, origin=True, auth=True, too_large=False):
        self.calls = []
        def record(*args):
            self.calls.append(args); return {'status': 'ok'}
        cls = production_class('web_backend/stage9_api.py', 'Stage9Mixin', env={
            'parent_create_package': record, 'parent_quote_package': record, 'parent_attach_receipt': record})
        obj = cls(); obj._auth = lambda: {'role': 'parent', 'id': 7} if auth else None
        obj._same_origin_write = lambda: origin
        obj._body = lambda: data; obj._body_too_large = too_large
        obj._json = lambda status, payload: (status, payload)
        return obj

    def test_two_lesson_package_uses_existing_payment_rules(self):
        obj = self.route({'student_id': 19, 'selection_key': 2, 'lessons_count': 2})
        self.assertEqual(obj.stage9_post('/api/parent/finance/package')[0], 200)
        self.assertEqual(self.calls, [(7, 19, 2, 2, None)])

    def test_one_receipt_for_combined_payment(self):
        obj = self.route({'student_id': 19, 'payment_id': 42, 'filename': 'week.pdf', 'mime_type': 'application/pdf', 'content_b64': 'abc'})
        self.assertEqual(obj.stage9_post('/api/parent/finance/receipt')[0], 200)
        self.assertEqual(self.calls, [(7, 19, 42, 'week.pdf', 'application/pdf', 'abc')])

    def test_cross_origin_rejected(self):
        obj = self.route({}, origin=False)
        self.assertEqual(obj.stage9_post('/api/parent/finance/package')[0], 403)
        self.assertEqual(self.calls, [])

    def test_unauthenticated_rejected(self):
        obj = self.route({}, auth=False)
        self.assertEqual(obj.stage9_post('/api/parent/finance/receipt')[0], 401)

    def test_invalid_json_and_oversize_response(self):
        for data in [[], 'text', None]:
            self.assertEqual(self.route(data).stage9_post('/api/parent/finance/package')[0], 400)
        self.assertEqual(self.route(None, too_large=True).stage9_post('/api/parent/finance/receipt')[0], 413)

if __name__ == '__main__':
    unittest.main()
