/* Кабинет «Журнал»: общее ядро. window.C, C.boot(). Без фреймворков. */
(function () {
  'use strict';
  var C = window.C = {};
  var SUBJ = { PHYSICS: 'Физика', CHEMISTRY: 'Химия', OGE: 'ОГЭ', EGE: 'ЕГЭ', SCHOOL: 'Школьная программа' };
  var PAY = { PAID: ['Оплачено', 'ok'], AWAITING_PAYMENT: ['Ждём оплату', 'due'], UNPAID: ['Не оплачено', 'due'], WAITING: ['Ждём оплату', 'due'], PREPAID: ['Оплачено', 'ok'], FREE: ['Без оплаты', ''] };
  var HOME = { teacher: '/teacher/', student: '/app/' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  C.esc = esc;
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  C.el = el;

  C.api = function (path, opts) {
    opts = opts || {};
    var ctl = new AbortController(), t = setTimeout(function () { ctl.abort(); }, 12000);
    var init = { method: opts.method || 'GET', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, signal: ctl.signal };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    return fetch('/api' + path, init).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var e = new Error(j.detail || j.error || 'Не получилось загрузить. Попробуйте ещё раз.'); e.status = r.status; throw e; }
        return j;
      });
    }, function (err) {
      var e = new Error(err && err.name === 'AbortError' ? 'Сервер долго отвечает. Попробуйте ещё раз.' : 'Нет связи с сервером.'); e.status = 0; throw e;
    }).then(function (v) { clearTimeout(t); return v; }, function (e) { clearTimeout(t); throw e; });
  };

  /* ---- время ---- */
  C.hhmm = function (iso, tz) {
    if (!iso) return '';
    var s = String(iso), m = s.match(/^\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/);
    if (m && !m[3]) return m[1] + ':' + m[2];
    var d = new Date(s); if (isNaN(d)) return '';
    try { return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: tz || undefined }).format(d); }
    catch (e) { return new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d); }
  };

  /* ---- компоненты ---- */
  C.label = function (num, text) { return el('p', 'c-label', (num ? num + ' / ' : '') + String(text).toUpperCase()); };
  C.section = function (num, text) { var s = el('section', 'c-section'); s.appendChild(C.label(num, text)); return s; };
  C.empty = function (text) { return el('p', 'c-empty', text); };
  C.error = function (text, retry) {
    var d = el('div', 'c-error'); d.setAttribute('role', 'alert'); d.appendChild(el('span', '', text + ' '));
    if (retry) { var b = C.button('Повторить', 'text', retry); d.appendChild(b); } return d;
  };
  C.button = function (text, kind, onClick) {
    var isLink = typeof onClick === 'string', b = el(isLink ? 'a' : 'button', 'c-btn' + (kind && kind !== 'secondary' ? ' ' + kind : ''), text);
    if (isLink) b.href = onClick; else { b.type = 'button'; if (onClick) b.addEventListener('click', onClick); }
    return b;
  };
  C.subjectLabel = function (s) { return SUBJ[String(s || '').toUpperCase()] || (s ? String(s) : ''); };
  C.payStatus = function (s) { var p = PAY[String(s || '').toUpperCase()]; return p ? { text: p[0], cls: p[1] } : null; };

  /* lessonRow(l, {tz, actions:[Node|string(html из доверенного модуля)], payHtml, link}) */
  C.lessonRow = function (l, o) {
    o = o || {};
    var row = el('article', 'c-lesson'), tm = C.hhmm(l.start_at, o.tz), te = C.hhmm(l.end_at, o.tz);
    row.appendChild(el('div', 'c-lesson-time', tm + (te ? '–' + te : '')));
    var info = el('div', 'c-lesson-info');
    var group = l.format === 'GROUP' || l.kind === 'group_lesson';
    info.appendChild(el('div', 'c-lesson-who', (group ? (l.group_title || l.title) : (l.student_name || l.title)) || 'Занятие'));
    var meta = el('div', 'c-lesson-meta');
    meta.appendChild(el('span', 'c-tag', group ? 'Группа' + (l.members_count ? ' · ' + l.members_count : '') : 'Индивидуально'));
    var subj = C.subjectLabel(l.subject); if (subj) meta.appendChild(el('span', '', subj));
    if (l.goal) { var g = C.subjectLabel(l.goal); meta.appendChild(el('span', '', g)); }
    var ps = C.payStatus(l.payment_status);
    if (ps) meta.appendChild(el('span', 'c-pay ' + ps.cls, ps.text));
    info.appendChild(meta); row.appendChild(info);
    var act = el('div', 'c-actions');
    (o.actions || []).forEach(function (a) { if (typeof a === 'string') act.insertAdjacentHTML('beforeend', a); else if (a) act.appendChild(a); });
    row.appendChild(act); return row;
  };

  var ATTN = { homework: 'Работы на проверку', receipt: 'Чеки на подтверждение', request: 'Заявки', message: 'Сообщения' };
  C.attentionRow = function (a, href) {
    var r = el('a', 'c-attn'); r.href = href || a.link || '#';
    r.appendChild(el('span', 'c-attn-n', String(a.count)));
    var t = el('span', 'c-attn-t'); t.appendChild(el('b', '', ATTN[a.kind] || a.kind));
    var first = (a.items || [])[0];
    if (first) t.appendChild(el('small', '', [first.title, first.subtitle].filter(Boolean).join(' · ')));
    r.appendChild(t); r.appendChild(el('span', '', '→')); r.setAttribute('aria-label', (ATTN[a.kind] || a.kind) + ': ' + a.count);
    return r;
  };

  var toastT;
  C.toast = function (text) {
    var o = document.querySelector('.c-toast'); if (o) o.remove(); clearTimeout(toastT);
    var t = el('div', 'c-toast', text); t.setAttribute('role', 'status'); document.body.appendChild(t);
    toastT = setTimeout(function () { t.remove(); }, 5000);
  };

  C.modal = function (o) {
    var prev = document.activeElement, bd = el('div', 'c-backdrop'), m = el('div', 'c-modal');
    m.setAttribute('role', 'dialog'); m.setAttribute('aria-modal', 'true'); m.tabIndex = -1;
    var h = el('h2', '', o.title || ''); h.id = 'cm' + Date.now(); m.setAttribute('aria-labelledby', h.id); m.appendChild(h);
    var body = el('div'); if (typeof o.body === 'string') body.textContent = o.body; else if (o.body) body.appendChild(o.body); m.appendChild(body);
    var act = el('div', 'c-actions'); m.appendChild(act); bd.appendChild(m);
    function close() { document.removeEventListener('keydown', key, true); bd.remove(); if (prev && prev.focus) prev.focus(); }
    function key(e) {
      if (e.key === 'Escape') { e.stopPropagation(); close(); }
      else if (e.key === 'Tab') {
        var f = [].slice.call(m.querySelectorAll('button,a[href],input,select,textarea')).filter(function (x) { return !x.disabled; });
        if (!f.length) return; var a = f[0], z = f[f.length - 1];
        if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); } else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
      }
    }
    (o.actions || [{ text: 'Закрыть', kind: 'secondary' }]).forEach(function (a) {
      act.appendChild(C.button(a.text, a.kind, function () { if (!a.onClick || a.onClick() !== false) close(); }));
    });
    bd.addEventListener('mousedown', function (e) { if (e.target === bd) close(); });
    document.addEventListener('keydown', key, true); document.body.appendChild(bd);
    (m.querySelector('input,button,a') || m).focus();
    return { close: close };
  };

  C.setBell = function (n) {
    var b = document.querySelector('.cab-bell'); if (!b) return;
    var s = b.querySelector('b'); if (s) s.remove();
    n = Number(n) || 0;
    if (n > 0) b.appendChild(el('b', '', n > 99 ? '99+' : String(n)));
    b.setAttribute('aria-label', n > 0 ? 'Уведомления: ' + n : 'Уведомления');
  };

  /* ---- boot ---- */
  C.boot = function (opts) {
    var role = opts.role, home = HOME[role], other = role === 'teacher' ? 'student' : 'teacher';
    document.body.classList.add('cab');
    C.api('/auth/me').then(function (me) {
      var s = me && me.session;
      if (!me || !me.authenticated || !s) { location.replace(home); return; }
      if (s.role === 'parent') { location.replace('/app/parent/'); return; }
      if (s.role !== role) { location.replace(s.role === 'teacher' ? '/app/cabinet/teacher.html' : '/app/cabinet/student.html'); return; }
      build(s);
    }, function (e) { if (e.status === 401) location.replace(home); else showFatal(e); });

    function showFatal(e) { document.body.innerHTML = ''; var d = el('div', 'cab-main'); d.appendChild(C.error(e.message || 'Не получилось открыть кабинет.', function () { location.reload(); })); document.body.appendChild(d); }

    function build(s) {
      var menu = opts.menu || [];
      document.body.innerHTML = '';
      var skip = el('a', 'cab-skip', 'К содержимому'); skip.href = '#cabMain'; document.body.appendChild(skip);
      var head = el('header', 'cab-head');
      var brand = el('a', 'cab-brand', 'Аделия'); brand.href = home; head.appendChild(brand);
      var nm = s.name || s.full_name || (s.user && (s.user.name || s.user.full_name)) || ''; head.appendChild(el('span', 'cab-name', nm));
      var bell = el('button', 'cab-bell'); bell.type = 'button'; bell.setAttribute('aria-label', 'Уведомления');
      bell.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 17V11a6 6 0 0 1 12 0v6l1.5 2h-15zM10 21h4"/></svg>';
      bell.addEventListener('click', function () { location.href = home; }); head.appendChild(bell);
      var old = el('a', 'cab-link cab-old', 'Вернуться к старому'); old.href = home; head.appendChild(old);
      var out = el('button', 'cab-link', 'Выйти'); out.type = 'button';
      out.addEventListener('click', function () { C.api('/auth/logout', { method: 'POST', body: {} }).catch(function () {}).then(function () { location.replace(home); }); });
      head.appendChild(out); document.body.appendChild(head);

      var shell = el('div', 'cab-shell'), side = el('nav', 'cab-side'); side.setAttribute('aria-label', 'Разделы');
      menu.forEach(function (m) { var a = el('a', '', m.label); a.href = m.href; if (m.key === opts.active) a.setAttribute('aria-current', 'page'); side.appendChild(a); });
      var main = el('main', 'cab-main'); main.id = 'cabMain'; main.tabIndex = -1;
      shell.appendChild(side); shell.appendChild(main); document.body.appendChild(shell);

      var phone = menu.filter(function (m) { return m.phone; }); if (!phone.length) phone = menu.slice(0, 4);
      var rest = menu.filter(function (m) { return phone.indexOf(m) < 0; });
      var tabs = el('nav', 'cab-tabs'); tabs.setAttribute('aria-label', 'Основные разделы');
      phone.forEach(function (m) { var a = el('a', '', m.short || m.label); a.href = m.href; if (m.key === opts.active) a.setAttribute('aria-current', 'page'); tabs.appendChild(a); });
      var more = el('div', 'cab-more'); more.hidden = true; more.id = 'cabMore';
      rest.forEach(function (m) { var a = el('a', '', m.label); a.href = m.href; more.appendChild(a); });
      var oa = el('a', '', 'Вернуться к старому'); oa.href = home; more.appendChild(oa);
      var mb = el('button', '', 'Ещё'); mb.type = 'button'; mb.setAttribute('aria-expanded', 'false'); mb.setAttribute('aria-controls', 'cabMore');
      mb.addEventListener('click', function () { more.hidden = !more.hidden; mb.setAttribute('aria-expanded', String(!more.hidden)); });
      tabs.appendChild(mb); document.body.appendChild(more); document.body.appendChild(tabs);

      C.main = main;
      Promise.resolve().then(function () { return opts.render(main, s); }).catch(function (e) {
        if (e && e.status === 401) { location.replace(home); return; }
        main.innerHTML = ''; main.appendChild(C.error((e && e.message) || 'Что-то пошло не так.', function () { location.reload(); }));
      });
    }
  };
})();
