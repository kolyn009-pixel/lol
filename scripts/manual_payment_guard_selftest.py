import ast,concurrent.futures,sqlite3,tempfile,threading,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class GuardTest(unittest.TestCase):
 def test_concurrent_and_linked_invoice(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'test.db'
   def connect():c=sqlite3.connect(path,timeout=10);c.row_factory=sqlite3.Row;return c
   c=connect();c.executescript('''CREATE TABLE lessons(id INTEGER PRIMARY KEY,user_id INTEGER,study_goal TEXT,subject TEXT,price INTEGER,payment_status TEXT,lesson_status TEXT,payment_id INTEGER,package_id INTEGER,charged INTEGER,payment_deadline TEXT,updated_at TEXT);
INSERT INTO lessons VALUES(1,1,'EGE','PHYSICS',3000,'AWAITING_PAYMENT','CONFIRMED',NULL,NULL,0,NULL,NULL),(2,1,'EGE','PHYSICS',3000,'AWAITING_PAYMENT','CONFIRMED',NULL,NULL,0,NULL,NULL);
CREATE TABLE payments(id INTEGER PRIMARY KEY,user_id INTEGER,study_goal TEXT,subject TEXT,payment_type TEXT,lessons_count INTEGER,price_per_lesson INTEGER,subtotal INTEGER,discount_percent INTEGER,package_discount_amount INTEGER,promo_discount_amount INTEGER,total_amount INTEGER,status TEXT,created_at TEXT,confirmed_at TEXT,lesson_id INTEGER);
CREATE TABLE lesson_packages(id INTEGER PRIMARY KEY,payment_id INTEGER,user_id INTEGER,study_goal TEXT,subject TEXT,lessons_total INTEGER,lessons_used INTEGER,price_per_lesson INTEGER,discount_percent INTEGER,amount_paid INTEGER,status TEXT,source_type TEXT,created_at TEXT);''');c.commit();c.close()
   f=next(x for x in ast.parse((ROOT/'database.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='confirm_manual_lesson_payment');env={'connect':connect,'now_iso':lambda:'2026-10-31T12:00:00'};exec(compile(ast.Module(body=[f],type_ignores=[]),'actual-function','exec'),env);barrier=threading.Barrier(2)
   def call(_):barrier.wait(timeout=5);return env[f.name](1,actor_id=99,source='TEST')
   with concurrent.futures.ThreadPoolExecutor(2) as pool:r=list(pool.map(call,range(2)))
   self.assertEqual(r[0],r[1]);c=connect();self.assertEqual(c.execute('SELECT COUNT(*),SUM(total_amount) FROM payments').fetchone()[:],(1,3000));self.assertEqual(c.execute('SELECT COUNT(*) FROM lesson_packages').fetchone()[0],1);self.assertEqual(c.execute('SELECT actor_id FROM lesson_payment_confirmations').fetchone()[0],99)
   with self.assertRaises(ValueError):env[f.name](2,0)
   c.execute("INSERT INTO payments(lesson_id,status,total_amount,lessons_count) VALUES(2,'WAITING',9000,3)");c.commit();c.close()
   with self.assertRaisesRegex(ValueError,'linked_invoice_requires_review'):env[f.name](2)
   c=connect();self.assertEqual(c.execute("SELECT COUNT(*) FROM payments WHERE status='PAID'").fetchone()[0],1);c.close()
if __name__=='__main__':unittest.main()
