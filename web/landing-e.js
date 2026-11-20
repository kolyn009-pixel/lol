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
  var DICT = { PHYSICS: 'Физика', CHEMISTRY: 'Химия', SCHOOL: 'Школьная программа', OGE: 'ОГЭ', EGE: 'ЕГЭ', COLLEGE_PHYSICS: 'Физика в колледже', OLYMPIAD: 'Олимпиада' };
  function tr(code) { return DICT[String(code || '').toUpperCase()] || ''; }
  function subjectOf(x) {
    var s = String(x.subject || '').toUpperCase();
    if (!s || s === 'PHYSICS' || s.indexOf('ФИЗИК') !== -1) return 'PHYSICS';
    if (s === 'CHEMISTRY' || s.indexOf('ХИМИ') !== -1) return 'CHEMISTRY';
    return s;
  }
  function rowSubject(row) { return (row.getAttribute('data-subject') || 'PHYSICS').toUpperCase(); }
  function overlaps(x, min, max) {
    var a = x.grade_min == null ? null : Number(x.grade_min);
    var b = x.grade_max == null ? null : Number(x.grade_max);
    if (a == null && b == null) return true;
    return (a == null || a <= max) && (b == null || b >= min);
  }
  function num(n) { return Number(n).toLocaleString('ru-RU'); }
  var oppPromise = null;
  function loadOpps() {
    if (!oppPromise) oppPromise = getJSON('/api/public/opportunities', { cache: 'no-store' });
    return oppPromise;
  }
  function setText(el, t) { if (el) el.textContent = t; }
  function loadPrices() {
    var rows = doc.querySelectorAll('.e-course[data-goal]');
    if (!rows.length) return;
    getJSON('/api/public/prices').then(function (data) {
      var list = items(data);
      var overall = null;
      rows.forEach(function (row) {
        var goal = row.getAttribute('data-goal');
        var subj = rowSubject(row);
        var min = Number(row.getAttribute('data-grade-min'));
        var max = Number(row.getAttribute('data-grade-max'));
        var hits = list.filter(function (x) {
          return String(x.goal || '').toUpperCase() === goal && subjectOf(x) === subj && overlaps(x, min, max) && Number(x.amount != null ? x.amount : x.hourly_rate) > 0;
        });
        if (!hits.length) return;
        var best = Math.min.apply(null, hits.map(function (x) { return Number(x.amount != null ? x.amount : x.hourly_rate); }));
        overall = overall == null ? best : Math.min(overall, best);
        setText(row.querySelector('[data-price]'), 'от ' + num(best) + ' ₽ / 60 мин');
      });
      if (overall != null) setText(doc.querySelector('[data-formats-price="individual"]'), 'от ' + num(overall) + ' ₽ / 60 мин');
    }).catch(function () { /* остаётся статическое «Цена уточняется» */ });
  }
  function groupPrice(g) { return Number(g.price); }
  function loadGroupPrices() {
    var rows = doc.querySelectorAll('.e-course[data-goal]');
    loadOpps().then(function (data) {
      var groups = (data.groups || []).filter(function (x) {
        return groupPrice(x) > 0 && x.recruitment_status !== 'WAITLIST';
      });
      if (!groups.length) return;
      var minOf = function (arr) { return Math.min.apply(null, arr.map(groupPrice)); };
      var phys = groups.filter(function (x) { return subjectOf(x) === 'PHYSICS'; });
      var overall = minOf(phys.length ? phys : groups);
      rows.forEach(function (row) {
        var goal = row.getAttribute('data-goal');
        var subj = rowSubject(row);
        var matched = groups.filter(function (x) { return String(x.study_goal || '').toUpperCase() === goal && subjectOf(x) === subj; });
        var link = row.querySelector('[data-group-link]');
        if (!link || !matched.length) return; // нет групп по этой цели — остаётся «Группы набираются»
        var y = minOf(matched);
        setText(link.querySelector('[data-group-price]'), 'от ' + num(y) + ' ₽ / занятие');
        link.classList.remove('is-empty');
        link.setAttribute('href', '/start/?format=group#e-groups');
        link.setAttribute('aria-label', 'В группе, ' + (row.querySelector('.e-course__title').textContent) + ': от ' + num(y) + ' рублей за занятие');
      });
      setText(doc.querySelector('[data-formats-price="group"]'), 'от ' + num(overall) + ' ₽ / занятие');
      var maxN = Math.max.apply(null, groups.map(function (x) { return Number(x.max_members) || 0; }));
      if (maxN > 0) {
        doc.querySelectorAll('[data-group-max]').forEach(function (el) { el.textContent = maxN; });
        doc.querySelectorAll('[data-group-max-wrap]').forEach(function (el) { el.hidden = false; });
      }
    }).catch(function () { /* остаётся «Группы набираются» */ });
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
    loadOpps().then(function (data) {
      var out = [];
      (data.groups || []).forEach(function (x) {
        var wait = x.recruitment_status === 'WAITLIST';
        out.push(row('Группа', wait ? 'Лист ожидания' : 'Набор открыт', x.title,
          [tr(x.subject), tr(x.study_goal)].filter(Boolean).join(' · '),
          [money(x.price) + ' / занятие', x.next_lesson ? 'Ближайшее: ' + when(x.next_lesson) : '', seatsText(x)],
          '/start/group.html?group_id=' + encodeURIComponent(x.id),
          wait ? 'Встать в лист ожидания' : 'Записаться в группу'));
      });
      (data.events || []).forEach(function (x) {
        out.push(row(x.event_label || 'Событие', 'Регистрация открыта', x.title,
          [tr(x.subject), gradeText(x)].filter(Boolean).join(' · '),
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

  /* ---------- Преподаватель: /api/public/teacher-profile (статический fallback в HTML) ---------- */
  function clean(v) { v = v == null ? '' : String(v).trim(); return /^(null|undefined|\[.*\])$/i.test(v) ? '' : v; }
  function loadTeacher() {
    getJSON('/api/public/teacher-profile').then(function (d) {
      if (!d || typeof d !== 'object') return;
      var q = doc.querySelector('[data-teacher-quote] p'), nm = doc.querySelector('[data-teacher-name]');
      var facts = doc.querySelector('[data-teacher-facts]'), bio = doc.querySelector('[data-teacher-bio]'), lk = doc.querySelector('[data-teacher-links]');
      if (clean(d.quote) && q) q.textContent = '«' + clean(d.quote).replace(/^«|»$/g, '') + '»';
      if (clean(d.display_name) && nm) nm.textContent = clean(d.display_name);
      var fl = [].concat(Array.isArray(d.facts) ? d.facts : []).map(clean).filter(Boolean);
      if (clean(d.education)) fl.unshift(clean(d.education));
      if (clean(d.experience_text) && fl.indexOf(clean(d.experience_text)) === -1) fl.unshift(clean(d.experience_text));
      if (facts && fl.length) facts.innerHTML = fl.map(function (f) { return '<li>' + esc(f) + '</li>'; }).join('');
      if (bio && clean(d.bio)) bio.textContent = clean(d.bio);
      var L = d.links || {};
      var defs = [['profi', 'Отзывы на Профи.ру'], ['telegram_channel', 'Telegram-канал'], ['vk', 'VK']];
      var lh = defs.filter(function (k) { return /^https?:\/\//.test(clean(L[k[0]])); }).map(function (k) {
        return '<a href="' + esc(clean(L[k[0]])) + '" target="_blank" rel="noopener" data-link="' + k[0] + '">' + k[1] + '</a>';
      }).join('');
      if (lk && lh) lk.innerHTML = lh;
    }).catch(function () { /* остаётся статический текст */ });
  }

  loadTeacher();
  loadPrices();
  loadGroupPrices();
  loadOpportunities();
  loadReviews();
  recommendDesktop();
})();
