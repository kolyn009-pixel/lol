"""Stage 8 API: teacher finance, actual payments and editable pricing."""
from __future__ import annotations
from web_backend.finance_pricing import list_prices,set_price,list_overrides,list_packages,save_package,history
from web_backend.finance_price_sync import set_override,delete_override,quote,package_quote
from web_backend.finance_reporting import dashboard,student_finance,calendar_analytics
from web_backend.finance_receipts import list_receipts,summary as receipt_summary,review as review_receipt
from web_backend import teacher_invoices

class Stage8Mixin:
    def stage8_get(self,path,q):
        if not path.startswith('/api/teacher/finance/'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:
            if path=='/api/teacher/finance/dashboard':return self._json(200,dashboard(q.get('start',[None])[0],q.get('end',[None])[0],q.get('period',[None])[0]))
            if path=='/api/teacher/finance/calendar-analytics':return self._json(200,calendar_analytics())
            if path=='/api/teacher/finance/receipts':return self._json(200,{'summary':receipt_summary(),'items':list_receipts(q.get('status',['WAITING'])[0],q.get('limit',[100])[0])})
            if path=='/api/teacher/finance/invoices':return self._json(200,teacher_invoices.candidates(q.get('limit',[100])[0]))
            if path=='/api/teacher/finance/student':return self._json(200,student_finance(int(q.get('user_id',['0'])[0])))
            if path=='/api/teacher/finance/prices':return self._json(200,{'items':list_prices()})
            if path=='/api/teacher/finance/overrides':
                uid=q.get('user_id',[None])[0];return self._json(200,{'items':list_overrides(int(uid) if uid not in (None,'') else None)})
            if path=='/api/teacher/finance/packages':return self._json(200,{'items':list_packages()})
            if path=='/api/teacher/finance/quote':
                key=q.get('tariff_key',[None])[0] or None;return self._json(200,quote(int(q.get('user_id',['0'])[0]),key,q.get('duration_minutes',[60])[0]))
            if path=='/api/teacher/finance/package-quote':return self._json(200,package_quote(int(q.get('user_id',['0'])[0]),q.get('code',[''])[0],q.get('tariff_key',[None])[0],q.get('duration_minutes',[60])[0]))
            if path=='/api/teacher/finance/history':return self._json(200,{'items':history(q.get('limit',[200])[0])})
        except ValueError as exc:return self._json(400,{'error':str(exc)})
        except Exception as exc:print('[web-api] finance GET error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False

    def stage8_post(self,path):
        if not path.startswith('/api/teacher/finance/'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        body=self._body()
        if body is None:return self._json(400,{'error':'invalid_json'})
        try:
            if path=='/api/teacher/finance/invoice':return self._json(200,teacher_invoices.issue(body.get('lesson_id')))
            if path=='/api/teacher/finance/receipt/review':return self._json(200,review_receipt(body.get('payment_id'),body.get('action')))
            if path=='/api/teacher/finance/price':return self._json(200,set_price(body.get('tariff_key'),body.get('amount'),body.get('title'),body.get('subject'),body.get('education_type'),body.get('study_goal'),body.get('duration_minutes',60),body.get('active',True)))
            if path=='/api/teacher/finance/override':return self._json(200,set_override(body.get('user_id'),body.get('tariff_key'),body.get('amount'),body.get('note'),body.get('active',True)))
            if path=='/api/teacher/finance/override/delete':return self._json(200,delete_override(body.get('user_id'),body.get('tariff_key')))
            if path=='/api/teacher/finance/package':return self._json(200,save_package(body.get('code'),body.get('title'),body.get('lessons_count'),body.get('discount_percent',0),body.get('fixed_total'),body.get('tariff_key'),body.get('active',True),body.get('sort_order',100)))
        except (ValueError,TypeError) as exc:return self._json(400,{'error':str(exc)})
        except Exception as exc:print('[web-api] finance POST error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
