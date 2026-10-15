"""Run the production checkout implementation against real, isolated SQLite."""
import ast
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]

class Checkout(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'db.sqlite'
  def connect():
   c=sqlite3.connect(self.db,timeout=10);c.row_factory=sqlite3.Row;return c
  self.connect=connect
  c=connect();c.execute('''CREATE TABLE payments(id INTEGER PRIMARY KEY,user_id INTEGER,study_goal TEXT,subject TEXT,payment_type TEXT,lessons_count INTEGER,price_per_lesson INTEGER,subtotal INTEGER,discount_percent INTEGER,package_discount_amount INTEGER,promo_id INTEGER,promo_code TEXT,promo_discount_amount INTEGER,total_amount INTEGER,lesson_id INTEGER,status TEXT,created_at TEXT,minutes_total INTEGER,base_duration_minutes INTEGER,hourly_rate INTEGER,program_id INTEGER)''');c.commit();c.close()
  tree=ast.parse((ROOT/'database.py').read_text(encoding='utf-8'));node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='create_payment')
  scope={'connect':connect,'sqlite3':sqlite3,'now_iso':lambda:'2026-10-15T10:00:00','calculate_package':lambda price,count:{'subtotal':price*count,'total':price*count,'discount_percent':0,'discount_amount':0}}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'database.py','exec'),scope);self.create=scope['create_payment']
 def tearDown(self):self.tmp.cleanup()
 def purchase(self,**kw):
  args=dict(user_id=1,study_goal='SCHOOL',subject='MATH',lessons_count=2,price_per_lesson=1750,minutes_total=120,base_duration_minutes=60,hourly_rate=1750,self_service=True);args.update(kw);return self.create(**args)
 def test_individual_price_and_same_checkout_reuses_invoice(self):
  first=self.purchase();self.assertEqual(first,self.purchase())
  c=self.connect();r=c.execute('SELECT * FROM payments').fetchone();self.assertEqual(r['total_amount'],3500);self.assertEqual(r['minutes_total'],120);c.close()
 def test_parallel_checkouts_are_one_invoice(self):
  barrier=threading.Barrier(2)
  def run(_):barrier.wait();return self.purchase()
  with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(run,range(2)))
  self.assertEqual(ids[0],ids[1]);c=self.connect();self.assertEqual(c.execute('SELECT COUNT(*) FROM payments').fetchone()[0],1);c.close()
 def test_old_receipt_blocks_even_with_newer_waiting_invoice(self):
  old=self.purchase();c=self.connect();c.execute("UPDATE payments SET status='RECEIPT_SENT' WHERE id=?",(old,));c.commit();c.close()
  self.purchase(self_service=False,price_per_lesson=2000)
  with self.assertRaisesRegex(ValueError,'receipt_already_under_review'):self.purchase()
 def test_different_student_tariff_or_minutes_not_reused(self):
  ids={self.purchase(),self.purchase(user_id=2),self.purchase(price_per_lesson=2000),self.purchase(minutes_total=180,base_duration_minutes=90),self.purchase(lesson_id=18)}
  self.assertEqual(len(ids),5)
 def test_paid_invoice_not_reused(self):
  old=self.purchase();c=self.connect();c.execute("UPDATE payments SET status='PAID' WHERE id=?",(old,));c.commit();c.close();self.assertNotEqual(old,self.purchase())

 def test_parent_status_endpoint_checks_link_and_payment_owner(self):
  from types import SimpleNamespace
  own=self.purchase();foreign=self.purchase(user_id=2)
  c=self.connect();c.executescript("CREATE TABLE users(id INTEGER,active INTEGER);INSERT INTO users VALUES(1,1),(2,1);CREATE TABLE parent_accounts(id INTEGER,active INTEGER);INSERT INTO parent_accounts VALUES(7,1),(8,1);CREATE TABLE parent_student_links(parent_id INTEGER,student_id INTEGER);INSERT INTO parent_student_links VALUES(7,1);");c.close()
  def get_payment(pid):
   c=self.connect()
   try:return c.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
   finally:c.close()
  scope={'database':SimpleNamespace(connect=self.connect,get_payment=get_payment)}
  tree=ast.parse((ROOT/'web_backend/student_finance.py').read_text(encoding='utf-8'));node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_payment_owned')
  exec(compile(ast.Module(body=[node],type_ignores=[]),'student_finance.py','exec'),scope)
  scope['student_finance']=SimpleNamespace(_payment_owned=scope['_payment_owned'],_safe_payment=lambda row:{'id':row['id'],'status':row['status']})
  tree=ast.parse((ROOT/'web_backend/payment_hub.py').read_text(encoding='utf-8'));nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'_linked','parent_payment'}]
  exec(compile(ast.Module(body=nodes,type_ignores=[]),'payment_hub.py','exec'),scope)
  self.assertEqual(scope['parent_payment'](7,1,own)['payment']['id'],own)
  with self.assertRaises(PermissionError):scope['parent_payment'](8,1,own)
  with self.assertRaises(PermissionError):scope['parent_payment'](7,1,foreign)
  with self.assertRaises(PermissionError):scope['parent_payment'](7,2,foreign)

if __name__=='__main__':unittest.main()
