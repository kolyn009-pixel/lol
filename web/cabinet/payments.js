/* Кабинет «Журнал»: Оплаты преподавателя. Эндпоинты старого кабинета; каждый блок грузится и рисуется независимо. */
(function () {
  'use strict';
  window.__lpNoReload = true;
  var T = '/app/teacher.html';
  var MENU = window.C && C.TEACHER_MENU || [];
  var UNPAID = ['AWAITING_PAYMENT', 'UNPAID', 'WAITING'];
  var DEAD = ['CANCELLED', 'LATE_CANCELLED', 'REJECTED', 'SICKNESS', 'NO_SHOW'];
  var PSTAT = { PAID: 'Оплачено', WAITING: 'Ожидает оплаты', PENDING: 'На проверке', REVERSED: 'Подтверждение отменено', RECEIPT_SENT: 'Чек отправлен' };
  var MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var el = function (t, c, x) { return C.el(t, c, x); };
  var up = function (s) { return String(s == null ? '' : s).toUpperCase(); };
  var sec = {}, lessons = [], students = [], fin = {}, openUser = null, expanded = {}, firstLessons = true;

  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function rub(n) { return num(n).toLocaleString('ru-RU') + ' ₽'; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T00:00:00'; }
  function whenText(s) {
    var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/); if (!m) return '';
    return Number(m[3]) + ' ' + MON[Number(m[2]) - 1] + (m[4] ? ', ' + m[4] + ':' + m[5] : '');
  }
  function dateText(s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + '.' + m[2] + '.' + m[1] : ''; }
  function plural(n, a, b, c) { n = Math.abs(n) % 100; var m = n % 10; return n > 10 && n < 20 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c; }
  function cnt(n, a, b, c) { return n + ' ' + plural(n, a, b, c); }
  function errText(e) {
    var map = { unauthorized: 'Нужно войти заново.', server_error: 'Сервер не справился. Попробуйте ещё раз.', cross_origin_forbidden: 'Запрос отклонён. Обновите страницу.', payment_not_found: 'Платёж не найден.', receipt_not_found: 'Чек не найден.', invalid_action: 'Неизвестное действие.', payment_not_waiting: 'Платёж уже обработан. Обновите страницу.', not_waiting: 'Чек уже обработан. Обновите страницу.' };
    var m = e && e.message || ''; return map[m] || (/^[a-z_0-9]+$/.test(m) ? 'Не получилось выполнить действие. Обновите страницу.' : m || 'Не получилось. Попробуйте ещё раз.');
  }
  function lStart(l) { return l.start_time || l.start_at || ''; }
  function lName(l) { return l.name || l.student_name || 'Ученик без имени'; }
  function lPrice(l) { var v = num(l.price != null ? l.price : l.lesson_price != null ? l.lesson_price : l.amount); return v > 0 ? v : 0; }
  function isPast(l) { var d = new Date(String(lStart(l)).replace(' ', 'T')); return !isNaN(d) && d.getTime() < Date.now(); }

  function box(key, num_, title) {
    var s = C.section(num_, title), b = el('div', 'pay-body'); b.setAttribute('aria-live', 'polite'); s.appendChild(b); sec[key] = { s: s, b: b }; return s;
  }
  function skel(key) { sec[key].b.replaceChildren(el('div', 'c-skel')); }
  function fail(key, e, retry) { sec[key].b.replaceChildren(C.error(errText(e), retry)); }
  function auth(e) { if (e && e.status === 401) { location.replace(T); return true; } return false; }

  /* ---- 01 ждут оплаты ---- */
  function loadLessons() {
    if (firstLessons) skel('wait'); var now = new Date();
    return C.api('/teacher/crm/schedule?limit=500&start=' + iso(new Date(now.getTime() - 30 * 864e5)) + '&end=' + iso(new Date(now.getTime() + 14 * 864e5))).then(function (d) {
      lessons = (d && d.items || []).filter(function (l) { return l && l.id != null && UNPAID.indexOf(up(l.payment_status)) >= 0 && DEAD.indexOf(up(l.lesson_status)) < 0; });
      firstLessons = false; paintWait();
    }, function (e) { if (!auth(e)) fail('wait', e, loadLessons); });
  }
  function paintWait() {
    var b = sec.wait.b;
    if (!lessons.length) { b.replaceChildren(C.empty('Неоплаченных занятий нет. Всё сошлось.')); return; }
    var by = {}, order = [];
    lessons.forEach(function (l) { var k = l.user_id != null ? 'u' + l.user_id : 'n' + lName(l); if (!by[k]) { by[k] = { key: k, name: lName(l), items: [] }; order.push(by[k]); } by[k].items.push(l); });
    order.forEach(function (g) {
      g.items.sort(function (a, c) { var pa = isPast(a), pc = isPast(c); if (pa !== pc) return pa ? -1 : 1; return String(lStart(a)) < String(lStart(c)) ? -1 : 1; });
      g.past = g.items.filter(isPast).length; g.sum = g.items.reduce(function (t, l) { return t + lPrice(l); }, 0); g.noPrice = g.items.filter(function (l) { return !lPrice(l); }).length;
    });
    order.sort(function (a, c) { if ((a.past > 0) !== (c.past > 0)) return a.past > 0 ? -1 : 1; return String(lStart(a.items[0])) < String(lStart(c.items[0])) ? -1 : 1; });
    var f = document.createDocumentFragment(), total = lessons.reduce(function (t, l) { return t + lPrice(l); }, 0);
    f.appendChild(el('p', 'pay-sumline', cnt(lessons.length, 'занятие', 'занятия', 'занятий') + ' · ' + cnt(order.length, 'ученик', 'ученика', 'учеников') + (total ? ' · ' + rub(total) : '')));
    order.forEach(function (g, i) {
      if (expanded[g.key] == null) expanded[g.key] = i < 3;
      var wrap = el('div', 'pay-group'), h = el('button', 'pay-ghead'); h.type = 'button'; h.setAttribute('aria-expanded', String(expanded[g.key]));
      var info = el('span', 'pay-info'); info.appendChild(el('span', 'pay-who', g.name));
      var m = el('span', 'pay-meta'); m.appendChild(el('span', '', cnt(g.items.length, 'занятие', 'занятия', 'занятий')));
      if (g.past) m.appendChild(el('span', 'pay-debt', 'прошло: ' + g.past));
      if (g.noPrice) m.appendChild(el('span', '', 'без цены: ' + g.noPrice));
      info.appendChild(m); h.appendChild(info); h.appendChild(el('span', 'pay-sum', g.sum ? rub(g.sum) : '—'));
      h.appendChild(el('span', 'pay-arrow', expanded[g.key] ? '−' : '+'));
      var list = el('div', 'pay-glist'); list.hidden = !expanded[g.key];
      h.addEventListener('click', function () { expanded[g.key] = !expanded[g.key]; list.hidden = !expanded[g.key]; h.setAttribute('aria-expanded', String(expanded[g.key])); h.lastChild.textContent = expanded[g.key] ? '−' : '+'; });
      g.items.forEach(function (l) {
        var r = el('article', 'pay-row'), info2 = el('div', 'pay-info');
        var past = isPast(l); info2.appendChild(el('div', 'pay-who', whenText(lStart(l)) || 'Дата не указана'));
        var mt = el('div', 'pay-meta'); mt.appendChild(el('span', past ? 'pay-debt' : '', past ? 'прошло' : 'впереди'));
        var sj = C.subjectLabel(l.subject); if (sj) mt.appendChild(el('span', '', sj)); info2.appendChild(mt); r.appendChild(info2);
        r.appendChild(el('div', 'pay-sum', lPrice(l) ? rub(lPrice(l)) : 'без цены'));
        var a = el('div', 'c-actions');
        if (window.AdeliaLessonPayment) a.insertAdjacentHTML('beforeend', window.AdeliaLessonPayment.buttons({ id: l.id, name: lName(l), start_time: lStart(l), price: lPrice(l), payment_status: l.payment_status, payment_wait_confirmed_at: l.payment_wait_confirmed_at }));
        r.appendChild(a); list.appendChild(r);
      });
      wrap.append(h, list); f.appendChild(wrap);
    });
    b.replaceChildren(f);
  }

  /* ---- 02 чеки ---- */
  var receipts = [];
  function loadReceipts() {
    skel('rec');
    return C.api('/teacher/finance/receipts?status=WAITING&limit=200').then(function (d) {
      receipts = (d && d.items || []).filter(function (x) { return x && up(x.receipt_status || 'WAITING') === 'WAITING' && up(x.payment_status) !== 'REVERSED'; });
      paintReceipts(); C.setBell(receipts.length);
    }, function (e) { if (!auth(e)) fail('rec', e, loadReceipts); });
  }
  function paintReceipts() {
    var b = sec.rec.b; if (!receipts.length) { b.replaceChildren(C.empty('Чеков на проверке нет.')); return; }
    var f = document.createDocumentFragment(), state = el('div'); state.setAttribute('aria-live', 'polite');
    receipts.forEach(function (x) {
      var r = el('article', 'pay-row'), info = el('div', 'pay-info');
      info.appendChild(el('div', 'pay-who', x.name || 'Ученик без имени'));
      var meta = el('div', 'pay-meta'), sj = C.subjectLabel(x.subject); if (sj) meta.appendChild(el('span', '', sj));
      if (num(x.lessons_count)) meta.appendChild(el('span', '', cnt(num(x.lessons_count), 'занятие', 'занятия', 'занятий')));
      var d = whenText(x.receipt_created_at || x.payment_created_at); if (d) meta.appendChild(el('span', '', 'Отправлено ' + d));
      info.appendChild(meta); r.appendChild(info);
      var amt = x.total_amount != null ? x.total_amount : x.amount; r.appendChild(el('div', 'pay-sum', num(amt) ? rub(amt) : 'сумма не указана'));
      var a = el('div', 'c-actions'), view = null;
      if (x.can_view_file !== false && x.receipt_id != null) { view = C.button('Посмотреть чек', 'secondary', function () { preview(x); }); a.appendChild(view); }
      var ok = C.button('Подтвердить', 'primary', function () { review(x, 'APPROVE', a, state); }), no = C.button('Отклонить', 'secondary', function () { review(x, 'REJECT', a, state); });
      a.append(ok, no); r.appendChild(a); f.appendChild(r);
    });
    f.appendChild(state); b.replaceChildren(f);
  }
  function fileUrl(x) { return '/api/teacher/finance/receipt/file?receipt_id=' + encodeURIComponent(x.receipt_id); }
  function preview(x) {
    var body = el('div', 'pay-prev'), url = fileUrl(x), pdf = /pdf/i.test(String(x.file_type || ''));
    var link = el('a', 'c-btn', 'Открыть в новой вкладке'); link.href = url; link.target = '_blank'; link.rel = 'noopener';
    if (!pdf) {
      var img = el('img', 'pay-img'); img.alt = 'Чек: ' + (x.name || 'ученик'); img.src = url;
      img.addEventListener('error', function () { img.replaceWith(el('p', 'c-empty', 'Это не картинка или файл не открылся. Откройте его в новой вкладке.')); });
      body.appendChild(img);
    } else body.appendChild(el('p', 'c-empty', 'Чек в формате PDF.'));
    body.appendChild(link);
    C.modal({ title: 'Чек: ' + (x.name || 'ученик'), body: body, actions: [{ text: 'Закрыть', kind: 'secondary' }] });
  }
  function postLong(path, body) {
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 65000);
    return fetch('/api' + path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ctl.signal }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) { var e = new Error(j.detail || j.error || 'Не получилось.'); e.status = r.status; throw e; } return j; });
    }, function (er) { var e = new Error(er && er.name === 'AbortError' ? 'Сервер долго отвечает. Проверьте статус чека и обновите страницу.' : 'Нет связи с сервером.'); e.status = 0; throw e; }).then(function (v) { clearTimeout(t); return v; }, function (e) { clearTimeout(t); throw e; });
  }
  function review(x, action, box, state) {
    function go() {
      var all = box.querySelectorAll('button,a'); [].forEach.call(all, function (b) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); }); state.replaceChildren(el('p', 'c-empty', action === 'APPROVE' ? 'Подтверждаю…' : 'Отклоняю…'));
      postLong('/teacher/finance/receipt/review', { payment_id: Number(x.payment_id), action: action }).then(function () {
        C.toast(action === 'APPROVE' ? 'Оплата подтверждена.' : 'Чек отклонён. Ученик сможет отправить новый.'); fin = {}; return Promise.all([loadReceipts(), loadTotals(), loadStudents(), loadLessons()]);
      }, function (e) { [].forEach.call(all, function (b) { b.disabled = false; b.removeAttribute('aria-disabled'); }); if (!auth(e)) state.replaceChildren(C.error(errText(e))); });
    }
    if (action === 'REJECT') C.modal({ title: 'Отклонить чек?', body: 'Ученик сможет отправить новый файл.', actions: [{ text: 'Отмена', kind: 'secondary' }, { text: 'Отклонить', kind: 'primary', onClick: function () { go(); } }] });
    else go();
  }

  /* ---- 03 ученики ---- */
  var query = '';
  function loadStudents() {
    if (!students.length) skel('stu');
    return C.api('/teacher/crm/students?limit=500').then(function (d) { students = (d && d.items || []).filter(function (u) { return u && u.id != null; }); paintStudents(); },
      function (e) { if (!auth(e)) fail('stu', e, loadStudents); });
  }
  function paintStudents() {
    var b = sec.stu.b; if (openUser != null) { b.replaceChildren(studentCard(openUser)); return; }
    if (!students.length) { b.replaceChildren(C.empty('Учеников пока нет.')); return; }
    var f = document.createDocumentFragment();
    if (students.length > 8) {
      var inp = el('input'); inp.type = 'search'; inp.placeholder = 'Найти ученика'; inp.setAttribute('aria-label', 'Найти ученика'); inp.value = query;
      inp.addEventListener('input', function () { query = inp.value; var p = inp.selectionStart; fillStudents(list); inp.focus(); inp.setSelectionRange(p, p); }); f.appendChild(inp);
    }
    var list = el('div'); f.appendChild(list); fillStudents(list); b.replaceChildren(f);
  }
  function fillStudents(list) {
    var q = query.trim().toLowerCase();
    var rows = students.filter(function (u) { return !q || String(u.name || '').toLowerCase().indexOf(q) >= 0; }).sort(function (a, c) {
      var da = num(a.payment_waiting) > 0, dc = num(c.payment_waiting) > 0; if (da !== dc) return da ? -1 : 1; return String(a.name || '').localeCompare(String(c.name || ''), 'ru');
    });
    list.replaceChildren(); if (!rows.length) list.appendChild(C.empty('Никого не нашли.'));
    rows.forEach(function (u) {
      var debt = num(u.payment_waiting), b = el('button', 'pay-stu'); b.type = 'button'; var nm = u.name || 'Ученик без имени';
      b.appendChild(el('span', 'pay-who', nm)); var m = el('span', 'pay-meta'); m.appendChild(el('span', debt > 0 ? 'pay-debt' : '', debt > 0 ? 'Ждёт оплаты ' + rub(debt) : 'Долга нет')); b.appendChild(m);
      b.appendChild(el('span', 'pay-arrow', '→')); b.addEventListener('click', function () { openUser = u.id; paintStudents(); sec.stu.s.scrollIntoView({ block: 'start' }); }); list.appendChild(b);
    });
  }
  function studentCard(uid) {
    var w = el('div', 'pay-card'), u = students.filter(function (x) { return x.id === uid; })[0] || {};
    w.appendChild(C.button('← Все ученики', 'text', function () { openUser = null; paintStudents(); })); w.appendChild(el('h2', 'pay-h', u.name || 'Ученик без имени'));
    var body = el('div'); body.setAttribute('aria-live', 'polite'); body.appendChild(el('p', 'c-empty', 'Загружаю…')); w.appendChild(body);
    (fin[uid] ? Promise.resolve(fin[uid]) : C.api('/teacher/finance/student?user_id=' + encodeURIComponent(uid))).then(function (f) {
      fin[uid] = f; body.replaceChildren(); var t = f.totals || {}, st = el('div', 'c-stats');
      [['Оплачено', rub(t.paid)], ['Ожидается', rub(t.waiting)], ['Осталось занятий', String(num(t.lessons_left))]].forEach(function (p) { var sp = el('span'); sp.appendChild(document.createTextNode(p[0] + ': ')); sp.appendChild(el('b', '', p[1])); st.appendChild(sp); });
      body.appendChild(st); body.appendChild(el('p', 'c-label', 'ИСТОРИЯ ОПЛАТ'));
      var pays = f.payments || []; if (!pays.length) body.appendChild(C.empty('Платежей нет.'));
      pays.forEach(function (p) {
        var r = el('article', 'pay-row'), info = el('div', 'pay-info'), k = up(p.status);
        info.appendChild(el('div', 'pay-who', (C.subjectLabel(p.subject) || 'Оплата') + ' · ' + (PSTAT[k] || p.status || 'без статуса')));
        var mt = el('div', 'pay-meta'), dd = dateText(p.confirmed_at || p.created_at); if (dd) mt.appendChild(el('span', '', dd));
        if (num(p.lessons_count)) mt.appendChild(el('span', '', cnt(num(p.lessons_count), 'занятие', 'занятия', 'занятий'))); info.appendChild(mt); r.appendChild(info);
        r.appendChild(el('div', 'pay-sum', rub(p.total_amount))); var a = el('div', 'c-actions');
        if (window.AdeliaPaymentReversal) a.insertAdjacentHTML('beforeend', window.AdeliaPaymentReversal.button(p.id, k));
        r.appendChild(a); body.appendChild(r);
      });
      if (window.AdeliaPaymentReversal) window.AdeliaPaymentReversal.bind(body, function () { fin = {}; return Promise.all([loadStudents(), loadTotals(), loadLessons()]); });
    }, function (e) { if (!auth(e)) body.replaceChildren(C.error(errText(e), function () { paintStudents(); })); });
    return w;
  }

  /* ---- 04 итоги ---- */
  function loadTotals() {
    skel('tot');
    return C.api('/teacher/finance/dashboard?period=month').then(function (d) {
      var g = el('div', 'pay-totals'), paid = d && d.paid || {}, wait = d && d.waiting || {};
      [['Получено', rub(paid.amount), cnt(num(paid.count), 'оплата', 'оплаты', 'оплат')], ['Ожидается', rub(wait.amount), cnt(num(wait.count), 'платёж', 'платежа', 'платежей')]].forEach(function (p) {
        var c = el('div', 'pay-total'); c.append(el('span', 'pay-t-l', p[0]), el('b', 'pay-t-v', p[1]), el('small', '', p[2])); g.appendChild(c);
      });
      var f = document.createDocumentFragment(); f.appendChild(g);
      if (d && d.period && d.period.start) f.appendChild(el('p', 'cab-sub', 'За период ' + dateText(d.period.start) + ' — ' + dateText(d.period.end)));
      sec.tot.b.replaceChildren(f);
    }, function (e) { if (!auth(e)) fail('tot', e, loadTotals); });
  }

  function reloadAll() { fin = {}; return Promise.all([loadLessons(), loadReceipts(), loadStudents(), loadTotals()]); }

  C.boot({
    role: 'teacher', menu: MENU, active: 'payments',
    render: function (main) {
      main.append(el('h1', 'cab-title', 'Оплаты'), el('p', 'cab-sub', 'Кто ждёт оплату, какие чеки проверить и сколько занятий осталось.'));
      main.append(box('wait', '01', 'Ждут оплаты'), box('rec', '02', 'Чеки на подтверждение'), box('stu', '03', 'Ученики и баланс'), box('tot', '04', 'Итоги месяца'));
      document.title = 'Оплаты — Аделия';
      document.addEventListener('adelia:lesson-payment-changed', function () { fin = {}; setTimeout(function () { loadLessons(); loadStudents(); loadTotals(); }, 250); });
      document.addEventListener('adelia:payment-reversed', function () { fin = {}; });
      reloadAll();
    }
  });
})();
