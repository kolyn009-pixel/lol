/* Ученик: «Оплата». API как в старом кабинете: GET /student/finance/overview, /student/payments,
   /student/finance/quote?selection_key&lessons_count[&promo_code]; POST /student/finance/package
   {selection_key, lessons_count, promo_code}, /student/finance/receipt {payment_id, filename, mime_type, content_b64} */
(function () {
  'use strict';
  var A = '/app/', body, fin, hist, loading = false, sel = { key: null, count: 4, promo: '' };
  var PS = { WAITING: 'Ждёт оплаты', PENDING: 'Ждёт оплаты', RECEIPT_SENT: 'Чек проверяется', PAID: 'Оплачено', REVERSED: 'Подтверждение отменено', REJECTED: 'Отклонено', CANCELLED: 'Отменено' };
  function stat(s) { s = String(s || '').toUpperCase(); return PS[s] || s || '—'; }
  function cls(s) { s = String(s || '').toUpperCase(); return s === 'PAID' ? 'ok' : (s === 'REJECTED' || s === 'WAITING' || s === 'PENDING') ? 'due' : ''; }
  function sub(v) { return C.subjectLabel(v); }
  function tname(t) { return [sub(t.subject), C.subjectLabel(t.study_goal)].filter(Boolean).join(' · ') || 'Занятия'; }
  function fdate(v) { var s = S.date(v); return s || ''; }

  function balance() {
    var s = C.section('01', 'Баланс'), b = (fin && fin.balance) || {}, tot = S.num(b.total), l = Math.floor(tot / 60);
    s.appendChild(C.el('div', 'c-big', tot + ' мин'));
    var t = '≈ ' + l + ' ' + S.plural(l, 'занятие', 'занятия', 'занятий') + ' по 60 минут';
    if (S.num(b.bonus) > 0) t += ' · бонусных ' + S.num(b.bonus) + ' мин';
    s.appendChild(C.el('p', 'c-row-s', t)); return s;
  }

  /* ---- чек ---- */
  function receiptBox(pid, method, onDone) {
    var w = C.el('div', 'st-pay-box');
    if (method) w.appendChild(C.el('p', 'st-method', method));
    var inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/jpeg,image/png,application/pdf';
    var out = C.el('div'), b = C.button('Отправить чек', 'primary', function () {
      var f = inp.files && inp.files[0];
      if (!f) { out.replaceChildren(S.note('bad', 'Выбери файл чека.')); return; }
      if (f.size > 8 * 1024 * 1024) { out.replaceChildren(S.note('bad', 'Файл больше 8 МБ.')); return; }
      b.disabled = true; b.textContent = 'Отправляю…';
      S.b64(f).then(function (c) { return C.api('/student/finance/receipt', { method: 'POST', body: { payment_id: +pid, filename: f.name, mime_type: f.type, content_b64: c } }); }).then(function () {
        out.replaceChildren(S.note('ok', 'Чек отправлен. Статус обновится после проверки преподавателем.')); b.remove(); inp.disabled = true; C.toast('Чек отправлен.'); setTimeout(onDone, 900);
      }, function (e) { b.disabled = false; b.textContent = 'Отправить чек'; out.replaceChildren(S.note('bad', e.message || 'Не получилось отправить чек.')); });
    });
    w.append(S.field('Чек: фото, скриншот или PDF до 8 МБ', inp), b, out); return w;
  }

  function waiting() {
    var p = fin && fin.waiting_payment; if (!p || typeof p !== 'object') return null;
    var s = C.section('02', 'Ждёт оплаты'), r = C.el('div', 'c-row'), t = C.el('div', 'c-row-t');
    t.appendChild(C.el('div', 'c-big', S.rub(p.total_amount)));
    t.appendChild(C.el('div', 'c-row-s', 'Платёж #' + p.id + (p.minutes_total ? ' · ' + p.minutes_total + ' мин' : '')));
    r.append(t, C.el('span', 'c-pay ' + cls(p.status), stat(p.status))); s.appendChild(r);
    if (String(p.status).toUpperCase() === 'RECEIPT_SENT') s.appendChild(S.note('', 'Чек у преподавателя на проверке. Ничего больше делать не нужно.'));
    else s.appendChild(receiptBox(p.id, typeof fin.payment_method === 'string' ? fin.payment_method : '', load));
    return s;
  }

  /* ---- тарифы ---- */
  function tariffs() {
    var s = C.section('03', 'Пополнить баланс'), ts = (fin && fin.tariffs) || [];
    if (!ts.length) { s.appendChild(C.empty('Доступных тарифов пока нет. Напиши преподавателю.')); return s; }
    if (sel.key == null || !ts.some(function (t) { return String(t.selection_key) === String(sel.key); })) sel.key = ts[0].selection_key;
    var tsel = document.createElement('select');
    ts.forEach(function (t) { var o = document.createElement('option'); o.value = t.selection_key; o.textContent = tname(t) + ' · ' + S.rub(t.hourly_rate) + '/60 мин · урок ' + t.duration + ' мин'; if (String(t.selection_key) === String(sel.key)) o.selected = true; tsel.appendChild(o); });
    tsel.addEventListener('change', function () { sel.key = tsel.value; res.replaceChildren(); });
    s.appendChild(S.field('Тариф', tsel));
    var cw = C.el('div', 'st-counts'), cnt = document.createElement('input');
    cnt.type = 'number'; cnt.min = 1; cnt.max = 40; cnt.value = sel.count; cnt.addEventListener('input', function () { sel.count = Math.max(1, parseInt(cnt.value, 10) || 1); mark(); });
    function mark() { [].forEach.call(cw.children, function (b) { b.setAttribute('aria-pressed', String(+b.textContent === sel.count)); }); res.replaceChildren(); }
    [1, 2, 4, 6, 10].forEach(function (n) { var b = C.el('button', 'c-btn', String(n)); b.type = 'button'; b.addEventListener('click', function () { sel.count = n; cnt.value = n; mark(); }); cw.appendChild(b); });
    var res = C.el('div'); mark();
    var lab = C.el('p', 'c-label', 'Количество занятий'); s.append(lab, cw, S.field('Другое количество', cnt));
    var pr = document.createElement('input'); pr.type = 'text'; pr.placeholder = 'Если есть'; pr.autocomplete = 'off'; pr.value = sel.promo; pr.addEventListener('input', function () { sel.promo = pr.value.trim(); res.replaceChildren(); });
    s.appendChild(S.field('Промокод', pr));
    s.appendChild(C.button('Рассчитать', 'secondary', function (ev) {
      var b = ev.currentTarget; b.disabled = true; res.replaceChildren(C.el('p', 'c-row-s', 'Считаю…'));
      C.api('/student/finance/quote?selection_key=' + encodeURIComponent(sel.key) + '&lessons_count=' + sel.count + (sel.promo ? '&promo_code=' + encodeURIComponent(sel.promo) : '')).then(function (q) {
        var f = document.createDocumentFragment(), l = [q.lessons_count + ' × ' + q.duration + ' мин = ' + q.minutes_total + ' мин', 'Тариф: ' + S.rub(q.hourly_rate) + ' за 60 мин'];
        if (q.discount_percent) l.push('Скидка за количество: ' + q.discount_percent + '%'); if (q.promo_code) l.push('Промокод: ' + q.promo_code);
        f.append(C.el('div', 'c-big', S.rub(q.total_amount)), C.el('p', 'c-row-s st-quote', l.join(' · ')));
        f.appendChild(C.button('Создать оплату', 'primary', function (e2) {
          var b2 = e2.currentTarget; b2.disabled = true;
          C.api('/student/finance/package', { method: 'POST', body: { selection_key: sel.key, lessons_count: sel.count, promo_code: sel.promo || null } }).then(function (r) {
            var p = r.payment || {}, g = document.createDocumentFragment();
            g.append(S.note('ok', 'Платёж #' + p.id + ' создан: ' + S.rub(p.total_amount) + '. Оплати и прикрепи чек.'), receiptBox(p.id, r.payment_method || '', load)); res.replaceChildren(g);
          }, function (e) { b2.disabled = false; res.appendChild(S.note('bad', e.message || 'Не получилось создать оплату.')); });
        }));
        res.replaceChildren(f);
      }, function (e) { res.replaceChildren(S.note('bad', e.message || 'Не получилось рассчитать.')); }).then(function () { b.disabled = false; });
    }));
    s.appendChild(res); return s;
  }

  function history() {
    var s = C.section('04', 'История оплат'), items = (hist && hist.items) || [], rc = (hist && hist.receipts) || [];
    if (!items.length) s.appendChild(C.empty('Платежей пока нет.'));
    items.forEach(function (x) {
      var r = C.el('div', 'c-row'), t = C.el('div', 'c-row-t');
      t.appendChild(C.el('div', '', (x.payment_type === 'PACKAGE' ? 'Абонемент' : 'Оплата занятия') + (x.minutes_total ? ' · ' + x.minutes_total + ' мин' : '')));
      t.appendChild(C.el('div', 'c-row-s', [fdate(x.created_at), stat(x.status)].filter(Boolean).join(' · ')));
      r.append(t, C.el('strong', 'st-sum', S.rub(x.total_amount))); s.appendChild(r);
    });
    if (rc.length) {
      s.appendChild(C.el('p', 'c-label st-sub', 'Чеки'));
      rc.forEach(function (x) { var r = C.el('div', 'c-row'); r.appendChild(C.el('span', 'c-row-t', 'Чек #' + x.id + (fdate(x.created_at) ? ' · ' + fdate(x.created_at) : ''))); r.appendChild(C.el('span', 'c-row-s', String(x.status || '').toUpperCase() === 'WAITING' ? 'Проверяется' : stat(x.status))); s.appendChild(r); });
    }
    return s;
  }

  function paint() {
    var f = document.createDocumentFragment();
    f.append(C.el('h1', 'cab-title', 'Оплата'), C.el('p', 'cab-sub', 'Баланс, абонементы и чеки'));
    f.appendChild(fin ? balance() : C.error('Не получилось загрузить баланс.', load));
    var w = fin && waiting(); if (w) f.appendChild(w);
    if (fin) f.appendChild(tariffs());
    f.appendChild(hist ? history() : C.error('Не получилось загрузить историю.', load));
    var pos = window.scrollY; body.replaceChildren(f); window.scrollTo(0, pos);
  }

  function load() {
    if (loading) return Promise.resolve(); loading = true;
    return Promise.all([S.go(C.api('/student/finance/overview')), S.go(C.api('/student/payments?limit=50'))]).then(function (r) {
      if (r[0].e && r[1].e) { if (!fin) body.replaceChildren(C.error(r[0].e.message, load)); else C.toast('Не удалось обновить.'); return; }
      fin = r[0].v || fin; hist = r[1].v || hist; paint();
    }, function (e) { if (e.status === 401) location.replace(A); }).then(function () { loading = false; });
  }

  C.boot({
    role: 'student', menu: C.STUDENT_MENU, active: 'pay',
    render: function (main) {
      body = document.createElement('div'); body.setAttribute('aria-live', 'polite');
      for (var i = 0; i < 3; i++) body.appendChild(C.el('div', 'c-skel'));
      main.appendChild(body); document.title = 'Оплата — Аделия'; return load();
    }
  });
})();
