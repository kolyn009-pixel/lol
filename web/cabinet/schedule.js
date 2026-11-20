/* Кабинет «Журнал»: Расписание преподавателя. Контракт эндпоинтов — как в старом кабинете. */
(function () {
  'use strict';
  window.__lpNoReload = true;
  var T = '/app/teacher.html';
  var STATUS = { SCHEDULED: 'Запланировано', PLANNED: 'Запланировано', PENDING: 'Ждёт подтверждения', IN_PROGRESS: 'Идёт', COMPLETED: 'Завершено', FINISHED: 'Завершено', CANCELLED: 'Отменено', CONFIRMED: 'Подтверждено' };
  var ERR = { invalid_start_time: 'Проверьте дату и время.', start_time_in_past: 'Выберите будущее время.', slot_unavailable: 'Это время уже занято.', program_not_found: 'Направление недоступно. Выберите другое.', cross_origin_forbidden: 'Обновите страницу и повторите.', unauthorized: 'Войдите заново.' };
  var weekOffset = 0, items = [], groups = [], tz = '', body, bar, grid, rangeEl, hadData = false;

  function p2(n) { return (n < 10 ? '0' : '') + n; }
  function ymd(d) { return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); }
  function monday(off) { var d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + off * 7); return d; }
  function parseDay(s) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function fmtLong(d) { return d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }); }
  function status(s) { var k = String(s || '').toUpperCase(); return STATUS[k] || (k && !/^[A-Z0-9_ -]+$/.test(String(s)) ? String(s) : ''); }
  function msg(e) { return ERR[e.code] || e.message || 'Не получилось. Попробуйте ещё раз.'; }
  function post(path, b) {
    return C.api(path, { method: 'POST', body: b }).catch(function (e) { throw e; });
  }
  function tr(e) { var m = ERR[(e && e.message) || '']; if (m) e.message = m; return e; }
  function isCancelled(l) { return String(l.lesson_status || l.status || '').toUpperCase() === 'CANCELLED'; }

  function range() { var m = monday(weekOffset), e = new Date(m); e.setDate(e.getDate() + 7); return { m: m, e: e }; }

  function load() {
    var r = range(), q = '?start=' + ymd(r.m) + 'T00:00:00&end=' + ymd(r.e) + 'T00:00:00&limit=500';
    return Promise.all([
      C.api('/teacher/crm/schedule' + q),
      C.api('/teacher/group-lessons').catch(function () { return { items: [] }; })
    ]).then(function (a) {
      hadData = true; items = a[0].items || []; groups = (a[1].items || []).filter(function (g) {
        var d = String(g.start_time || '').slice(0, 10); return d >= ymd(r.m) && d < ymd(r.e);
      });
      paint();
    }, function (e) {
      if (e.status === 401) { location.replace(T); return; }
      if (!hadData) { grid.replaceChildren(C.error(tr(e).message, load)); } else C.toast('Не удалось обновить. Показаны прежние данные.');
    });
  }

  function paint() {
    var r = range(), last = new Date(r.e); last.setDate(last.getDate() - 1);
    rangeEl.textContent = r.m.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) + ' — ' + last.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
    var today = ymd(new Date()), frag = document.createDocumentFragment(), total = 0;
    for (var i = 0; i < 7; i++) {
      var d = new Date(r.m); d.setDate(d.getDate() + i); var key = ymd(d);
      var day = C.el('section', 'sch-day' + (key === today ? ' today' : '')); if (key === today) day.setAttribute('aria-current', 'date');
      var dh = C.el('div', 'sch-dh'); dh.append(C.el('span', '', d.toLocaleDateString('ru-RU', { weekday: 'short' }) + ', ' + d.getDate() + ' ' + d.toLocaleDateString('ru-RU', { month: 'short' })));
      day.appendChild(dh);
      var list = [];
      items.forEach(function (l) { if (String(l.start_time).slice(0, 10) === key) list.push({ k: 'lesson', l: l }); });
      groups.forEach(function (g) { if (String(g.start_time).slice(0, 10) === key) list.push({ k: 'group', l: g }); });
      list.sort(function (a, b) { return String(a.l.start_time).localeCompare(String(b.l.start_time)); });
      if (!list.length) day.appendChild(C.el('p', 'sch-none', 'Занятий нет'));
      list.forEach(function (x) { total++; day.appendChild(card(x)); });
      frag.appendChild(day);
    }
    grid.replaceChildren(frag);
    if (!total) grid.insertBefore(C.empty('На этой неделе занятий нет. Добавьте урок кнопкой «+ Урок».'), grid.firstChild);
    var bell = items.filter(function (l) { return String(l.payment_status || '').toUpperCase() === 'AWAITING_PAYMENT' && !isCancelled(l); }).length; void bell;
  }

  function card(x) {
    var l = x.l, g = x.k === 'group', b = C.el('button', 'sch-item' + (!g && isCancelled(l) ? ' cancelled' : ''));
    b.type = 'button';
    var w = C.el('span', 'sch-w');
    w.append(C.el('span', 'sch-t', C.hhmm(l.start_time) + (l.duration_minutes ? ' · ' + l.duration_minutes + ' мин' : '')));
    w.append(document.createElement('br'), document.createTextNode(g ? (l.group_name || 'Группа') : (l.name || 'Занятие')));
    b.appendChild(w);
    var m = C.el('span', 'sch-m'); m.appendChild(C.el('span', 'c-tag', g ? 'Группа' : 'Индивидуально'));
    var s = C.subjectLabel(l.subject); if (s) m.appendChild(C.el('span', '', s));
    if (!g) { var ps = C.payStatus(l.payment_status); if (ps && !isCancelled(l)) m.appendChild(C.el('span', 'c-pay ' + ps.cls, ps.text)); }
    var st = status(g ? l.status : l.lesson_status); if (st && (isCancelled(l) || /Идёт|Завершено/.test(st))) m.appendChild(C.el('span', '', st));
    b.appendChild(m);
    b.addEventListener('click', function () { g ? openGroup(l) : openLesson(l); });
    return b;
  }

  function fmtWhen(l) { var d = parseDay(String(l.start_time).slice(0, 10)); return fmtLong(d) + ', ' + C.hhmm(l.start_time); }

  function openGroup(g) {
    var bd = C.el('div', 'sch-facts');
    bd.append(C.el('p', '', fmtWhen(g)), C.el('p', '', [C.subjectLabel(g.subject), C.subjectLabel(g.study_goal)].filter(Boolean).join(' · ')));
    if (g.participants != null) bd.append(C.el('p', '', 'Были: ' + (g.attended || 0) + ' из ' + g.participants));
    var a = C.el('div', 'sch-acts'); a.appendChild(C.button('Открыть в старом кабинете', 'secondary', T)); bd.appendChild(a);
    C.modal({ title: g.group_name || 'Групповое занятие', body: bd });
  }

  function openLesson(l) {
    var bd = C.el('div', 'sch-facts'), cancelled = isCancelled(l), st = status(l.lesson_status);
    bd.append(C.el('p', '', fmtWhen(l) + (l.duration_minutes ? ' · ' + l.duration_minutes + ' мин' : '')),
      C.el('p', '', [C.subjectLabel(l.subject), C.subjectLabel(l.study_goal)].filter(Boolean).join(' · ')));
    var ps = C.payStatus(l.payment_status), line = [st, ps && ps.text, Number(l.price) > 0 ? Number(l.price).toLocaleString('ru-RU') + ' ₽' : ''].filter(Boolean).join(' · ');
    if (line) bd.append(C.el('p', '', line));
    var out = C.el('div'); out.setAttribute('aria-live', 'polite');
    var acts = C.el('div', 'sch-acts'), m;
    function fail(e) { out.replaceChildren(Object.assign(C.el('p', 'sch-err', msg(tr(e))), { role: 'alert' })); }
    function done(text) { m.close(); C.toast(text); load(); }
    function busy(btn, fn) {
      btn.disabled = true; var t = btn.textContent; out.replaceChildren();
      return fn().then(function () { }, function (e) { fail(e); }).then(function () { btn.disabled = false; btn.textContent = t; });
    }
    if (!cancelled) {
      var isDone = /Завершено/.test(st);
      if (!isDone) {
        var open = C.button(/Идёт/.test(st) ? 'Открыть занятие' : 'Начать занятие', 'primary', function () {
          var w = window.open('', '_blank');
          busy(open, function () {
            return post('/teacher/lesson/open-entry', { lesson_id: l.id }).then(function (r) {
              if (r.meeting_url) { if (w) w.location = r.meeting_url; else location.href = r.meeting_url; C.toast('Занятие открыто'); load(); }
              else { if (w) w.close(); C.toast('Занятие начато'); load(); }
            }, function (e) { if (w) w.close(); throw e; });
          });
        });
        acts.appendChild(open);
        acts.appendChild(C.button('Перенести', 'secondary', function () { reschedulePanel(l, out, m, done, fail); }));
        acts.appendChild(C.button('Отменить', 'secondary', function () { cancelPanel(l, out, m, done, fail); }));
      }
      if (window.AdeliaLessonPayment) {
        var pw = C.el('div', 'sch-acts'); pw.style.marginTop = '0';
        pw.innerHTML = window.AdeliaLessonPayment.buttons(Object.assign({}, l, { name: l.name })) || '';
        if (pw.children.length) acts.append.apply(acts, [].slice.call(pw.children));
      }
    }
    bd.append(out, acts);
    m = C.modal({ title: l.name || 'Занятие', body: bd });
    document.addEventListener('adelia:lesson-payment-changed', function h() { document.removeEventListener('adelia:lesson-payment-changed', h); m.close(); setTimeout(load, 250); });
  }

  function reschedulePanel(l, out, m, done, fail) {
    var f = C.el('form', 'sch-form'), lab = C.el('label', '', 'Новое время'), inp = document.createElement('input');
    inp.type = 'datetime-local'; inp.required = true; inp.value = String(l.start_time).slice(0, 16); inp.name = 'desired_start'; lab.appendChild(inp);
    var go = C.button('Перенести', 'primary'); go.type = 'submit';
    f.append(lab, go); out.replaceChildren(f);
    f.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!inp.value || inp.value === String(l.start_time).slice(0, 16)) { fail(new Error('Выберите новое время.')); return; }
      go.disabled = true;
      post('/teacher/lesson/reschedule', { lesson_id: l.id, desired_start: inp.value, note: 'CABINET_SCHEDULE' }).then(function (r) {
        done(r.status === 'waiting_occupant' ? 'Запрос создан — нужно согласие другого ученика.' : 'Занятие перенесено.');
      }, function (er) { go.disabled = false; fail(er); });
    });
    inp.focus();
  }

  function cancelPanel(l, out, m, done, fail) {
    var f = C.el('form', 'sch-form'), lab = C.el('label', '', 'Причина отмены (можно оставить пустой)'), inp = document.createElement('input');
    inp.name = 'reason'; inp.maxLength = 300; lab.appendChild(inp);
    f.append(lab, C.el('p', 'sch-ok', 'Отменить занятие? Оплата и минуты ученика не сгорят.'));
    var go = C.button('Да, отменить занятие', 'primary'); go.type = 'submit'; f.appendChild(go); out.replaceChildren(f);
    f.addEventListener('submit', function (e) {
      e.preventDefault(); go.disabled = true;
      post('/teacher/lesson/cancel', { lesson_id: l.id, reason: inp.value }).then(function () { done('Занятие отменено без штрафа.'); }, function (er) { go.disabled = false; fail(er); });
    });
    inp.focus();
  }

  var HUMAN = { PHYSICS: 'Физика', CHEMISTRY: 'Химия', MATH: 'Математика', SCHOOL: 'Школьная программа', EGE: 'ЕГЭ', OGE: 'ОГЭ', OLYMPIAD: 'Олимпиада' };
  function h(x) { return HUMAN[x] || x || ''; }

  function createPanel() {
    var f = C.el('form', 'sch-form'), out = C.el('div'); out.setAttribute('aria-live', 'polite');
    function field(label, ctrl) { var l = C.el('label', '', label); l.appendChild(ctrl); f.appendChild(l); return ctrl; }
    var stu = document.createElement('select'); stu.name = 'user_id'; stu.required = true; stu.innerHTML = '<option value="">Загружаю учеников…</option>';
    field('Ученик', stu);
    var prog = document.createElement('select'); prog.name = 'program_id'; prog.disabled = true; prog.innerHTML = '<option value="">Сначала выберите ученика</option>';
    field('Направление', prog);
    var when = document.createElement('input'); when.type = 'datetime-local'; when.name = 'start_time'; when.required = true;
    var n = new Date(Date.now() + 3600000); n.setMinutes(Math.ceil(n.getMinutes() / 30) * 30, 0, 0); when.value = ymd(n) + 'T' + p2(n.getHours()) + ':' + p2(n.getMinutes());
    field('Дата и время', when);
    var dur = document.createElement('select'); dur.name = 'duration_minutes';
    [30, 45, 60, 90, 120].forEach(function (v) { var o = document.createElement('option'); o.value = v; o.textContent = v + ' минут'; if (v === 60) o.selected = true; dur.appendChild(o); });
    field('Длительность', dur);
    var pay = document.createElement('select'); pay.name = 'payment_mode';
    [['AWAITING_PAYMENT', 'Оплата до занятия'], ['BALANCE', 'Из баланса ученика'], ['FREE', 'Бесплатное занятие']].forEach(function (v) { var o = document.createElement('option'); o.value = v[0]; o.textContent = v[1]; pay.appendChild(o); });
    field('Оплата', pay);
    var go = C.button('Создать урок', 'primary'); go.type = 'submit'; f.append(out, go);
    function fail(e) { out.replaceChildren(Object.assign(C.el('p', 'sch-err', msg(tr(e))), { role: 'alert' })); }
    var programs = [];
    C.api('/teacher/crm/students?limit=500').then(function (d) {
      stu.innerHTML = '<option value="">Выберите ученика</option>';
      (d.items || []).forEach(function (s) { var o = document.createElement('option'); o.value = s.id; o.textContent = s.name || 'Ученик'; stu.appendChild(o); });
    }, function (e) { stu.innerHTML = '<option value="">—</option>'; fail(e); });
    stu.addEventListener('change', function () {
      programs = []; prog.disabled = true; out.replaceChildren(); if (!stu.value) return;
      C.api('/teacher/lesson/options?user_id=' + encodeURIComponent(stu.value)).then(function (d) {
        programs = d.programs || [];
        prog.innerHTML = '<option value="">Выберите направление</option>';
        programs.forEach(function (p) { var o = document.createElement('option'); o.value = p.id; o.textContent = h(p.subject) + ' · ' + h(p.study_goal); prog.appendChild(o); });
        if (programs.length === 1) prog.value = String(programs[0].id);
        prog.disabled = false;
        if (!programs.length) out.replaceChildren(C.el('p', 'sch-err', 'У ученика нет подтверждённого направления. Добавьте его в карточке ученика.'));
      }, fail);
    });
    var m = C.modal({ title: 'Новый урок', body: f, actions: [{ text: 'Закрыть', kind: 'secondary' }] });
    f.addEventListener('submit', function (e) {
      e.preventDefault(); out.replaceChildren();
      if (!stu.value) { fail(new Error('Выберите ученика.')); return; }
      var b = { user_id: Number(stu.value), start_time: when.value, duration_minutes: Number(dur.value), payment_mode: pay.value };
      if (prog.value) b.program_id = Number(prog.value);
      go.disabled = true;
      post('/teacher/lesson/create', b).then(function (r) {
        m.close(); C.toast(r.already_created ? 'Это занятие уже создано.' : 'Занятие назначено.');
        var d = parseDay(when.value.slice(0, 10)), mon = monday(0); weekOffset = Math.floor((d - mon) / (7 * 86400000)); load();
      }, function (er) { go.disabled = false; fail(er); });
    });
  }

  C.boot({
    role: 'teacher', menu: C.TEACHER_MENU, active: 'schedule',
    render: function (main) {
      main.appendChild(C.el('h1', 'cab-title', 'Расписание'));
      bar = C.el('div', 'sch-bar');
      var prev = C.button('← Неделя', 'secondary', function () { weekOffset--; load(); });
      var next = C.button('Неделя →', 'secondary', function () { weekOffset++; load(); });
      var tod = C.button('Сегодня', 'secondary', function () { weekOffset = 0; load(); });
      rangeEl = C.el('div', 'sch-range'); rangeEl.setAttribute('aria-live', 'polite');
      var add = C.button('+ Урок', 'primary', createPanel);
      bar.append(prev, rangeEl, next, tod, add);
      grid = C.el('div', 'sch-week'); grid.setAttribute('aria-live', 'polite');
      for (var i = 0; i < 3; i++) grid.appendChild(C.el('div', 'c-skel'));
      main.append(bar, grid);
      document.title = 'Расписание — Аделия';
      document.addEventListener('adelia:lesson-payment-changed', function () { setTimeout(load, 250); });
      return load();
    }
  });
})();
