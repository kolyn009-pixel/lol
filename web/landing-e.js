/* Аделия — лендинг E. Без фреймворков. Данные — те же публичные API, что у web/landing.js. */
(function () {
  'use strict';
  var doc = document;
  doc.documentElement.classList.remove('no-js');

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>'"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c];
    });
  }
  function rub(n) { return Number(n).toLocaleString('ru-RU') + ' ₽'; }
  function money(v) { var n = Number(v || 0); return n ? rub(n) : 'Бесплатно'; }
  function when(v) {
    if (!v) return '';
    var d = new Date(v);
    return isNaN(d.getTime()) ? '' : d.toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
  }
  function gradeText(x) {
    if (x.grade_min && x.grade_max) return Number(x.grade_min) === Number(x.grade_max) ? x.grade_min + ' класс' : x.grade_min + '–' + x.grade_max + ' классы';
    if (x.grade_min) return 'от ' + x.grade_min + ' класса';
    if (x.grade_max) return 'до ' + x.grade_max + ' класса';
    return '';
  }
  function getJSON(url, opts) {
    var ctrl = 'AbortController' in window ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 8000) : 0;
    var init = { headers: { Accept: 'application/json' }, cache: (opts && opts.cache) || 'default' };
    if (ctrl) init.signal = ctrl.signal;
    return fetch(url, init).then(function (r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error('http_' + r.status);
      return r.json();
    }, function (e) { clearTimeout(timer); throw e; });
  }
  function items(data) { return Array.isArray(data) ? data : (data && data.items) || []; }

  /* ---------- Меню ---------- */
  var toggle = doc.querySelector('.e-menu-toggle');
  var nav = doc.getElementById('e-nav');
  var mobile = window.matchMedia('(max-width: 768px)');
  function setMenu(open, focusToggle) {
    if (!toggle || !nav) return;
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.querySelector('.e-menu-toggle__text').textContent = open ? 'Закрыть' : 'Меню';
    nav.classList.toggle('is-open', open);
    if (!open && focusToggle) toggle.focus();
  }
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = toggle.getAttribute('aria-expanded') !== 'true';
      setMenu(open);
      if (open) { var first = nav.querySelector('a'); if (first) first.focus(); }
    });
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a') && mobile.matches) setMenu(false);
    });
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') setMenu(false, true);
    });
    var onChange = function () { if (!mobile.matches) setMenu(false); };
    if (mobile.addEventListener) mobile.addEventListener('change', onChange); else if (mobile.addListener) mobile.addListener(onChange);
  }

  /* ---------- Активный пункт меню ---------- */
  if ('IntersectionObserver' in window) {
    var links = {};
    doc.querySelectorAll('.e-nav__list a[href^="#"]').forEach(function (a) { links[a.getAttribute('href').slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var a = links[en.target.id];
        if (!a) return;
        if (en.isIntersecting) {
          Object.keys(links).forEach(function (k) { links[k].removeAttribute('aria-current'); });
          a.setAttribute('aria-current', 'true');
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    Object.keys(links).forEach(function (id) { var el = doc.getElementById(id); if (el) io.observe(el); });
  }

  /* ---------- Цены курсов: /api/public/prices ---------- */
  function isPhysics(x) {
    var s = String(x.subject || '').toUpperCase();
    return !s || s === 'PHYSICS' || s.indexOf('ФИЗИК') !== -1;
  }
  function overlaps(x, min, max) {
    var a = x.grade_min == null ? null : Number(x.grade_min);
    var b = x.grade_max == null ? null : Number(x.grade_max);
    if (a == null && b == null) return true;
    return (a == null || a <= max) && (b == null || b >= min);
  }
  function loadPrices() {
    var rows = doc.querySelectorAll('.e-course[data-goal]');
    if (!rows.length) return;
    getJSON('/api/public/prices').then(function (data) {
      var list = items(data);
      rows.forEach(function (row) {
        var goal = row.getAttribute('data-goal');
        var min = Number(row.getAttribute('data-grade-min'));
        var max = Number(row.getAttribute('data-grade-max'));
        var hits = list.filter(function (x) {
          return String(x.goal || '').toUpperCase() === goal && isPhysics(x) && overlaps(x, min, max) && Number(x.amount != null ? x.amount : x.hourly_rate) > 0;
        });
        var slot = row.querySelector('[data-price]');
        if (!hits.length || !slot) return;
        hits.sort(function (p, q) { return Number(p.amount != null ? p.amount : p.hourly_rate) - Number(q.amount != null ? q.amount : q.hourly_rate); });
        var best = hits[0];
        var amount = Number(best.amount != null ? best.amount : best.hourly_rate);
        var minutes = Number(best.duration_minutes || 60);
        slot.textContent = (hits.length > 1 ? 'от ' : '') + rub(amount) + ' / ' + minutes + ' мин';
      });
    }).catch(function () { /* остаётся статический «[цена уточняется]» */ });
  }

  /* ---------- Группы и события: /api/public/opportunities ---------- */
  function seatsText(x) {
    if (x.seats_left === null || x.seats_left === undefined) return '';
    return x.seats_left > 0 ? 'Осталось мест: ' + x.seats_left : 'Места уточняются';
  }
  function row(kind, status, title, text, meta, href, action) {
    return '<article class="e-row">' +
      '<p class="e-label e-row__kind">' + esc(kind) + '<br>' + esc(status) + '</p>' +
      '<div class="e-row__body"><h3 class="e-row__title">' + esc(title) + '</h3>' +
      (text ? '<p class="e-row__text">' + esc(text) + '</p>' : '') +
      '<p class="e-row__meta">' + meta.filter(Boolean).map(function (m) { return '<span>' + esc(m) + '</span>'; }).join('') + '</p></div>' +
      '<a class="e-row__action" href="' + esc(href) + '">' + esc(action) + ' →</a></article>';
  }
  function emptyRow(title, text) {
    return '<div class="e-row e-row--empty"><h3 class="e-row__title">' + esc(title) + '</h3><p class="e-row__text">' + esc(text) + '</p><a class="e-row__action" href="/start/">Записаться на пробный урок →</a></div>';
  }
  function loadOpportunities() {
    var root = doc.getElementById('e-opportunities');
    if (!root) return;
    getJSON('/api/public/opportunities', { cache: 'no-store' }).then(function (data) {
      var out = [];
      (data.groups || []).forEach(function (x) {
        var wait = x.recruitment_status === 'WAITLIST';
        out.push(row('Группа', wait ? 'Лист ожидания' : 'Набор открыт', x.title,
          [x.subject, x.study_goal].filter(Boolean).join(' · '),
          [money(x.price) + ' / занятие', x.next_lesson ? 'Ближайшее: ' + when(x.next_lesson) : '', seatsText(x)],
          '/start/group.html?group_id=' + encodeURIComponent(x.id),
          wait ? 'Встать в лист ожидания' : 'Записаться в группу'));
      });
      (data.events || []).forEach(function (x) {
        out.push(row(x.event_label || 'Событие', 'Регистрация открыта', x.title,
          [x.subject, gradeText(x)].filter(Boolean).join(' · '),
          [when(x.starts_at), money(x.price), seatsText(x)],
          '/start/?event_id=' + encodeURIComponent(x.id), 'Записаться'));
      });
      root.innerHTML = out.join('') || emptyRow('Новые группы и события появятся здесь', 'Сейчас открытого набора нет. Можно записаться на пробный урок.');
    }).catch(function () {
      root.innerHTML = emptyRow('Группы и события скоро появятся здесь', 'А пока можно записаться на пробный урок.');
    });
  }

  /* ---------- Отзывы: /api/public/reviews ---------- */
  function loadReviews() {
    var root = doc.getElementById('e-reviews-list');
    if (!root) return;
    getJSON('/api/public/reviews').then(function (data) {
      var html = items(data).slice(0, 6).map(function (x) {
        return '<figure class="e-review"><blockquote><p>«' + esc(x.text) + '»</p></blockquote>' +
          '<figcaption><b>' + esc(x.author || 'Ученик') + '</b> · ' + esc(x.source || 'Профи.ру') + '</figcaption></figure>';
      }).join('');
      root.innerHTML = html || '<p class="e-note">Скоро здесь появятся подтверждённые отзывы учеников.</p>';
    }).catch(function () {
      root.innerHTML = '<p class="e-note">Отзывы появятся после импорта подтверждённых отзывов с Профи.ру.</p>';
    });
  }

  /* ---------- Приложение: подсветить версию для этого устройства ---------- */
  function recommendDesktop() {
    var ua = navigator.userAgent || '', platform = navigator.platform || '';
    var os = /Win/i.test(platform) || /Windows/i.test(ua) ? 'windows' : (/Mac/i.test(platform) || /Macintosh/i.test(ua)) && !/iPhone|iPad/i.test(ua) ? 'mac' : '';
    if (!os) return;
    doc.querySelectorAll('#e-downloads a[data-os="' + os + '"]').forEach(function (a) {
      a.classList.add('is-recommended');
      a.setAttribute('aria-describedby', 'e-download-hint');
    });
    var label = doc.querySelector('#e-downloads .e-label');
    if (label && !doc.getElementById('e-download-hint')) {
      var hint = doc.createElement('span');
      hint.id = 'e-download-hint';
      hint.className = 'e-visually-hidden';
      hint.textContent = 'Подходит для этого компьютера';
      label.appendChild(hint);
    }
  }

  loadPrices();
  loadOpportunities();
  loadReviews();
  recommendDesktop();
})();
