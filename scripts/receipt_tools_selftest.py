"""Receipt parsing and factual payment dates against isolated production SQLite."""
from datetime import timedelta
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import database
from web_backend import receipt_review_tools as tools


class Receipts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=database.DB_NAME
        database.DB_NAME=str(Path(self.tmp.name)/'test.db');database.create_tables();tools.ensure_schema()
        c=database.connect();c.execute("INSERT INTO users(id,name,grade,study_goal,main_subject,created_at,active) VALUES(1,'Тест',11,'EGE','PHYSICS','2026-01-01',1)")
        c.execute("INSERT INTO payments(id,user_id,study_goal,subject,lessons_count,price_per_lesson,total_amount,status,discount_percent,payment_type,subtotal,created_at) VALUES(1,1,'EGE','PHYSICS',2,900,1800,'WAITING',0,'PACKAGE',1800,?)",(database.now_iso(),))
        c.execute("INSERT INTO receipts(id,payment_id,user_id,source_platform,file_type,status,created_at) VALUES(1,1,1,'WEB','PNG','WAITING',?)",(database.now_iso(),));c.commit();c.close()

    def tearDown(self):database.DB_NAME=self.old;self.tmp.cleanup()

    def test_sum_date_recipient_and_success(self):
        r=tools.parse_text('Перевод выполнен\nСумма перевода\n1 800,00 ₽\nКомиссия 0,00 ₽\nПолучатель: Николай С.\n21.10.2026 18:30')
        self.assertEqual(r['amount_kopeks'],180000);self.assertEqual(r['paid_on'],'2026-10-21');self.assertEqual(r['recipient'],'Николай С.');self.assertEqual(r['transfer_status'],'SUCCESS_TEXT')

    def test_ambiguous_or_no_sum_not_guessed(self):
        for text in ['Баланс 20 000,00 ₽\nКомиссия 50 ₽','Сумма 900 ₽\nИтого 1000 ₽','Сумма 1.800,00 ₽']:
            self.assertIsNone(tools.parse_text(text)['amount_kopeks'])
        self.assertEqual(tools.parse_text('Сумма: 1\u202f800,50 RUB')['amount_kopeks'],180050)

    def test_failed_and_pending_have_precedence(self):
        self.assertEqual(tools.parse_text('не выполнен, ранее выполнен')['transfer_status'],'FAILED')
        self.assertEqual(tools.parse_text('в обработке, перевод выполнен')['transfer_status'],'PENDING')

    def test_future_or_invalid_date_rejected(self):
        for value in ['2026-02-30','',None,(tools.today()+timedelta(days=1)).isoformat()]:
            with self.assertRaises(ValueError):tools.paid_date(value)

    def test_backdated_approval_uses_existing_credit_path_once(self):
        from web_backend import finance_receipts
        # No network notifications or independent balance backend in this test.
        day=(tools.today()-timedelta(days=10)).isoformat()
        with patch.object(finance_receipts,'_notify_review'),patch.object(finance_receipts,'approve_paid_booking_draft_payment',return_value=None):
            a=tools.review(1,'APPROVE',day,99);b=tools.review(1,'APPROVE',day,99)
        self.assertEqual(a['package_id'],b['package_id'])
        c=database.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM lesson_packages WHERE payment_id=1').fetchone()[0],1)
        p=c.execute('SELECT * FROM payments WHERE id=1').fetchone();self.assertEqual(p['status'],'PAID');self.assertTrue(p['confirmed_at'].startswith(database.now_iso()[:10]));c.close()
        self.assertEqual(tools.details(1)['paid_on'],day)
        with self.assertRaises(ValueError):tools.review(1,'APPROVE',tools.today().isoformat(),99)

    def test_mismatch_requires_reason_and_does_not_credit(self):
        r={**tools.parse_text('Сумма 900 ₽\nВыполнен'),'sha256':'abc'}
        c=database.connect();c.execute('INSERT INTO receipt_inspections VALUES(?,?,?,?)',(1,'abc',json.dumps(r),database.now_iso()));c.commit();c.close()
        with self.assertRaises(ValueError):tools.review(1,'APPROVE',tools.today().isoformat(),99,acknowledged=True)
        self.assertEqual(tools.details(1)['status'],'WAITING')

    def test_existing_past_lesson_can_be_confirmed_without_duplicate_credit(self):
        from web_backend import finance_receipts
        c=database.connect();c.execute("INSERT INTO lessons(id,user_id,study_goal,subject,start_time,end_time,duration_minutes,price,payment_status,lesson_status,created_at) VALUES(37,1,'EGE','PHYSICS','2026-01-05T18:15:00','2026-01-05T19:15:00',60,1800,'UNPAID','COMPLETED','2026-01-01')")
        c.execute('UPDATE payments SET lesson_id=37,lessons_count=1 WHERE id=1');c.commit();c.close()
        with patch.object(finance_receipts,'_notify_review'),patch.object(finance_receipts,'approve_paid_booking_draft_payment',return_value=None):
            a=tools.review(1,'APPROVE','2026-01-05',99);b=tools.review(1,'APPROVE','2026-01-05',99)
        self.assertEqual(a['package_id'],b['package_id']);c=database.connect()
        l=c.execute('SELECT * FROM lessons WHERE id=37').fetchone();self.assertEqual(l['payment_status'],'PAID');self.assertEqual(l['lesson_status'],'COMPLETED');self.assertEqual(c.execute('SELECT COUNT(*) FROM lesson_packages').fetchone()[0],1);c.close()

    def test_duplicate_finds_other_payment_but_not_same_payment(self):
        c=database.connect();c.execute("INSERT INTO payments(id,user_id,study_goal,subject,payment_type,lessons_count,price_per_lesson,subtotal,total_amount,status,created_at) VALUES(2,1,'EGE','PHYSICS','PACKAGE',2,900,1800,1800,'PAID','2026-01-01')")
        c.execute("INSERT INTO receipts(id,payment_id,user_id,source_platform,file_type,status,created_at) VALUES(2,2,1,'WEB','PNG','APPROVED',?)",(database.now_iso(),))
        c.execute('INSERT INTO receipt_inspections VALUES(?,?,?,?)',(2,'same','{}',database.now_iso()));c.commit();c.close()
        r=tools.decorate(1,{'sha256':'same'},tools._payment(1));self.assertEqual(r['duplicates'][0]['payment_id'],2);self.assertFalse(r['bank_verified'])

    def test_unsupported_file_not_executed(self):
        with self.assertRaises(ValueError):tools.extract(b'<svg onload="bad"/>')

    def test_api_auth_and_origin(self):
        from web_backend.receipt_tools_api import ReceiptToolsMixin
        o=ReceiptToolsMixin();o.path='/api/teacher/finance/receipt/inspect';o._teacher=lambda:None;o._same_origin_write=lambda:True;o._json=lambda code,data:(code,data)
        self.assertEqual(o.do_POST()[0],401);o._same_origin_write=lambda:False;self.assertEqual(o.do_POST()[0],403)


if __name__=='__main__':unittest.main()
