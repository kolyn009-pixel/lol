"""Local receipt assistance. Recognition never confirms a bank transfer."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import database

_ocr_slots=threading.BoundedSemaphore(2)
_review_lock=threading.RLock()


def ensure_schema():
    c=database.connect()
    try:
        c.executescript('''CREATE TABLE IF NOT EXISTS receipt_inspections(
          receipt_id INTEGER PRIMARY KEY,file_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,checked_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_receipt_inspection_sha ON receipt_inspections(file_sha256);
        CREATE TABLE IF NOT EXISTS receipt_review_dates(
          payment_id INTEGER PRIMARY KEY,paid_on TEXT NOT NULL,teacher_id TEXT NOT NULL,
          requested_at TEXT NOT NULL,reviewed_at TEXT,note TEXT NOT NULL DEFAULT '');''');c.commit()
    finally:c.close()


def today():
    from core.lesson_time import lesson_timezone
    return datetime.now(lesson_timezone()).date()


def paid_date(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(value)):raise ValueError()
        d=date.fromisoformat(value)
    except (TypeError,ValueError):raise ValueError('Укажите дату фактической оплаты.') from None
    if d>today():raise ValueError('Дата оплаты не может быть в будущем.')
    return d.isoformat()


def parse_text(text):
    text=str(text or '')[:50000].replace('\u00a0',' ').replace('\u202f',' ')
    lines=[re.sub(r'\s+',' ',s).strip() for s in text.splitlines() if s.strip()]
    amounts=[]
    money=r'(\d[\d ]{0,12}(?:[.,]\d{2})?)\s*(?:₽|руб(?:\.|лей|ля)?|RUB)?'
    for i,line in enumerate(lines):
        m=re.search(r'^(?:сумма(?: перевода| операции| платежа)?|итого|total)\s*[:—–-]?\s*'+money+r'\s*$',line,re.I)
        if not m and re.fullmatch(r'(?:сумма(?: перевода| операции| платежа)?|итого|total)\s*:?',line,re.I) and i+1<len(lines):
            m=re.fullmatch(money,lines[i+1],re.I)
        if m:
            try:
                n=int(Decimal(m[1].replace(' ','').replace(',','.'))*100)
                if 0<n<=10000000000:amounts.append(n)
            except (ValueError,InvalidOperation):pass
    amounts=sorted(set(amounts));low=text.lower()
    failed=bool(re.search(r'не выполнен|не исполнен|отклон[её]н|отмен[её]н|возврат|неуспеш|failed|cancelled|rejected',low))
    pending=bool(re.search(r'в обработке|обрабатывается|ожидает|pending|processing',low))
    success=bool(re.search(r'успешно|выполнен|исполнен|заверш[её]н|successful|completed',low))
    status='FAILED' if failed else 'PENDING' if pending else 'SUCCESS_TEXT' if success else 'UNKNOWN'
    dates=[]
    for d,m,y in re.findall(r'\b(\d{2})[./](\d{2})[./](20\d{2})\b',text):
        try:dates.append(date(int(y),int(m),int(d)).isoformat())
        except ValueError:pass
    dates=sorted(set(dates));receiver=None
    for i,line in enumerate(lines):
        m=re.match(r'^(?:получатель|имя получателя|кому)\s*[:—–-]?\s*(.*)$',line,re.I)
        if m:
            receiver=(m[1] or (lines[i+1] if i+1<len(lines) else ''))[:150] or None;break
    return {'amount_kopeks':amounts[0] if len(amounts)==1 else None,'amount_candidates':amounts,
      'paid_on':dates[0] if len(dates)==1 else None,'recipient':receiver,'transfer_status':status,
      'text_excerpt':text[:12000]}


def _run(args,timeout=18):
    # Native parsers receive bounded local files, no URLs or shell commands.
    limit=shutil.which('prlimit')
    if limit:args=[limit,'--as=805306368','--cpu=15','--fsize=16777216','--',*args]
    return subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=timeout)


def extract(data):
    if len(data)>8*1024*1024:raise ValueError('Чек больше 8 МБ. Откройте его и проверьте вручную.')
    pdf=data.startswith(b'%PDF-');image=data.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n',b'RIFF'))
    if not pdf and not image:raise ValueError('Формат не поддерживается для распознавания. Проверьте файл вручную.')
    with tempfile.TemporaryDirectory(prefix='adelia-receipt-') as tmp:
        root=Path(tmp);source=root/('receipt.pdf' if pdf else 'receipt.img');source.write_bytes(data)
        if pdf and shutil.which('pdftotext'):
            out=root/'native.txt'
            try:
                _run(['pdftotext','-f','1','-l','2','-layout',str(source),str(out)])
                text=out.read_bytes()[:50000].decode('utf-8','replace')
                if len(text.strip())>=40:return text,'PDF_TEXT'
            except (OSError,subprocess.SubprocessError):pass
        if not shutil.which('tesseract'):return '', 'OCR_UNAVAILABLE'
        pictures=[source]
        if pdf:
            if not shutil.which('pdftoppm'):return '', 'OCR_UNAVAILABLE'
            _run(['pdftoppm','-f','1','-l','2','-scale-to','1800','-png',str(source),str(root/'page')])
            pictures=sorted(root.glob('page-*.png'))[:2]
        texts=[]
        for n,pic in enumerate(pictures):
            out=root/('ocr-'+str(n))
            _run(['tesseract',str(pic),str(out),'-l','rus+eng','--psm','6'],timeout=22)
            texts.append(out.with_suffix('.txt').read_bytes()[:50000].decode('utf-8','replace'))
        return '\n'.join(texts)[:50000],'OCR'


def _payment(pid):
    c=database.connect()
    try:
        row=c.execute('SELECT * FROM payments WHERE id=?',(int(pid),)).fetchone()
        if not row:raise ValueError('Платёж не найден.')
        return dict(row)
    finally:c.close()


def decorate(rid,result,payment):
    r=dict(result);warnings=[];amount=r.get('amount_kopeks')
    expected=int(Decimal(str(payment['total_amount']))*100)
    if amount is None:warnings.append('Сумма не распознана однозначно — сверьте её вручную.')
    elif amount!=expected:warnings.append('Сумма в чеке отличается от суммы платежа.')
    if r.get('transfer_status')!='SUCCESS_TEXT':warnings.append('В чеке не найдено однозначного указания на успешный перевод.')
    if not r.get('recipient'):warnings.append('Получатель не распознан — проверьте реквизиты вручную.')
    else:warnings.append('Сверьте распознанного получателя со своими реквизитами.')
    c=database.connect()
    try:
        duplicates=c.execute('''SELECT i.receipt_id,r.payment_id,p.status FROM receipt_inspections i
          JOIN receipts r ON r.id=i.receipt_id JOIN payments p ON p.id=r.payment_id
          WHERE i.file_sha256=? AND i.receipt_id<>? AND r.payment_id<>? ORDER BY i.receipt_id DESC LIMIT 10''',
          (r.get('sha256',''),int(rid),int(payment['id']))).fetchall()
    finally:c.close()
    r['duplicates']=[dict(x) for x in duplicates]
    if duplicates:warnings.append('Такой же файл уже прикреплён к другому платежу.')
    r.update(expected_kopeks=expected,warnings=warnings,bank_verified=False)
    return r


def inspect(receipt_id):
    ensure_schema();rid=int(receipt_id)
    from web_backend import receipt_cloud_archive
    item=receipt_cloud_archive._receipt(rid)
    if not item:raise ValueError('Чек не найден.')
    payment=_payment(item['payment_id']);c=database.connect()
    try:cached=c.execute('SELECT result_json FROM receipt_inspections WHERE receipt_id=?',(rid,)).fetchone()
    finally:c.close()
    if cached:return decorate(rid,json.loads(cached['result_json']),payment)
    if not _ocr_slots.acquire(blocking=False):raise ValueError('Распознавание занято. Повторите через несколько секунд.')
    try:
        data=receipt_cloud_archive._receipt_bytes(item)
        if not data:raise ValueError('Файл чека недоступен. Откройте его вручную.')
        digest=hashlib.sha256(data).hexdigest()
        try:text,method=extract(data)
        except (OSError,subprocess.SubprocessError):text,method='','UNREADABLE'
        result={**parse_text(text),'method':method,'sha256':digest,'checked_at':database.now_iso()}
        # Missing OCR dependencies are retryable after installation.
        if method!='OCR_UNAVAILABLE':
            c=database.connect()
            try:c.execute('INSERT OR REPLACE INTO receipt_inspections VALUES(?,?,?,?)',(rid,digest,json.dumps(result,ensure_ascii=False),result['checked_at']));c.commit()
            finally:c.close()
        return decorate(rid,result,payment)
    finally:_ocr_slots.release()


def details(payment_id):
    ensure_schema();p=_payment(payment_id);c=database.connect()
    try:
        rows=c.execute('SELECT id,status,file_type,created_at FROM receipts WHERE payment_id=? ORDER BY id DESC',(p['id'],)).fetchall()
        audit=c.execute('SELECT * FROM receipt_review_dates WHERE payment_id=?',(p['id'],)).fetchone()
        lessons=c.execute('SELECT id,start_time,payment_status FROM lessons WHERE payment_id=? OR id=? ORDER BY start_time',(p['id'],p.get('lesson_id') or 0)).fetchall()
    finally:c.close()
    return {'payment_id':p['id'],'status':p['status'],'total_amount':p['total_amount'],
      'confirmed_at':p.get('confirmed_at'),'paid_on':audit['paid_on'] if audit else None,
      'today':today().isoformat(),'receipts':[dict(r) for r in rows],'lessons':[dict(r) for r in lessons],
      'ocr_ready':bool(shutil.which('tesseract') and shutil.which('pdftotext'))}


def review(payment_id,action,paid_on,teacher_id,note='',acknowledged=False):
    """Keep the existing crediting path and preserve a separate factual payment date.

    The date reservation precedes crediting so retries after process failure keep
    the same date. It is displayed as paid only when payments.status is PAID.
    confirmed_at/reviewed_at retain the actual audit timestamps.
    """
    ensure_schema();pid=int(payment_id);action=str(action or '').upper()
    from web_backend import finance_receipts
    if action!='APPROVE':return finance_receipts.review(pid,action)
    day=paid_date(paid_on);note=str(note or '').strip()[:1000]
    with _review_lock:
        c=database.connect()
        try:
            c.execute('BEGIN IMMEDIATE');p=c.execute('SELECT * FROM payments WHERE id=?',(pid,)).fetchone()
            if not p:raise ValueError('Платёж не найден.')
            if p['status']=='REVERSED':raise ValueError('Подтверждение платежа уже отменено.')
            previous=c.execute('SELECT * FROM receipt_review_dates WHERE payment_id=?',(pid,)).fetchone()
            if previous and previous['paid_on']!=day and p['status']=='PAID':raise ValueError('Для этого подтверждения уже сохранена другая дата оплаты.')
            if p['status']=='PAID' and not previous:raise ValueError('Оплата уже подтверждена. Историческую дату нельзя менять повторным подтверждением.')
            check=c.execute('''SELECT i.receipt_id,i.result_json,i.file_sha256 FROM receipt_inspections i JOIN receipts r ON r.id=i.receipt_id
              WHERE r.payment_id=? ORDER BY r.id DESC LIMIT 1''',(pid,)).fetchone()
            if check:
                parsed=json.loads(check['result_json']);mismatch=parsed.get('amount_kopeks') not in (None,int(Decimal(str(p['total_amount']))*100))
                duplicate=c.execute('''SELECT 1 FROM receipt_inspections i JOIN receipts r ON r.id=i.receipt_id
                  JOIN payments p ON p.id=r.payment_id WHERE i.file_sha256=? AND p.id<>? AND p.status='PAID' LIMIT 1''',(check['file_sha256'],pid)).fetchone()
                bad=parsed.get('transfer_status') in ('FAILED','PENDING')
                if (mismatch or duplicate or bad) and (not acknowledged or len(note)<5):raise ValueError('Есть несоответствие в чеке. Сверьте зачисление в банке и укажите причину подтверждения.')
            if not previous:c.execute('INSERT INTO receipt_review_dates VALUES(?,?,?,?,NULL,?)',(pid,day,str(teacher_id),database.now_iso(),note))
            elif p['status']!='PAID':c.execute('UPDATE receipt_review_dates SET paid_on=?,teacher_id=?,note=? WHERE payment_id=?',(day,str(teacher_id),note,pid))
            c.commit()
        except BaseException:c.rollback();raise
        finally:c.close()
        result=finance_receipts.review(pid,action)
        c=database.connect()
        try:
            c.execute('UPDATE receipt_review_dates SET reviewed_at=COALESCE(reviewed_at,?) WHERE payment_id=?',(database.now_iso(),pid));c.commit()
        finally:c.close()
        return {**result,'paid_on':day}
