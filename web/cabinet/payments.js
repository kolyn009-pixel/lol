/* Кабинет «Журнал»: Оплаты преподавателя. Те же эндпоинты, что в старом кабинете. */
(function () {
  'use strict';
  window.__lpNoReload = true;
  var T = C.classic('/app/teacher.html');
  var MENU = C.TEACHER_MENU;
  var UNPAID = ['AWAITING_PAYMENT', 'UNPAID', 'WAITING'];
  var DEAD = ['CANCELLED', 'LATE_CANCELLED', 'REJECTED', 'SICKNESS', 'NO_SHOW'];
  var PSTAT = { PAID: 'Оплачено', WAITING: 'Ожидает оплаты', PENDING: 'На проверке', REVERSED: 'Подтверждение отменено', RECEIPT_SENT: 'Чек отправлен' };
  var MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
  var el = function (t, c, x) { return C.el(t, c, x); };
  var root, hadData = false, loading = false, openUser = null, students = [], fin = {};

  function rub(n) { return Number(n || 0).toLocaleString('ru-RU') + ' ₽'; }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function iso(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T00:00:00'; }
  function whenText(s) {
    var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); if (!m) return '';
    return Number(m[3]) + ' ' + MON[Number(m[2]) - 1] + (C.hhmm(s) ? ', ' + C.hhmm(s) : '');
  }
  function dateText(s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + '.' + m[2] + '.' + m[1] : ''; }
  function plural(n, a, b, c) { n = Math.abs(n) % 100; var m = n % 10; return n > 10 && n < 20 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c; }
  function errText(e) {
    var map = { unauthorized: 'Нужно войти заново.', server_error: 'Сервер не справился. Попробуйте ещё раз.', cross_origin_forbidden: 'Запрос отклонён. Обновите страницу.', payment_not_found: 'Платёж не найден.', receipt_not_found: 'Чек не найден.' };
    var m = e && e.message || ''; return map[m] || (/^[a-z_]+$/.test(m) ? 'Не получилось выполнить действие. Обновите страницу.' : m || 'Не получилось. Попробуйте ещё раз.');
  }

  /* ---- 01 ждут оплаты ---- */
  function waitingSection(items) {
    var s = C.section('01', 'Ждут оплаты');
    var list = items.filter(function (l) { return UNPAID.indexOf(String(l.payment_status || '').toUpperCase()) >= 0 && DEAD.indexOf(String(l.lesson_status || '').toUpperCase()) < 0; });
    if (!list.length) { s.appendChild(C.empty('Неоплаченных занятий нет. Всё сошлось.')); return s; }
    list.forEach(function (l) {
      var r = el('article', 'pay-row'), info = el('div', 'pay-info');
      info.appendChild(el('div', 'pay-who', l.name || 'Ученик'));
      var meta = el('div', 'pay-meta');
      meta.appendChild(el('span', '', whenText(l.start_time)));
      var sj = C.subjectLabel(l.subject); if (sj) meta.appendChild(el('span', '', sj));
      info.appendChild(meta); r.appendChild(info);
      r.appendChild(el('div', 'pay-sum', Number(l.price) > 0 ? rub(l.price) : 'Цена не задана'));
      var a = el('div', 'c-actions');
      if (window.AdeliaLessonPayment) a.insertAdjacentHTML('beforeend', window.AdeliaLessonPayment.buttons(l));
      r.appendChild(a); s.appendChild(r);
    });
    return s;
  }

  /* ---- 02 чеки ---- */
  function receiptsSection(rc) {
    var items = (rc.items || []).filter(function (x) { return String(x.receipt_status || '').toUpperCase() === 'WAITING' && String(x.payment_status || '').toUpperCase() !== 'REVERSED'; });
    var s = C.section('02', 'Чеки на подтверждение');
    if (!items.length) { s.appendChild(C.empty('Чеков на проверке нет.')); return s; }
    var state = el('div'); state.setAttribute('aria-live', 'polite');
    items.forEach(function (x) {
      var r = el('article', 'pay-row'), info = el('div', 'pay-info');
      info.appendChild(el('div', 'pay-who', x.name || 'Ученик'));
      var meta = el('div', 'pay-meta');
      var sj = C.subjectLabel(x.subject); if (sj) meta.appendChild(el('span', '', sj));
      if (x.lessons_count) meta.appendChild(el('span', '', x.lessons_count + ' ' + plural(x.lessons_count, 'занятие', 'занятия', 'занятий')));
      var d = whenText(x.receipt_created_at || x.payment_created_at); if (d) meta.appendChild(el('span', '', 'Отправлено ' + d));
      info.appendChild(meta); r.appendChild(info);
      r.appendChild(el('div', 'pay-sum', rub(x.total_amount)));
      var a = el('div', 'c-actions'), btns = [];
      if (x.can_view_file) { var v = C.button('Посмотреть чек', 'secondary', '/api/teacher/finance/receipt/file?receipt_id=' + encodeURIComponent(x.receipt_id)); v.target = '_blank'; v.rel = 'noopener'; a.appendChild(v); }
      ['APPROVE', 'REJECT'].forEach(function (act) {
        var b = C.button(act === 'APPROVE' ? 'Подтвердить' : 'Отклонить', act === 'APPROVE' ? 'primary' : 'secondary', function () { review(x, act, b, a, state); });
        btns.push(b); a.appendChild(b);
      });
      r.appendChild(a); s.appendChild(r);
    });
    s.appendChild(state); return s;
  }
  function review(x, action, btn, box, state) {
    function go() {
      var all = box.querySelectorAll('button'); [].forEach.call(all, function (b) { b.disabled = true; }); state.replaceChildren();
      C.api('/teacher/finance/receipt/review', { method: 'POST', body: { payment_id: Number(x.payment_id), action: action } }).then(function () {
        C.toast(action === 'APPROVE' ? 'Оплата подтверждена.' : 'Чек отклонён. Ученик сможет отправить новый.'); return load();
      }, function (e) { [].forEach.call(all, function (b) { b.disabled = false; }); state.replaceChildren(C.error(errText(e))); });
    }
    if (action === 'REJECT') {
      C.modal({ title: 'Отклонить чек?', body: 'Ученик сможет отправить новый файл.', actions: [{ text: 'Отмена', kind: 'secondary' }, { text: 'Отклонить', kind: 'primary', onClick: function () { go(); } }] });
    } else go();
  }

  /* ---- 03 ученики ---- */
  function studentsSection() {
    var s = C.section('03', 'Ученики и баланс');
    if (openUser) { s.appendChild(studentCard(openUser)); return s; }
    if (!students.length) { s.appendChild(C.empty('Учеников пока нет.')); return s; }
    students.forEach(function (u) {
      var f = fin[u.id], debt = Number(u.payment_waiting) || 0;
      var b = el('button', 'pay-stu'); b.type = 'button'; b.setAttribute('aria-label', 'Открыть: ' + u.name);
      b.appendChild(el('span', 'pay-who', u.name));
      var m = el('span', 'pay-meta');
      var left = f ? Number(f.totals.lessons_left) : null;
      m.appendChild(el('span', '', left == null ? 'Остаток: —' : 'Остаток: ' + left + ' ' + plural(left, 'занятие', 'занятия', 'занятий')));
      m.appendChild(el('span', debt > 0 ? 'pay-debt' : '', debt > 0 ? 'Долг ' + rub(debt) : 'Долга нет'));
      b.appendChild(m); b.appendChild(el('span', 'pay-arrow', '→')); b.setAttribute('data-uid', u.id);
      b.addEventListener('click', function () { openUser = u.id; paint(); scrollTo(0, root.getBoundingClientRect().top + scrollY - 60); });
      s.appendChild(b);
    });
    return s;
  }
  function studentCard(uid) {
    var w = el('div', 'pay-card'), u = students.filter(function (x) { return x.id === uid; })[0] || { name: 'Ученик' };
    var back = C.button('← Все ученики', 'text', function () { openUser = null; paint(); });
    w.appendChild(back); w.appendChild(el('h2', 'pay-h', u.name));
    var body = el('div'); body.setAttribute('aria-live', 'polite'); body.appendChild(el('div', 'c-skel')); w.appendChild(body);
    C.api('/teacher/finance/student?user_id=' + encodeURIComponent(uid)).then(function (f) {
      fin[uid] = f; body.replaceChildren();
      var st = el('div', 'c-stats'), t = f.totals || {};
      [['Оплачено', rub(t.paid)], ['Ожидается', rub(t.waiting)], ['Осталось занятий', String(t.lessons_left || 0)]].forEach(function (p) { var sp = el('span'); sp.appendChild(document.createTextNode(p[0] + ': ')); sp.appendChild(el('b', '', p[1])); st.appendChild(sp); });
      body.appendChild(st); body.appendChild(el('p', 'c-label', 'ИСТОРИЯ ОПЛАТ'));
      var pays = f.payments || [];
      if (!pays.length) body.appendChild(C.empty('Платежей нет.'));
      var msg = el('div'); msg.setAttribute('aria-live', 'polite');
      pays.forEach(function (p) {
        var r = el('article', 'pay-row'), info = el('div', 'pay-info');
        info.appendChild(el('div', 'pay-who', (C.subjectLabel(p.subject) || 'Оплата') + ' · ' + (PSTAT[String(p.status).toUpperCase()] || p.status)));
        var mt = el('div', 'pay-meta'); mt.appendChild(el('span', '', dateText(p.confirmed_at || p.created_at)));
        if (p.lessons_count) mt.appendChild(el('span', '', p.lessons_count + ' ' + plural(p.lessons_count, 'занятие', 'занятия', 'занятий')));
        info.appendChild(mt); r.appendChild(info); r.appendChild(el('div', 'pay-sum', rub(p.total_amount)));
        var a = el('div', 'c-actions');
        if (window.AdeliaPaymentReversal) a.insertAdjacentHTML('beforeend', window.AdeliaPaymentReversal.button(p.id, p.status));
        r.appendChild(a); body.appendChild(r);
      });
      body.appendChild(msg);
      if (window.AdeliaPaymentReversal) window.AdeliaPaymentReversal.bind(body, function () { return load(); });
    }, function (e) { body.replaceChildren(C.error(errText(e), function () { paint(); })); });
    return w;
  }

  /* ---- 04 итоги ---- */
  function totalsSection(d) {
    var s = C.section('04', 'Итоги месяца');
    if (!d) { s.appendChild(C.empty('Итоги пока недоступны.')); return s; }
    var g = el('div', 'pay-totals');
    var paid = d.paid || {}, wait = d.waiting || {};
    [['Получено', rub(paid.amount), (paid.count || 0) + ' ' + plural(paid.count || 0, 'оплата', 'оплаты', 'оплат')],
     ['Ожидается', rub(wait.amount), (wait.count || 0) + ' ' + plural(wait.count || 0, 'платёж', 'платежа', 'платежей')]].forEach(function (p) {
      var c = el('div', 'pay-total'); c.append(el('span', 'pay-t-l', p[0]), el('b', 'pay-t-v', p[1]), el('small', '', p[2])); g.appendChild(c);
    });
    s.appendChild(g);
    if (d.period && d.period.start) s.appendChild(el('p', 'cab-sub', 'За период ' + dateText(d.period.start) + ' — ' + dateText(d.period.end)));
    return s;
  }

  function paint(parts) {
    parts = parts || paint.last; paint.last = parts;
    var f = document.createDocumentFragment();
    f.append(waitingSection(parts.lessons), receiptsSection(parts.receipts), studentsSection(), totalsSection(parts.dash));
    root.replaceChildren(f);
    C.setBell((parts.receipts.items || []).filter(function (x) { return String(x.receipt_status).toUpperCase() === 'WAITING'; }).length);
  }

  function opt(p) { return p.then(function (v) { return { v: v }; }, function (e) { if (e.status === 401) throw e; return { e: e }; }); }
  function load() {
    if (loading) return Promise.resolve(); loading = true;
    var now = new Date(), a = new Date(now.getTime() - 60 * 864e5), b = new Date(now.getTime() + 60 * 864e5);
    return Promise.all([
      opt(C.api('/teacher/crm/schedule?limit=500&start=' + iso(a) + '&end=' + iso(b))),
      opt(C.api('/teacher/finance/receipts?status=WAITING&limit=200')),
      opt(C.api('/teacher/crm/students?limit=500')),
      opt(C.api('/teacher/finance/dashboard'))
    ]).then(function (r) {
      var bad = r.filter(function (x) { return x.e; });
      if (bad.length === 4) throw bad[0].e;
      students = r[2].v ? (r[2].v.items || []) : students;
      var parts = { lessons: r[0].v ? (r[0].v.items || []) : [], receipts: r[1].v || { items: [] }, dash: r[3].v || null };
      hadData = true; paint(parts);
      if (bad.length) root.insertBefore(C.error('Часть данных не загрузилась. ' + errText(bad[0].e) + ' '), root.firstChild).appendChild(C.button('Повторить', 'text', load));
      // остатки занятий для списка (не блокируют экран)
      var need = students.filter(function (u) { return !fin[u.id]; }).slice(0, 60);
      return Promise.all(need.map(function (u) { return C.api('/teacher/finance/student?user_id=' + encodeURIComponent(u.id)).then(function (f) { fin[u.id] = f; }, function () {}); })).then(function () { if (!openUser && paint.last) paint(); });
    }).catch(function (e) {
      if (e.status === 401) { location.replace(T); return; }
      if (!hadData) root.replaceChildren(C.error(errText(e), load)); else C.toast('Не удалось обновить. Показаны прежние данные.');
    }).then(function () { loading = false; });
  }

  C.boot({
    role: 'teacher', menu: MENU, active: 'payments',
    render: function (main) {
      main.append(el('h1', 'cab-title', 'Оплаты'), el('p', 'cab-sub', 'Кто ждёт оплату, какие чеки проверить и сколько занятий осталось.'));
      root = document.createElement('div'); root.setAttribute('aria-live', 'polite');
      for (var i = 0; i < 3; i++) root.appendChild(el('div', 'c-skel'));
      main.appendChild(root); document.title = 'Оплаты — Аделия';
      document.addEventListener('adelia:lesson-payment-changed', function () { fin = {}; setTimeout(load, 250); });
      document.addEventListener('adelia:payment-reversed', function () { fin = {}; });
      return load();
    }
  });
})();
