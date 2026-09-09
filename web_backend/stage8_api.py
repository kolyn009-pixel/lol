"""Stage 8 API: teacher finance and editable pricing."""
from __future__ import annotations
from web_backend.finance_pricing import list_prices,set_price,list_overrides,set_override,delete_override,list_packages,save_package,quote,package_quote,history

class Stage8Mixin:
    def stage8_get(self,path,q):
        if not path.startswith('/api/teacher/finance/'):return False
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:
            if path=='/api/teacher/finance/prices':return self._json(200,{'items':list_prices()})
            if path=='/api/teacher/finance/overrides':
                uid=q.get('user_id',[None])[0];return self._json(200,{'items':list_overrides(int(uid) if uid not in (None,'') else None)})
            if path=='/api/teacher/finance/packages':return self._json(200,{'items':list_packages()})
            if path=='/api/teacher/finance/quote':return self._json(200,quote(int(q.get('user_id',['0'])[0]),q.get('tariff_key',[''])[0],q.get('duration_minutes',[60])[0]))
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
            if path=='/api/teacher/finance/price':
                r=set_price(body.get('tariff_key'),body.get('amount'),body.get('title'),body.get('subject'),body.get('education_type'),body.get('study_goal'),body.get('duration_minutes',60),body.get('active',True));return self._json(200,r)
            if path=='/api/teacher/finance/override':
                r=set_override(body.get('user_id'),body.get('tariff_key'),body.get('amount'),body.get('note'),body.get('active',True));return self._json(200,r)
            if path=='/api/teacher/finance/override/delete':
                r=delete_override(body.get('user_id'),body.get('tariff_key'));return self._json(200,r)
            if path=='/api/teacher/finance/package':
                r=save_package(body.get('code'),body.get('title'),body.get('lessons_count'),body.get('discount_percent',0),body.get('fixed_total'),body.get('tariff_key'),body.get('active',True),body.get('sort_order',100));return self._json(200,r)
        except ValueError as exc:return self._json(400,{'error':str(exc)})
        except Exception as exc:print('[web-api] finance POST error:',repr(exc),flush=True);return self._json(500,{'error':'server_error'})
        return False
