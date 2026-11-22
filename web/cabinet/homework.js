/* Кабинет «Журнал»: Работы преподавателя. Эндпоинты старого кабинета: homework-center, detail, task-feedback, finalize. */
(function () {
  'use strict';
  var el = function (t, c, x) { return C.el(t, c, x); };
  var MENU = C.TEACHER_MENU;
  var STAT = { ASSIGNED: 'Назначено', SUBMITTED: 'Сдано', UNDER_REVIEW: 'На проверке', REVISION: 'Доработка', REVIEWED: 'Проверено', COMPLETED: 'Завершено', CANCELLED: 'Отменено' };
  var TYPE = { INTERACTIVE: 'Интерактивное', EXTERNAL: 'Решу ЕГЭ/ОГЭ' };
  var TABS = [['review', 'На проверке'], ['assigned', 'Выданные'], ['done', 'Проверенные']];
  var MON = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  var root, items = [], tab = 'review', loaded = false, loading = false;

  function dt(s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/); return m ? Number(m[3]) + ' ' + MON[Number(m[2]) - 1] + (m[4] ? ', ' + m[4] + ':' + m[5] : '') : '—'; }
  function err(e) { var m = e && e.message || ''; return m === 'homework_not_found' ? 'Работа не найдена.' : /^[a-z_]+$/.test(m) ? 'Не получилось. Обновите страницу и повторите.' : m || 'Не получилось. Попробуйте ещё раз.'; }
  function inTab(h, t) {
    var st = String(h.status || '').toUpperCase();
    if (t === 'review') return Number(h.pending_submissions) > 0;
    if (t === 'assigned') return ['ASSIGNED', 'REVISION', 'SUBMITTED', 'UNDER_REVIEW'].indexOf(st) >= 0 && !(Number(h.pending_submissions) > 0);
    return st === 'REVIEWED' || st === 'COMPLETED';
  }

  /* ---- список ---- */
  function list() {
    var f = document.createDocumentFragment();
    var bar = el('div', 'hw-bar'), tabs = el('div', 'hw-tabs'); tabs.setAttribute('role', 'tablist');
    TABS.forEach(function (t) {
      var n = items.filter(function (h) { return inTab(h, t[0]); }).length;
      var b = el('button', 'hw-tab', t[1] + ' · ' + n); b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(tab === t[0]));
      b.addEventListener('click', function () { tab = t[0]; paint(); }); tabs.appendChild(b);
    });
    bar.appendChild(tabs); bar.appendChild(C.button('＋ Задать ДЗ', 'primary', '/app/teacher.html?classic=1')); f.appendChild(bar);
    var s = C.section(String(TABS.map(function (t) { return t[0]; }).indexOf(tab) + 1).padStart(2, '0'), TABS.filter(function (t) { return t[0] === tab; })[0][1]);
    var rows = items.filter(function (h) { return inTab(h, tab); });
    if (!rows.length) s.appendChild(C.empty(tab === 'review' ? 'Работ на проверку нет. Когда ученик сдаст, она появится здесь.' : tab === 'assigned' ? 'Выданных работ нет.' : 'Проверенных работ пока нет.'));
    rows.forEach(function (h) {
      var b = el('button', 'hw-row'); b.type = 'button';
      var info = el('span', 'hw-info');
      info.appendChild(el('span', 'hw-title', h.title || 'Домашнее задание'));
      var m = el('span', 'hw-meta'); m.appendChild(el('span', '', (h.name || 'Ученик') + (h.grade ? ' · ' + h.grade + ' кл.' : '')));
      m.appendChild(el('span', '', 'Срок: ' + dt(h.deadline)));
      if (TYPE[h.homework_type]) m.appendChild(el('span', '', TYPE[h.homework_type]));
      m.appendChild(el('span', Number(h.pending_submissions) > 0 ? 'hw-due' : '', Number(h.pending_submissions) > 0 ? 'Проверить: ' + h.pending_submissions : (STAT[h.status] || h.status || '')));
      if (h.auto_score != null) m.appendChild(el('span', '', Math.round(Number(h.auto_score)) + '%'));
      info.appendChild(m); b.appendChild(info); b.appendChild(el('span', 'hw-arrow', '→'));
      b.setAttribute('aria-label', 'Открыть: ' + (h.title || 'работа') + ', ' + (h.name || ''));
      b.addEventListener('click', function () { openDetail(h.id); }); s.appendChild(b);
    });
    f.appendChild(s); return f;
  }
  function paint() { root.replaceChildren(list()); }

  /* ---- карточка ---- */
  function openDetail(id) {
    root.replaceChildren(el('div', 'c-skel'));
    C.api('/teacher/homework-center/detail?id=' + encodeURIComponent(id)).then(function (d) { root.replaceChildren(card(d, id)); scrollTo(0, 0); },
      function (e) { root.replaceChildren(backBtn(), C.error(err(e), function () { openDetail(id); })); });
  }
  function backBtn() { return C.button('← Все работы', 'text', function () { paint(); load(true); }); }
  function card(d, id) {
    var h = d.homework, w = el('div'), latest = (d.submissions || [])[0];
    w.appendChild(backBtn());
    w.appendChild(el('h2', 'hw-h', h.title || 'Домашнее задание'));
    var m = el('p', 'cab-sub', (h.name || 'Ученик') + ' · срок ' + dt(h.deadline) + ' · ' + (STAT[h.status] || h.status)); w.appendChild(m);
    if (h.description) w.appendChild(el('p', 'hw-desc', h.description));
    if (d.auto_result) { var ar = d.auto_result; w.appendChild(el('p', 'hw-auto', 'Автопроверка: ' + Math.round(Number(ar.score_percent || 0)) + '% · ' + (ar.correct_tasks || 0) + '/' + (ar.total_tasks || 0) + ' верно · ' + (ar.earned_points || 0) + '/' + (ar.total_points || 0) + ' баллов')); }
    if (d.external && d.external.url) { var xl = C.button('Открыть вариант ↗', 'secondary', d.external.url); xl.target = '_blank'; xl.rel = 'noopener'; w.appendChild(xl); }

    var s1 = C.section('01', 'Ответы ученика');
    if (latest && latest.student_comment) s1.appendChild(el('p', 'hw-says', 'Ученик: «' + latest.student_comment + '»'));
    var groups = d.responses_by_attempt || {}, keys = Object.keys(groups).sort(function (a, b) { return b - a; });
    if (!keys.length) s1.appendChild(C.empty(latest ? 'Ответов по задачам нет: работа без тестовой части.' : 'Ученик ещё не сдавал эту работу.'));
    var canReview = latest && String(latest.status).toUpperCase() === 'SUBMITTED';
    keys.forEach(function (k) {
      var g = el('div', 'hw-attempt'); g.appendChild(el('p', 'c-label', 'ПОПЫТКА ' + k));
      groups[k].forEach(function (r) { g.appendChild(taskBlock(r, k, h, id, canReview && Number(k) === Number(latest.attempt_number || 1))); });
      s1.appendChild(g);
    });
    w.appendChild(s1);

    var files = (d.attachments || []).filter(function (a) { return /^\/api\/homework\/attachment\?id=\d+$/.test(String(a.url || '')); });
    var s2 = C.section('02', 'Файлы задания');
    if (!files.length) s2.appendChild(C.empty('К заданию файлов не прикреплено.'));
    files.forEach(function (a) { var l = C.button((a.filename || 'Файл') + ' ↗', 'secondary', a.url); l.target = '_blank'; l.rel = 'noopener'; l.classList.add('hw-file'); s2.appendChild(l); });
    w.appendChild(s2);

    var s3 = C.section('03', 'Оценка и итог');
    if (!latest) s3.appendChild(C.empty('Проверять пока нечего: ученик не сдал работу.'));
    else if (!canReview) s3.appendChild(el('p', 'hw-says', ({ REVIEWED: 'Работа уже принята.', REVISION: 'Работа отправлена на доработку.' })[String(latest.status).toUpperCase()] || 'Эта попытка уже закрыта.'));
    else {
      var lb = el('label', 'hw-lbl', 'Комментарий ученику'), ta = el('textarea', 'hw-ta'); ta.placeholder = 'Что получилось и что стоит повторить'; lb.appendChild(ta); s3.appendChild(lb);
      var out = el('div'); out.setAttribute('aria-live', 'polite');
      var act = el('div', 'c-actions');
      var fin = function (result, label) {
        var all = act.querySelectorAll('button'); [].forEach.call(all, function (b) { b.disabled = true; }); out.replaceChildren();
        C.api('/teacher/homework-center/finalize', { method: 'POST', body: { homework_id: Number(id), user_id: Number(h.user_id), attempt_number: Number(latest.attempt_number || 1), result: result, comment: ta.value } }).then(function (r) {
          C.toast(label + (r && r.total_points ? ' · ' + r.earned_points + '/' + r.total_points + ' баллов' : '')); openDetail(id);
        }, function (e) { [].forEach.call(all, function (b) { b.disabled = false; }); out.replaceChildren(C.error(err(e))); });
      };
      act.appendChild(C.button('Проверено', 'primary', function () { fin('ACCEPTED', 'Работа принята'); }));
      act.appendChild(C.button('На доработку', 'secondary', function () { fin('REVISION', 'Отправлено на доработку'); }));
      s3.appendChild(act); s3.appendChild(out);
    }
    w.appendChild(s3); return w;
  }
  function taskBlock(r, attempt, h, id, editable) {
    var verdict = r.override_correct != null ? r.override_correct : r.is_correct, max = r.max_points != null ? r.max_points : 1;
    var points = r.override_points != null ? r.override_points : r.points_awarded;
    var b = el('article', 'hw-task');
    b.appendChild(el('div', 'hw-task-t', r.title || ('Задача ' + r.task_id)));
    var a = el('div', 'hw-ans'); a.appendChild(document.createTextNode('Ответ ученика: ')); a.appendChild(el('code', '', r.response_text || '—')); b.appendChild(a);
    if (r.answer) b.appendChild(el('div', 'hw-key', 'Эталон: ' + r.answer));
    b.appendChild(el('div', 'hw-verdict ' + (verdict === 1 || verdict === true ? 'ok' : verdict === 0 || verdict === false ? 'bad' : ''), (verdict === 1 || verdict === true ? 'Верно' : verdict === 0 || verdict === false ? 'Неверно' : 'Ручная проверка') + (points != null ? ' · ' + points + '/' + max + ' б.' : '')));
    if (!editable) { if (r.teacher_comment) b.appendChild(el('div', 'hw-key', 'Комментарий: ' + r.teacher_comment)); return b; }
    var v = verdict === 1 || verdict === true ? '1' : verdict === 0 || verdict === false ? '0' : null;
    var row = el('div', 'c-actions'), bs = [];
    [['1', 'Верно'], ['0', 'Неверно']].forEach(function (x) { var k = el('button', 'hw-vbtn', x[1]); k.type = 'button'; k.setAttribute('aria-pressed', String(v === x[0])); k.addEventListener('click', function () { v = x[0]; bs.forEach(function (y) { y.setAttribute('aria-pressed', String(y === k)); }); }); bs.push(k); row.appendChild(k); });
    var pl = el('label', 'hw-pts', 'Баллы '), pi = el('input'); pi.type = 'number'; pi.min = 0; pi.max = max; pi.step = 0.5; pi.value = points != null ? points : ''; pl.appendChild(pi); row.appendChild(pl); b.appendChild(row);
    var ta = el('textarea', 'hw-ta'); ta.placeholder = 'Комментарий к задаче'; ta.value = r.teacher_comment || ''; ta.setAttribute('aria-label', 'Комментарий к задаче'); b.appendChild(ta);
    var o = el('span', 'hw-state'); o.setAttribute('aria-live', 'polite');
    var sv = C.button('Сохранить разбор', 'secondary', function () {
      sv.disabled = true; o.textContent = '';
      C.api('/teacher/homework-center/task-feedback', { method: 'POST', body: { homework_id: Number(id), task_id: Number(r.task_id), user_id: Number(h.user_id), attempt_number: Number(attempt), comment: ta.value, is_correct: v === null ? null : v === '1', points_awarded: pi.value } })
        .then(function (res) { o.textContent = 'Сохранено' + (res.result && res.result.score_percent != null ? ' · итог ' + Math.round(Number(res.result.score_percent)) + '%' : ''); }, function (e) { o.textContent = err(e); o.className = 'hw-state hw-due'; })
        .then(function () { sv.disabled = false; });
    });
    var f = el('div', 'c-actions'); f.append(sv, o); b.appendChild(f); return b;
  }

  function load(quiet) {
    if (loading) return Promise.resolve(); loading = true;
    return C.api('/teacher/homework-center').then(function (d) { items = d.items || []; loaded = true; paint(); C.setBell(items.filter(function (h) { return inTab(h, 'review'); }).length); },
      function (e) { if (e.status === 401) { location.replace(C.classic('/app/teacher.html')); return; } if (!loaded) root.replaceChildren(C.error(err(e), function () { load(); })); else if (!quiet) C.toast('Не удалось обновить.'); }).then(function () { loading = false; });
  }

  C.boot({
    role: 'teacher', menu: MENU, active: 'homework',
    render: function (main) {
      main.append(el('h1', 'cab-title', 'Работы'), el('p', 'cab-sub', 'Сданное ждёт проверки, выданное ждёт учеников.'));
      root = el('div'); root.setAttribute('aria-live', 'polite'); for (var i = 0; i < 3; i++) root.appendChild(el('div', 'c-skel'));
      main.appendChild(root); document.title = 'Работы — Аделия'; return load();
    }
  });
})();
