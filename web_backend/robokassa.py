"""Robokassa SMZ checkout. Disabled until configured; test receipts never credit.

Protocol: https://docs.robokassa.ru/ru/pay-interface and notifications-and-redirects.
Browser returns are informational. Only a signed ResultURL can settle an invoice.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlencode

import database

GATEWAY = 'https://auth.robokassa.ru/Merchant/Index.aspx'
PAYABLE = {'WAITING', 'PENDING', 'REJECTED'}


def _config(test=None, checkout=False):
    test = os.getenv('ROBOKASSA_TEST_MODE', '1') == '1' if test is None else bool(test)
    prefix = 'ROBOKASSA_TEST_' if test else 'ROBOKASSA_'
    cfg = {'merchant': os.getenv('ROBOKASSA_MERCHANT_LOGIN', '').strip(),
           'p1': os.getenv(prefix + 'PASSWORD1', ''),
           'p2': os.getenv(prefix + 'PASSWORD2', ''),
           'hash': os.getenv('ROBOKASSA_HASH', 'sha256').lower(), 'test': test}
    if not all(cfg[k] for k in ('merchant', 'p1', 'p2')) or cfg['hash'] not in {'md5', 'sha256', 'sha512'}:
        raise ValueError('robokassa_not_configured')
    if os.getenv('ROBOKASSA_TEST_PASSWORD2') and os.getenv('ROBOKASSA_TEST_PASSWORD2') == os.getenv('ROBOKASSA_PASSWORD2'):
        raise ValueError('robokassa_separate_test_passwords_required')
    if checkout and (os.getenv('ROBOKASSA_ENABLED', '0') != '1' or
                     (not test and os.getenv('ROBOKASSA_SMZ_READY', '0') != '1')):
        raise ValueError('robokassa_not_enabled')
    return cfg


def availability():
    try:
        cfg = _config(checkout=True)
        return {'enabled': True, 'test': cfg['test'], 'provider': 'robokassa'}
    except ValueError:
        return {'enabled': False, 'provider': 'robokassa'}


def ensure_schema():
    conn = database.connect()
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS robokassa_invoices (
            id INTEGER PRIMARY KEY, payment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, merchant TEXT NOT NULL,
            amount TEXT NOT NULL, is_test INTEGER NOT NULL, nonce TEXT NOT NULL,
            description TEXT NOT NULL, receipt TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'PENDING', created_at TEXT NOT NULL,
            received_at TEXT, settled_at TEXT, review_reason TEXT,
            UNIQUE(payment_id, is_test, merchant),
            FOREIGN KEY(payment_id) REFERENCES payments(id))''')
        conn.commit()
    finally:
        conn.close()


def _amount(raw):
    value = str(raw)
    if not re.fullmatch(r'[0-9]{1,12}(?:\.[0-9]{1,6})?', value):
        raise ValueError('invalid_amount')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('invalid_amount')
    if number <= 0 or number != number.quantize(Decimal('.01')):
        raise ValueError('invalid_amount')
    return number


def _hash(cfg, text):
    return hashlib.new(cfg['hash'], text.encode('utf-8')).hexdigest()


def _extras(row):
    return {'Shp_adelia': row['nonce'], 'Shp_mode': 'test' if row['is_test'] else 'live'}


def _suffix(extra):
    return ''.join(':' + key + '=' + extra[key] for key in sorted(extra))


def _check_payable(conn, payment):
    if payment['status'] not in PAYABLE:
        raise ValueError('payment_not_payable')
    # Draft booking has a separate reservation/confirmation workflow.
    if conn.execute('SELECT 1 FROM booking_drafts WHERE payment_id=? LIMIT 1', (payment['id'],)).fetchone():
        raise ValueError('booking_draft_requires_manual_payment')
    if payment['lesson_id']:
        lesson = conn.execute('SELECT lesson_status,payment_status FROM lessons WHERE id=?', (payment['lesson_id'],)).fetchone()
        if not lesson or lesson['lesson_status'] in {'CANCELLED', 'REJECTED'} or lesson['payment_status'] in {'PAID', 'FREE', 'RESERVED_BALANCE', 'TRANSFERRED'}:
            raise ValueError('lesson_not_payable')


def checkout(user_id, payment_id):
    cfg = _config(checkout=True)
    ensure_schema()
    conn = database.connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        payment = conn.execute('SELECT * FROM payments WHERE id=? AND user_id=?', (int(payment_id), int(user_id))).fetchone()
        if not payment:
            raise PermissionError('payment_not_found')
        _check_payable(conn, payment)
        amount = format(_amount(payment['total_amount']), '.2f')
        row = conn.execute('SELECT * FROM robokassa_invoices WHERE payment_id=? AND is_test=? AND merchant=?',
                           (payment['id'], int(cfg['test']), cfg['merchant'])).fetchone()
        if row and (row['amount'] != amount or row['state'] not in {'PENDING', 'TEST_PAID'}):
            raise ValueError('online_payment_requires_review')
        if not row:
            inv = secrets.randbelow(2**52 - 1) + 1
            description = ('Оплата занятия' if payment['lesson_id'] else 'Оплата абонемента на занятия') + ' ' + str(payment['id'])
            # Standard nomenclature; SMZ issuance is enabled by the merchant in Robokassa.
            receipt = quote(json.dumps({'items': [{'name': description, 'quantity': 1,
                'sum': int(payment['total_amount']), 'tax': 'none'}]}, ensure_ascii=False, separators=(',', ':')), safe='')
            conn.execute('''INSERT INTO robokassa_invoices
                (id,payment_id,user_id,merchant,amount,is_test,nonce,description,receipt,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (inv, payment['id'], int(user_id), cfg['merchant'], amount,
                int(cfg['test']), secrets.token_hex(16), description, receipt, database.now_iso()))
            row = conn.execute('SELECT * FROM robokassa_invoices WHERE id=?', (inv,)).fetchone()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    extra = _extras(row)
    signature = _hash(cfg, f"{cfg['merchant']}:{row['amount']}:{row['id']}:{row['receipt']}:{cfg['p1']}" + _suffix(extra))
    params = {'MerchantLogin': cfg['merchant'], 'OutSum': row['amount'], 'InvId': str(row['id']),
              'Description': row['description'], 'Receipt': row['receipt'], 'SignatureValue': signature,
              'Culture': 'ru', 'Encoding': 'utf-8', 'IsTest': '1' if cfg['test'] else '0', **extra}
    return {'url': GATEWAY + '?' + urlencode(params), 'payment_id': int(payment_id),
            'amount': row['amount'], 'test': cfg['test']}


def _notice(row, review=False):
    from core import event_center
    event_center.push('ONLINE_PAYMENT_REVIEW' if review else 'ONLINE_PAYMENT',
                     'Онлайн-оплата требует проверки' if review else 'Оплата через Робокассу',
                     'Платёж ' + str(row['payment_id']), 'ACTION' if review else 'INFO',
                     'payment', row['payment_id'], 'robokassa:' + str(row['id']))


def result(params):
    inv = str(params.get('InvId', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,18}', inv) or int(inv) > 2**63 - 1:
        raise ValueError('invalid_invoice')
    ensure_schema()
    conn = database.connect()
    try:
        row = conn.execute('SELECT * FROM robokassa_invoices WHERE id=?', (int(inv),)).fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError('unknown_invoice')
    cfg = _config(test=row['is_test'])
    extra = {k: v for k, v in params.items() if k.lower().startswith('shp_')}
    raw_sum = str(params.get('OutSum', ''))
    signature = str(params.get('SignatureValue', ''))
    expected = _hash(cfg, raw_sum + ':' + inv + ':' + cfg['p2'] + _suffix(extra))
    if (cfg['merchant'] != row['merchant'] or extra != _extras(row) or
            not hmac.compare_digest(signature.lower(), expected)):
        raise PermissionError('invalid_signature')
    if _amount(raw_sum) != _amount(row['amount']):
        raise ValueError('amount_mismatch')
    conn = database.connect()
    try:
        conn.execute('UPDATE robokassa_invoices SET received_at=COALESCE(received_at,?) WHERE id=?', (database.now_iso(), row['id']))
        if row['is_test']:
            conn.execute("UPDATE robokassa_invoices SET state='TEST_PAID' WHERE id=?", (row['id'],))
        conn.commit()
    finally:
        conn.close()
    if row['is_test']:
        return 'OK' + inv

    def verify(conn, payment):
        # Executed inside approve_payment's BEGIN IMMEDIATE. A duplicate callback
        # or simultaneous manual review cannot issue a second package.
        fresh = conn.execute('SELECT * FROM robokassa_invoices WHERE id=?', (row['id'],)).fetchone()
        if fresh['state'] == 'SETTLED' and payment['status'] == 'PAID':
            return
        if int(payment['user_id']) != row['user_id'] or _amount(payment['total_amount']) != _amount(row['amount']):
            raise ValueError('payment_changed')
        _check_payable(conn, payment)
        conn.execute("UPDATE robokassa_invoices SET state='SETTLED',settled_at=?,review_reason=NULL WHERE id=?",
                     (database.now_iso(), row['id']))

    try:
        package_id = database.approve_payment(row['payment_id'], verify_in_transaction=verify)
    except ValueError as exc:
        # Signed money received, but the lesson/invoice was changed or paid manually.
        # Preserve the receipt and alert the teacher; never silently credit another lesson.
        conn = database.connect()
        try:
            conn.execute("UPDATE robokassa_invoices SET state='REVIEW',review_reason=? WHERE id=? AND state!='SETTLED'",
                         (str(exc)[:200], row['id']))
            conn.commit()
        finally:
            conn.close()
        _notice(row, review=True)
        return 'OK' + inv
    from core import minute_balance
    minute_balance.credit_confirmed_payment(row['payment_id'], package_id)
    _notice(row)
    return 'OK' + inv


def teacher_status():
    ensure_schema()
    conn = database.connect()
    try:
        rows = conn.execute('''SELECT id,payment_id,amount,is_test,state,received_at,review_reason
            FROM robokassa_invoices ORDER BY created_at DESC LIMIT 50''').fetchall()
        return {**availability(), 'invoices': [dict(row) for row in rows]}
    finally:
        conn.close()
