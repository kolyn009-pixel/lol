"""Offline regression suite; real temporary SQLite, no provider/network calls."""
import hashlib
import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse, unquote
import json

import database
from core import minute_balance
from web_backend import robokassa
from web_backend.robokassa_api import RobokassaMixin, PREFIX


class Payments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, 'DB_NAME', str(Path(self.tmp.name) / 'test.db'))
        self.db_patch.start()
        self.env = patch.dict(os.environ, {'ROBOKASSA_ENABLED': '1', 'ROBOKASSA_TEST_MODE': '0',
            'ROBOKASSA_SMZ_READY': '1', 'ROBOKASSA_MERCHANT_LOGIN': 'test-shop',
            'ROBOKASSA_HASH': 'sha256', 'ROBOKASSA_PASSWORD1': 'live-one',
            'ROBOKASSA_PASSWORD2': 'live-two', 'ROBOKASSA_TEST_PASSWORD1': 'test-one',
            'ROBOKASSA_TEST_PASSWORD2': 'test-two'})
        self.env.start()
        database.create_tables()
        minute_balance.ensure_schema()
        with database.connect() as conn:
            for uid in (1, 2):
                conn.execute("INSERT INTO users(id,name,grade,study_goal,main_subject,created_at) VALUES(?, 'Fixture', 9, 'SCHOOL', 'PHYSICS', '2026-10-01')", (uid,))

    def tearDown(self):
        self.env.stop(); self.db_patch.stop(); self.tmp.cleanup()

    def payment(self, count=1, price=1600):
        return database.create_payment(1, 'SCHOOL', 'PHYSICS', count, price)

    def start(self, pid):
        result = robokassa.checkout(1, pid)
        return {k: v[0] for k, v in parse_qs(urlparse(result['url']).query).items()}

    def callback(self, request, amount=None, password=None):
        amount = amount or request['OutSum'] + '0000'
        extra = {k: v for k, v in request.items() if k.startswith('Shp_')}
        password = password or ('test-two' if request['IsTest'] == '1' else 'live-two')
        text = amount + ':' + request['InvId'] + ':' + password + ''.join(':' + k + '=' + extra[k] for k in sorted(extra))
        return {'OutSum': amount, 'InvId': request['InvId'], 'SignatureValue': hashlib.sha256(text.encode()).hexdigest(), **extra}

    def test_exact_amount_signature_receipt_and_reuse(self):
        pid = self.payment(price=1650)
        request = self.start(pid)
        self.assertEqual(request['OutSum'], '1650.00')
        extra = ''.join(':' + k + '=' + request[k] for k in sorted(request) if k.startswith('Shp_'))
        expected = hashlib.sha256(('test-shop:1650.00:' + request['InvId'] + ':' + request['Receipt'] + ':live-one' + extra).encode()).hexdigest()
        self.assertEqual(request['SignatureValue'], expected)
        self.assertEqual(json.loads(unquote(request['Receipt']))['items'][0]['sum'], 1650)
        self.assertEqual(self.start(pid)['InvId'], request['InvId'])
        with self.assertRaises(PermissionError): robokassa.checkout(2, pid)

    def test_forged_or_wrong_amount_does_not_credit(self):
        pid = self.payment(); request = self.start(pid)
        callback = self.callback(request); callback['SignatureValue'] = '0' * 64
        with self.assertRaises(PermissionError): robokassa.result(callback)
        with self.assertRaises(ValueError): robokassa.result(self.callback(request, '1.00'))
        with self.assertRaises(PermissionError): robokassa.result(self.callback(request, password='test-two'))
        self.assertEqual(database.get_payment(pid)['status'], 'WAITING')

    def test_duplicate_parallel_callback_and_consumed_minutes(self):
        pid = self.payment(count=4); request = self.start(pid); callback = self.callback(request)
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: robokassa.result(callback), range(4)))
        self.assertEqual(set(replies), {'OK' + request['InvId']})
        with database.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM lesson_packages WHERE payment_id=?', (pid,)).fetchone()[0], 1)
            conn.execute('UPDATE lesson_packages SET minutes_used=75,lessons_used=1 WHERE payment_id=?', (pid,))
        robokassa.result(callback)
        with database.connect() as conn:
            self.assertEqual(conn.execute('SELECT minutes_used FROM lesson_packages WHERE payment_id=?', (pid,)).fetchone()[0], 75)
            self.assertEqual(conn.execute('SELECT state FROM robokassa_invoices WHERE payment_id=?', (pid,)).fetchone()[0], 'SETTLED')

    def test_test_payment_never_credits_even_after_mode_switch(self):
        pid = self.payment()
        with patch.dict(os.environ, {'ROBOKASSA_TEST_MODE': '1'}): request = self.start(pid)
        robokassa.result(self.callback(request))
        self.assertEqual(database.get_payment(pid)['status'], 'WAITING')
        with database.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM lesson_packages').fetchone()[0], 0)

    def test_changed_or_manual_paid_invoice_requires_review(self):
        for changed in (True, False):
            pid = self.payment(); request = self.start(pid)
            if changed:
                with database.connect() as conn: conn.execute('UPDATE payments SET total_amount=1750 WHERE id=?', (pid,))
            else: database.approve_payment(pid)
            robokassa.result(self.callback(request))
            with database.connect() as conn:
                self.assertEqual(conn.execute('SELECT state FROM robokassa_invoices WHERE payment_id=?', (pid,)).fetchone()[0], 'REVIEW')
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM lesson_packages WHERE payment_id=?', (pid,)).fetchone()[0], 0 if changed else 1)

    def test_disabled_checkout_and_pending_callbacks(self):
        pid = self.payment(); request = self.start(pid)
        with patch.dict(os.environ, {'ROBOKASSA_ENABLED': '0'}):
            self.assertFalse(robokassa.availability()['enabled'])
            with self.assertRaises(ValueError): self.start(pid)
            self.assertEqual(robokassa.result(self.callback(request)), 'OK' + request['InvId'])

    def test_direct_lesson_and_cancelled_after_checkout(self):
        for cancelled in (False, True):
            with database.connect() as conn:
                lid = conn.execute("""INSERT INTO lessons
                    (user_id,study_goal,subject,start_time,end_time,duration_minutes,
                     lesson_status,payment_status,created_at)
                    VALUES(1,'SCHOOL','PHYSICS','2026-10-10T19:00:00+03:00',
                           '2026-10-10T20:00:00+03:00',60,'CONFIRMED','UNPAID','2026-10-01')""").lastrowid
            pid = database.create_payment(1, 'SCHOOL', 'PHYSICS', 1, 1650, lesson_id=lid)
            request = self.start(pid)
            if cancelled:
                with database.connect() as conn: conn.execute("UPDATE lessons SET lesson_status='CANCELLED' WHERE id=?", (lid,))
            robokassa.result(self.callback(request))
            with database.connect() as conn:
                lesson = conn.execute('SELECT * FROM lessons WHERE id=?', (lid,)).fetchone()
                state = conn.execute('SELECT state FROM robokassa_invoices WHERE payment_id=?', (pid,)).fetchone()[0]
                self.assertEqual(state, 'REVIEW' if cancelled else 'SETTLED')
                self.assertEqual(lesson['payment_status'], 'UNPAID' if cancelled else 'PAID')
                if not cancelled:
                    pkg = conn.execute('SELECT * FROM lesson_packages WHERE payment_id=?', (pid,)).fetchone()
                    self.assertEqual(pkg['minutes_used'], pkg['minutes_total'])

    def test_missing_smz_activation_and_equal_test_password(self):
        with patch.dict(os.environ, {'ROBOKASSA_SMZ_READY': '0'}): self.assertFalse(robokassa.availability()['enabled'])
        with patch.dict(os.environ, {'ROBOKASSA_TEST_PASSWORD2': 'live-two'}): self.assertFalse(robokassa.availability()['enabled'])

    def test_http_duplicate_params_csrf_and_success_never_credit(self):
        class Handler(RobokassaMixin):
            def send_response(self, status): self.status = status
            def send_header(self, *args): pass
            def end_headers(self): pass
            def _same_origin_write(self): return False
            def _json(self, status, body): self.status = status
        pid = self.payment(); request = self.start(pid)
        body = (urlencode(self.callback(request)) + '&InvId=99').encode()
        h = Handler(); h.headers = {'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': str(len(body))}
        h.rfile = io.BytesIO(body); h.wfile = io.BytesIO()
        h.robokassa_post(PREFIX + 'result'); self.assertEqual(h.status, 400)
        h.robokassa_post(PREFIX + 'checkout'); self.assertEqual(h.status, 403)
        h.robokassa_get(PREFIX + 'success'); self.assertEqual(h.status, 200)
        self.assertEqual(database.get_payment(pid)['status'], 'WAITING')


if __name__ == '__main__': unittest.main()
