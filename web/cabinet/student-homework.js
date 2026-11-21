/* Ученик: «Домашние задания». API как в старом кабинете: GET /student/homework, /student/homework/detail?id=,
   /student/homework/feedback?id=; POST /student/homework/submit {homework_id, responses, attempt_number},
   /student/homework/manual-submit {homework_id, comment}, /student/homework/external/open|status */
(function () {
  'use strict';
  var A = '/app/', body, tab = 'active', list = [], loading = false;
  var DONE = ['CHECKED', 'COMPLETED', 'ACCEPTED'], SENT = ['SUBMITTED', 'UNDER_REVIEW'];
  var PROV = { RESHU_EGE: 'Решу ЕГЭ', RESHU_OGE: 'Решу ОГЭ' };

  function st(h) { return String(h.status || '').toUpperCase(); }
  function group(h) { var s = st(h); return DONE.indexOf(s) >= 0 ? 'done' : SENT.indexOf(s) >= 0 ? 'sent' : 'active'; }
  function label(h) { var u = h.status_ui; if (u && typeof u === 'object') return u.label || u.text || u.title || ''; return u ? String(u) : (h.status || ''); }
  function kind(h) { return h.external ? (PROV[h.external.provider] || 'Внешний вариант') : h.interactive_task_count ? 'Интерактивное ДЗ' : 'ДЗ'; }
  function key(id) { return 'adelia_hw_draft_' + id; }
  function getDraft(id) { try { return JSON.parse(localStorage.getItem(key(id)) || '{}'); } catch (e) { return {}; } }
  function setDraft(id, v) { try { localStorage.setItem(key(id), JSON.stringify(v)); } catch (e) {} }
  function clrDraft(id) { try { localStorage.removeItem(key(id)); } catch (e) {} }
  function curId() { var m = location.hash.match(/(\d+)/); return m ? +m[1] : 0; }

  /* ---- список ---- */
  function paintList() {
    var cnt = { active: 0, sent: 0, done: 0 }; list.forEach(function (h) { cnt[group(h)]++; });
    var f = document.createDocumentFragment();
    f.append(C.el('h1', 'cab-title', 'Домашние задания'), C.el('p', 'cab-sub', cnt.active ? 'Ждут тебя: ' + cnt.active : 'Активных заданий нет'));
    f.appendChild(S.tabs([['active', 'Активные · ' + cnt.active], ['sent', 'Сданные · ' + cnt.sent], ['done', 'Проверенные · ' + cnt.done]], tab, function (k) { tab = k; paintList(); }));
    var s = C.section('01', { active: 'К выполнению', sent: 'На проверке', done: 'Проверено' }[tab]), rows = list.filter(function (h) { return group(h) === tab; });
    rows.sort(function (a, b) { return tab === 'active' ? String(a.deadline || '9').localeCompare(String(b.deadline || '9')) : String(b.deadline || '').localeCompare(String(a.deadline || '')); });
    if (!rows.length) s.appendChild(C.empty(tab === 'active' ? 'Заданий нет — можно выдохнуть.' : 'Здесь пока пусто.'));
    rows.forEach(function (h) {
      var r = C.el('a', 'c-row st-hwrow'); r.href = '#' + h.id; r.addEventListener('click', function (e) { e.preventDefault(); location.hash = String(h.id); });
      var t = C.el('div', 'c-row-t'); t.appendChild(C.el('div', 'st-hwt', h.title || 'Домашнее задание'));
      var sub = [kind(h), label(h), h.interactive_task_count ? h.interactive_task_count + ' заданий' : '', h.deadline ? 'до ' + S.date(h.deadline) : ''].filter(Boolean).join(' · ');
      t.appendChild(C.el('div', 'c-row-s', sub)); r.appendChild(t); r.appendChild(C.el('span', 'c-row-s', 'Открыть →')); s.appendChild(r);
    });
    f.appendChild(s); body.replaceChildren(f);
  }

  function loadList() {
    if (loading) return Promise.resolve(); loading = true;
    return C.api('/student/homework').then(function (d) { list = (d && d.items) || []; if (!curId()) paintList(); }, function (e) {
      if (e.status === 401) { location.replace(A); return; }
      if (!list.length) body.replaceChildren(C.error(e.message, loadList)); else C.toast('Не удалось обновить задания.');
    }).then(function () { loading = false; });
  }

  /* ---- карточка ---- */
  function back() { return C.button('← К заданиям', 'text', function () { location.hash = ''; }); }
  function links(title, arr, mk) {
    if (!arr || !arr.length) return null; var s = C.el('div', 'st-sub'); s.appendChild(C.el('p', 'c-label', title));
    arr.forEach(function (x) { var u = mk(x); if (!u.href) return; var a = C.el('a', 'c-row st-file', u.text); a.href = u.href; a.target = '_blank'; a.rel = 'noopener'; s.appendChild(a); });
    return s.childNodes.length > 1 ? s : null;
  }
  function feedbackBlock(f) {
    var rows = f.task_feedback || [], rv = f.reviews || []; if (!rows.length && !rv.length) return null;
    var s = C.section('', 'Разбор преподавателя');
    if (rv[0]) {
      var r = rv[0], res = r.result === 'ACCEPTED' ? 'Принято' : r.result === 'REVISION' ? 'На доработке' : (r.result || 'Проверено');
      s.appendChild(C.el('div', 'c-big st-res', res + (r.accuracy_percent != null ? ' · ' + r.accuracy_percent + '%' : '')));
      if (r.tutor_comment) s.appendChild(C.el('p', 'st-comment', r.tutor_comment));
    }
    rows.forEach(function (x) {
      var d = C.el('div', 'c-topic'), h = C.el('div', 'c-topic-h');
      h.append(C.el('span', '', (x.title || ('Задание ' + x.task_id)) + (x.task_number ? ' · №' + x.task_number : '')), C.el('span', '', 'попытка ' + x.attempt_number));
      d.appendChild(h);
      if (x.teacher_comment) d.appendChild(C.el('p', 'st-comment', x.teacher_comment));
      var m = x.override_correct === 1 ? 'Преподаватель отметил верным' : x.override_correct === 0 ? 'Нужно исправить ответ' : '';
      if (x.override_points != null) m += (m ? ' · ' : '') + x.override_points + ' б.';
      if (m) d.appendChild(C.el('div', 'c-row-s', m)); s.appendChild(d);
    });
    return s;
  }
  function resultBlock(r) {
    var w = C.el('div', 'st-result'); w.setAttribute('role', 'status');
    w.appendChild(C.el('div', 'c-big', Math.round(S.num(r.score_percent)) + '%'));
    w.appendChild(C.el('p', 'c-row-s', 'Попытка ' + (r.attempt_number || 1) + ' · верно ' + (r.correct_tasks || 0) + ' из ' + (r.total_tasks || 0) + ' · ' + (r.earned_points || 0) + ' / ' + (r.total_points || 0) + ' баллов' + (r.unchecked_tasks ? ' · ' + r.unchecked_tasks + ' проверит преподаватель' : '')));
    (r.details || []).forEach(function (x, i) {
      var d = C.el('div', 'c-row'); d.appendChild(C.el('span', '', 'Задание ' + (i + 1)));
      d.appendChild(C.el('span', 'c-pay ' + (!x.auto_checked ? '' : x.is_correct ? 'ok' : 'due'), !x.auto_checked ? 'Проверит преподаватель' : x.is_correct ? 'Верно' : 'Есть ошибка')); w.appendChild(d);
    });
    w.appendChild(S.note(r.auto_accepted ? 'ok' : '', r.auto_accepted ? 'Работа принята: всё проверено автоматически.' : 'Ответы отправлены. Теперь работа ждёт проверки преподавателя.'));
    return w;
  }

  function tasksForm(id, h, tasks, f, root) {
    var can = f.can_submit !== false, draft = getDraft(id), inputs = {}, s = C.section('', f.retry_allowed ? 'Исправление' : can ? 'Решение' : 'Ответы отправлены');
    var prog = C.el('p', 'c-row-s'); s.appendChild(prog);
    function upd() { var n = 0, v = {}; Object.keys(inputs).forEach(function (k) { v[k] = inputs[k].value; if (inputs[k].value.trim()) n++; }); if (can) setDraft(id, v); prog.textContent = 'Заполнено: ' + n + ' из ' + tasks.length; }
    tasks.forEach(function (t, i) {
      var d = C.el('div', 'st-task'), top = C.el('div', 'c-topic-h');
      top.append(C.el('span', 'c-tag', 'Задание ' + (i + 1) + (t.task_number ? ' · №' + t.task_number : '')), C.el('span', 'c-row-s', (t.points || 1) + ' б.'));
      d.append(top, C.el('div', 'st-title', t.title || t.topic || 'Задача'), C.el('p', 'st-stmt', t.statement || ''));
      var inp = document.createElement('input'); inp.type = 'text'; inp.autocomplete = 'off';
      if (String(t.answer_type || '').toUpperCase() === 'NUMBER') { inp.inputMode = 'decimal'; }
      inp.placeholder = 'Введи ответ'; inp.value = draft[String(t.id)] != null ? draft[String(t.id)] : ''; inp.disabled = !can; inp.addEventListener('input', upd);
      inputs[t.id] = inp; d.appendChild(S.field('Твой ответ', inp)); s.appendChild(d);
    });
    upd();
    if (can) {
      var out = C.el('div'), b = C.button(f.retry_allowed ? 'Отправить исправленную работу' : 'Проверить и отправить', 'primary', function () {
        var responses = {}; Object.keys(inputs).forEach(function (k) { responses[k] = inputs[k].value; });
        b.disabled = true; b.textContent = 'Отправляю…';
        C.api('/student/homework/submit', { method: 'POST', body: { homework_id: +id, responses: responses, attempt_number: f.next_attempt_number || 1 } }).then(function (r) {
          clrDraft(id); b.remove(); out.replaceChildren(resultBlock(r)); C.toast('Ответы отправлены.'); loadList();
        }, function (e) { b.disabled = false; b.textContent = f.retry_allowed ? 'Отправить исправленную работу' : 'Проверить и отправить'; out.replaceChildren(S.note('bad', e.message || 'Не получилось отправить.')); });
      });
      s.append(b, out);
    }
    return s;
  }

  function manualForm(id, f) {
    var s = C.section('', f.retry_allowed ? 'Отправить исправленную работу' : 'Отметить выполнение');
    s.appendChild(C.el('p', 'c-row-s', 'Когда закончишь, отметь работу выполненной. Можно оставить комментарий преподавателю.'));
    var ta = document.createElement('textarea'); ta.rows = 3; ta.maxLength = 1000; ta.value = getDraft(id).comment || ''; ta.addEventListener('input', function () { setDraft(id, { comment: ta.value }); });
    var out = C.el('div'), b = C.button(f.retry_allowed ? 'Отправить повторно' : 'Я выполнил(а) ДЗ', 'primary', function () {
      b.disabled = true;
      C.api('/student/homework/manual-submit', { method: 'POST', body: { homework_id: +id, comment: ta.value } }).then(function () {
        clrDraft(id); b.remove(); out.replaceChildren(S.note('ok', 'Работа отправлена преподавателю на проверку.')); loadList();
      }, function (e) { b.disabled = false; out.replaceChildren(S.note('bad', e.message || 'Не получилось отправить.')); });
    });
    s.append(S.field('Комментарий', ta), b, out); return s;
  }

  function externalBlock(id, ext) {
    var s = C.section('', PROV[ext.provider] || 'Внешний вариант'), out = C.el('div');
    s.appendChild(C.button('Открыть вариант ↗', 'primary', function (ev) {
      var b = ev.currentTarget, tabw = window.open('about:blank', '_blank'); b.disabled = true;
      C.api('/student/homework/external/open', { method: 'POST', body: { homework_id: +id } }).then(function (r) { var u = S.safeUrl(r && r.url) || ''; if (u && tabw) tabw.location = u; else if (u) location.href = u; else if (tabw) tabw.close(); }, function () { if (tabw) tabw.close(); out.replaceChildren(S.note('bad', 'Не удалось открыть вариант.')); }).then(function () { b.disabled = false; });
    }));
    s.appendChild(C.el('p', 'c-row-s', 'Когда закончишь, отметь статус — преподаватель увидит его вместе со ссылкой.'));
    var a = C.el('div', 'c-actions');
    [['WORKING', 'Решаю'], ['DONE', 'Сделал(а)'], ['NEED_MORE_TIME', 'Нужно время']].forEach(function (x) {
      a.appendChild(C.button(x[1], 'secondary', function () {
        C.api('/student/homework/external/status', { method: 'POST', body: { homework_id: +id, status: x[0] } }).then(function () { out.replaceChildren(S.note('ok', 'Статус отправлен преподавателю.')); }, function () { out.replaceChildren(S.note('bad', 'Не удалось отправить статус.')); });
      }));
    });
    s.append(a, out); return s;
  }

  function openCard(id) {
    body.replaceChildren(C.el('div', 'c-skel'), C.el('div', 'c-skel'));
    Promise.all([C.api('/student/homework/detail?id=' + id), C.api('/student/homework/feedback?id=' + id).catch(function () { return { can_submit: true, next_attempt_number: 1 }; })]).then(function (r) {
      if (curId() !== id) return;
      var d = r[0], f = r[1], h = d.homework || {}, tasks = d.tasks || [], fr = document.createDocumentFragment();
      fr.appendChild(back()); fr.appendChild(C.el('h1', 'cab-title st-h1', h.title || 'Домашнее задание'));
      var st0 = f.completed ? 'Принято' : f.pending_review ? 'Сдано · ждёт проверки' : f.retry_allowed ? 'На доработке' : label(h);
      fr.appendChild(C.el('p', 'cab-sub', [st0, h.deadline ? 'срок: ' + S.dt(h.deadline) : ''].filter(Boolean).join(' · ')));
      if (h.description) fr.appendChild(C.el('p', 'st-desc', h.description));
      var fb = feedbackBlock(f); if (fb) fr.appendChild(fb);
      if (f.completed) fr.appendChild(S.note('ok', 'Работа принята преподавателем. Новая попытка не нужна.'));
      else if (f.pending_review) fr.appendChild(S.note('', 'Ответы уже у преподавателя. Новая попытка откроется, только если работу вернут на доработку.'));
      else if (f.retry_allowed) fr.appendChild(S.note('', 'Работа на доработке: поправь ответы с учётом комментариев и отправь снова.'));
      var m = links('Материалы', d.materials, function (x) { return { href: S.safeUrl(x.external_url), text: x.title || 'Материал' }; }); if (m) fr.appendChild(m);
      var at = links('Файлы задания', d.attachments, function (x) { return { href: S.safeUrl(x.url), text: (x.filename || 'Файл') + ' ↗' }; }); if (at) fr.appendChild(at);
      if (d.external) fr.appendChild(externalBlock(id, d.external));
      else if (tasks.length) fr.appendChild(tasksForm(id, h, tasks, f, fr));
      else if (f.can_submit !== false && !f.completed && !f.pending_review) fr.appendChild(manualForm(id, f));
      fr.appendChild(C.el('p', 'c-row-s st-classic')).appendChild(C.button('Открыть в старом кабинете', 'text', A + '?classic=1'));
      body.replaceChildren(fr); window.scrollTo(0, 0);
    }, function (e) { if (e.status === 401) { location.replace(A); return; } body.replaceChildren(back(), C.error(e.message || 'Не получилось открыть задание.', function () { openCard(id); })); });
  }

  function route() { var id = curId(); if (id) openCard(id); else if (list.length || !loading) { paintList(); loadList(); } }

  C.boot({
    role: 'student', menu: C.STUDENT_MENU, active: 'homework',
    render: function (main) {
      body = document.createElement('div'); body.setAttribute('aria-live', 'polite');
      for (var i = 0; i < 3; i++) body.appendChild(C.el('div', 'c-skel'));
      main.appendChild(body); document.title = 'Домашние задания — Аделия';
      window.addEventListener('hashchange', route);
      return curId() ? (openCard(curId()), loadList()) : loadList();
    }
  });
})();
