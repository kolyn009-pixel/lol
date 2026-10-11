"""Isolated money-integrity regressions; never opens the production database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
import ast
import types
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import database
from core import minute_balance, payment_reversal
# Load the actual accounting modules without importing Telegram bot handlers
# from final_features.__init__ on dependency-free Actions preflight runners.
accounting_package = types.ModuleType("final_features")
accounting_package.__path__ = [str(Path(__file__).resolve().parents[1] / "final_features")]
sys.modules.setdefault("final_features", accounting_package)
from final_features import schema, ledger


class ReversalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = database.DB_NAME
        database.DB_NAME = self.tmp.name + "/test.db"
        database.create_tables()
        minute_balance.ensure_schema()
        schema.initialize()
        self.sql("INSERT INTO users(id,name,grade,study_goal,main_subject,created_at) VALUES(1,'Test',9,'SCHOOL','PHYSICS','2026-01-01')")

    def tearDown(self):
        database.DB_NAME = self.old
        self.tmp.cleanup()

    def sql(self, sql, args=()):
        c = database.connect()
        try:
            result = c.execute(sql, args)
            rows = result.fetchall()
            c.commit()
            return rows
        finally:
            c.close()

    def payment(self, count=4, bonus=False):
        pid = database.create_payment(1, "SCHOOL", "PHYSICS", count, 1600,
                                      minutes_total=count*60, base_duration_minutes=60, hourly_rate=1600)
        pkg = database.approve_payment(pid)
        if bonus:
            self.sql("UPDATE lesson_packages SET source_type='BONUS' WHERE id=?", (pkg,))
        return pid, pkg

    def lesson(self):
        rows = self.sql("""INSERT INTO lessons(user_id,study_goal,subject,start_time,end_time,
            duration_minutes,hourly_rate,price,payment_status,lesson_status,created_at)
            VALUES(1,'SCHOOL','PHYSICS','2026-12-10T12:00:00','2026-12-10T13:00:00',
            60,1600,1600,'AWAITING_PAYMENT','CONFIRMED','2026-01-01') RETURNING id""")
        return rows[0]["id"]

    def reverse(self, pid):
        return payment_reversal.reverse(pid, actor_id=100, source="TEST")

    def test_unused_package_repeat_and_stale_approval(self):
        pid, pkg = self.payment()
        self.assertEqual(minute_balance.get_balance(1)["paid"], 240)
        self.reverse(pid)
        self.assertEqual(minute_balance.get_balance(1)["paid"], 0)
        self.assertTrue(self.reverse(pid)["already_reversed"])
        self.assertEqual(self.sql("SELECT COUNT(*) n FROM payment_reversals")[0]["n"], 1)
        self.assertEqual(self.sql("SELECT SUM(money_rubles) s FROM minute_ledger")[0]["s"], 0)
        with self.assertRaises(ValueError): database.approve_payment(pid)
        with self.assertRaises(ValueError): database.add_receipt(pid, 1, "old", "PHOTO")
        minute_balance.credit_confirmed_payment(pid, pkg)
        self.assertEqual(minute_balance.get_balance(1)["paid"], 0)
        self.assertFalse(database.refund_prepaid_lesson(pkg))

    def test_direct_manual_lesson_can_be_paid_again(self):
        lid = self.lesson()
        pid, pkg = database.confirm_manual_lesson_payment(lid)
        self.reverse(pid)
        self.assertFalse(database.refund_prepaid_lesson(pkg))
        l = database.get_lesson(lid)
        self.assertEqual(l["payment_status"], "AWAITING_PAYMENT")
        self.assertEqual(l["lesson_status"], "CONFIRMED")
        self.assertIsNone(l["payment_deadline"])
        self.assertEqual(l["charged"], 0)
        pid2, _ = database.confirm_manual_lesson_payment(lid)
        self.assertNotEqual(pid, pid2)
        self.assertEqual(database.get_lesson(lid)["payment_status"], "PAID")

    def test_mixed_reservation_restores_real_bonus_and_preserves_completed_lesson(self):
        good = minute_balance.add_bonus_minutes(1, None, 30)
        bad, _ = self.payment(2)
        lid = self.lesson()
        minute_balance.reserve_minutes(1, 1600, 60, lid)
        self.sql("UPDATE lessons SET lesson_status='COMPLETED' WHERE id=?", (lid,))
        self.reverse(bad)
        self.assertEqual(minute_balance.get_balance(1), {"paid":0,"bonus":30,"total":30})
        self.assertEqual(ledger.derived_balance(1), {"paid":0,"bonus":30,"total":30})
        self.assertEqual(database.get_lesson(lid)["lesson_status"], "COMPLETED")
        self.assertEqual(database.get_lesson(lid)["payment_status"], "AWAITING_PAYMENT")
        self.assertEqual(self.sql("SELECT COUNT(*) n FROM lesson_minute_charges WHERE refunded=0")[0]["n"], 0)
        self.assertFalse(minute_balance.refund_lesson_minutes(lid))

    def test_already_refunded_reservation_does_not_duplicate_credit(self):
        pid, _ = self.payment(2)
        lid = self.lesson()
        minute_balance.reserve_minutes(1, 1600, 60, lid)
        minute_balance.refund_lesson_minutes(lid)
        self.reverse(pid)
        self.assertEqual(minute_balance.get_balance(1)["total"], 0)
        self.assertFalse(minute_balance.refund_lesson_minutes(lid))

    def test_provider_and_unpaid_rejected(self):
        pid, _ = self.payment()
        self.sql("CREATE TABLE robokassa_invoices(payment_id INTEGER,state TEXT)")
        self.sql("INSERT INTO robokassa_invoices VALUES(?,'SETTLED')", (pid,))
        with self.assertRaisesRegex(ValueError, "provider_payment_requires_refund"): self.reverse(pid)
        self.assertEqual(database.get_payment(pid)["status"], "PAID")
        waiting = database.create_payment(1, "SCHOOL", "PHYSICS", 1, 1600)
        with self.assertRaisesRegex(ValueError, "payment_not_paid"): self.reverse(waiting)

    def test_atomic_rollback_on_receipt_failure(self):
        pid, _ = self.payment()
        self.sql("INSERT INTO receipts(payment_id,user_id,file_type,status,created_at) VALUES(?,1,'PHOTO','APPROVED','2026-01-01')", (pid,))
        self.sql("CREATE TRIGGER refuse_reversal BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(Exception): self.reverse(pid)
        self.assertEqual(database.get_payment(pid)["status"], "PAID")
        self.assertEqual(minute_balance.get_balance(1)["paid"], 240)
        self.assertEqual(self.sql("SELECT COUNT(*) n FROM minute_ledger WHERE operation='PAYMENT_REVERSAL'")[0]["n"], 0)

    def test_concurrent_reverse_is_once(self):
        pid, _ = self.payment()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.reverse, [pid, pid]))
        self.assertEqual(sum(not x["already_reversed"] for x in results), 1)
        self.assertEqual(minute_balance.get_balance(1)["paid"], 0)

    def test_http_authorization_origin_and_explicit_confirmation(self):
        source = Path(__file__).resolve().parents[1] / "web_backend/stage8_api.py"
        tree = ast.parse(source.read_text())
        cls = next(x for x in tree.body if isinstance(x, ast.ClassDef))
        env = {"payment_reversal": payment_reversal}
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), env)
        class Handler(env["Stage8Mixin"]):
            def _teacher(self): return {"admin_telegram_id":100} if self.authorized else None
            def _same_origin_write(self): return self.same_origin
            def _body(self): return self.body
            def _json(self, code, value): return code, value
        h = Handler()
        pid, _ = self.payment()
        h.authorized = False; h.same_origin = True; h.body = {"payment_id":pid,"confirmed":True}
        self.assertEqual(h.stage8_post("/api/teacher/finance/payment/reverse")[0], 401)
        h.authorized = True; h.same_origin = False
        self.assertEqual(h.stage8_post("/api/teacher/finance/payment/reverse")[0], 403)
        h.same_origin = True; h.body["confirmed"] = False
        self.assertEqual(h.stage8_post("/api/teacher/finance/payment/reverse")[0], 400)
        self.assertEqual(database.get_payment(pid)["status"], "PAID")

    def test_preview_changes_no_balance(self):
        pid, _ = self.payment()
        result = payment_reversal.preview(pid)
        self.assertEqual(result["amount"], database.get_payment(pid)["total_amount"])
        self.assertEqual(result["remaining_minutes"], 240)
        self.assertEqual(database.get_payment(pid)["status"], "PAID")

    def test_telegram_confirmation_and_access(self):
        # Exercise the actual callback code with transport stubs, without
        # sending Telegram messages or importing the production bot.
        import asyncio
        class Button:
            def __init__(self, text, callback_data): self.text=text;self.callback_data=callback_data
        class Markup:
            def __init__(self, rows): self.inline_keyboard=rows
        fake_telegram=types.SimpleNamespace(InlineKeyboardButton=Button,InlineKeyboardMarkup=Markup)
        fake_admin=types.SimpleNamespace(is_admin=lambda update:update.effective_user.id==100)
        source=Path(__file__).resolve().parents[1]/"handlers/payment_reversal.py"
        env={}
        pid, _=self.payment()
        class Query:
            data=f"payment_admin_reverse|{pid}"
            message=types.SimpleNamespace(photo=None,document=None)
            async def edit_message_text(self,text,reply_markup): self.text=text;self.markup=reply_markup
            async def answer(self,*args,**kwargs): self.denied=True
        q=Query(); update=types.SimpleNamespace(callback_query=q,effective_user=types.SimpleNamespace(id=100))
        with patch.dict(sys.modules,{"telegram":fake_telegram,"admin":fake_admin}), patch.object(payment_reversal,"notify"):
            exec(compile(source.read_text(),str(source),"exec"),env)
            asyncio.run(env["handle"](update,types.SimpleNamespace()))
            self.assertEqual(database.get_payment(pid)["status"],"PAID")
            self.assertEqual(q.markup.inline_keyboard[0][0].callback_data,f"payment_admin_reverse_yes|{pid}")
            q.data=f"payment_admin_reverse_yes|{pid}";update.effective_user.id=999
            asyncio.run(env["handle"](update,types.SimpleNamespace()))
            self.assertEqual(database.get_payment(pid)["status"],"PAID")
            update.effective_user.id=100
            asyncio.run(env["handle"](update,types.SimpleNamespace()))
            self.assertEqual(database.get_payment(pid)["status"],"REVERSED")


if __name__ == "__main__":
    unittest.main()
