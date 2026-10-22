from urllib.parse import urlparse,parse_qs
from web_backend import receipt_review_tools as receipts


class ReceiptToolsMixin:
    def do_GET(self):
        u=urlparse(self.path)
        if u.path!='/api/teacher/finance/receipt/details':return super().do_GET()
        if not self._teacher():return self._json(401,{'error':'unauthorized'})
        try:return self._json(200,receipts.details(parse_qs(u.query).get('payment_id',['0'])[0]))
        except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})
        except Exception as e:
            print('[web-api] receipt details:',type(e).__name__,flush=True);return self._json(500,{'error':'server_error'})

    def do_POST(self):
        path=urlparse(self.path).path
        if path not in {'/api/teacher/finance/receipt/inspect','/api/teacher/finance/receipt/review'}:return super().do_POST()
        if not self._same_origin_write():return self._json(403,{'error':'cross_origin_forbidden'})
        teacher=self._teacher()
        if not teacher:return self._json(401,{'error':'unauthorized'})
        body=self._body()
        if not isinstance(body,dict):return self._json(400,{'error':'invalid_json'})
        try:
            if path.endswith('/inspect'):result=receipts.inspect(body.get('receipt_id'))
            else:
                # Existing clients keep the original review route and behaviour.
                if not body.get('paid_on'):
                    from web_backend import finance_receipts
                    result=finance_receipts.review(body.get('payment_id'),body.get('action'))
                else:result=receipts.review(body.get('payment_id'),body.get('action'),body.get('paid_on'),teacher['admin_telegram_id'],body.get('note',''),body.get('acknowledged') is True)
            return self._json(200,result)
        except (ValueError,TypeError) as e:return self._json(409,{'error':str(e)})
        except Exception as e:
            print('[web-api] receipt tools:',type(e).__name__,flush=True);return self._json(500,{'error':'server_error'})
