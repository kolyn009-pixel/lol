/* Ученик: «Занятия». API как в старом кабинете: /student/schedule, /student/lesson/join,
   /student/self-service/lesson-actions|cancel|sickness, /student/reschedule/free-slots|request */
(function () {
  'use strict';
  var A = '/app/', body, tab = 'future', items = [], loading = false;
  var LS = { CONFIRMED: 'Подтверждено', PENDING: 'Ждёт подтверждения', IN_PROGRESS: 'Идёт занятие', COMPLETED: 'Проведено', CANCELLED: 'Отменено', REJECTED: 'Отклонено' };

  function ts(l) { var d = new Date(S.stamp(l)); return isNaN(d) ? 0 : d.getTime(); }
  function te(l) { var d = new Date(S.stamp(l, 'end')); return isNaN(d) ? ts(l) : d.getTime(); }
  function isUp(l) { return te(l) >= Date.now() && ['cancelled', 'completed'].indexOf(String(l.ui_state || '').toLowerCase()) < 0 && String(l.lesson_status || '').toUpperCase() !== 'CANCELLED'; }

  function join(l, btn) {
    var fb = A + 'lesson/?id=' + encodeURIComponent(l.id); btn.disabled = true;
    C.api('/student/lesson/join', { method: 'POST', body: { lesson_id: l.id } }).then(function (r) {
      var u = (r && r.meeting_url) || l.meeting_url;
      if (u && /^https?:\/\//i.test(u)) window.open(u, '_blank', 'noopener'); else location.href = fb;
    }, function (e) {
      if (e.status === 401) { location.replace(A); return; }
      C.toast(e.message || 'Не получилось войти.');
      if (l.meeting_url && /^https?:\/\//i.test(l.meeting_url)) window.open(l.meeting_url, '_blank', 'noopener');
    }).then(function () { btn.disabled = false; });
  }

  /* ---- управление занятием ---- */
  function manage(l, box) {
    box.replaceChildren(C.el('p', 'c-row-s', 'Смотрю, что можно сделать…'));
    C.api('/student/self-service/lesson-actions?lesson_id=' + encodeURIComponent(l.id)).then(function (a) {
      var w = C.el('div', 'st-panel');
      if (!a.can_cancel) { w.appendChild(C.el('p', 'c-row-s', 'Для этого занятия перенос и отмена недоступны. Напиши преподавателю.')); box.replaceChildren(w); return; }
      var acts = C.el('div', 'c-actions'), out = C.el('div'), pane = C.el('div');
      acts.appendChild(C.button('Перенести', 'secondary', function () { reschedule(l, pane); }));
      acts.appendChild(C.button('Больничный', 'secondary', function () { sick(l, pane); }));
      acts.appendChild(C.button('Отменить', 'secondary', function () { cancel(l, a, out, box); }));
      w.append(acts, pane, out); box.replaceChildren(w);
    }, function (e) { box.replaceChildren(C.error(e.message || 'Не получилось загрузить действия.')); });
  }

  function cancel(l, a, out, box) {
    var t = a.teacher_day_off ? 'Преподаватель отметил это время как выходной. Отмена без штрафа, оплата и минуты сохранятся. Отменить занятие?'
      : a.late_cancel ? 'До занятия меньше двух часов. Поздняя отмена может быть списана. Продолжить?' : 'Отменить это занятие?';
    C.modal({ title: 'Отмена занятия', body: t, actions: [
      { text: 'Не отменять', kind: 'secondary' },
      { text: 'Отменить занятие', kind: 'primary', onClick: function () {
        C.api('/student/self-service/cancel', { method: 'POST', body: { lesson_id: l.id } }).then(function () {
          box.replaceChildren(S.note('ok', 'Занятие отменено.')); C.toast('Занятие отменено.'); load();
        }, function (e) { out.replaceChildren(S.note('bad', e.message || 'Не получилось отменить.')); });
      } }
    ] });
  }

  function sick(l, pane) {
    var ta = document.createElement('textarea'); ta.maxLength = 500; ta.rows = 3; var out = C.el('div');
    var send = C.button('Оформить больничный', 'primary', function () {
      send.disabled = true;
      C.api('/student/self-service/sickness', { method: 'POST', body: { lesson_id: l.id, comment: ta.value } }).then(function (r) {
        pane.replaceChildren(S.note('ok', 'Больничный оформлен' + (r && r.needs_admin_decision ? ' · преподаватель подтвердит решение.' : '.'))); load();
      }, function (e) { send.disabled = false; out.replaceChildren(S.note('bad', e.message || 'Не получилось.')); });
    });
    pane.replaceChildren(S.field('Комментарий (необязательно)', ta), send, out);
  }

  function sendMove(l, start, note, pane) {
    pane.replaceChildren(C.el('p', 'c-row-s', 'Отправляю…'));
    C.api('/student/reschedule/request', { method: 'POST', body: { lesson_id: l.id, desired_start: start, note: note || 'STUDENT_WEB_REQUEST' } }).then(function (r) {
      pane.replaceChildren(S.note('ok', 'Заявка' + (r && r.request_id ? ' #' + r.request_id : '') + ' отправлена. Занятие остаётся на месте до подтверждения преподавателя.'));
    }, function (e) { pane.replaceChildren(S.note('bad', e.message === 'active_reschedule_exists' ? 'По этому занятию уже есть заявка на перенос.' : (e.message || 'Не получилось отправить.'))); });
  }

  function reschedule(l, pane) {
    pane.replaceChildren(C.el('p', 'c-row-s', 'Ищу свободные окна…'));
    C.api('/student/reschedule/free-slots?lesson_id=' + encodeURIComponent(l.id) + '&days=14').then(function (d) {
      var f = document.createDocumentFragment(), days = d.items || [];
      f.appendChild(C.el('p', 'c-row-s', 'Переносится только это занятие. Постоянное расписание не меняется.'));
      days.forEach(function (day) {
        var dd = String(day.date || '').slice(0, 10), h = C.el('div', 'st-slotday', S.date(dd) || dd), g = C.el('div', 'st-slots');
        (day.slots || []).forEach(function (s) {
          g.appendChild(C.button(s.label || C.hhmm(s.start_time), 'secondary', function () {
            C.modal({ title: 'Перенос занятия', body: 'Перенести только это занятие на ' + S.dt(s.start_time) + '?', actions: [{ text: 'Нет', kind: 'secondary' }, { text: 'Перенести', kind: 'primary', onClick: function () { sendMove(l, s.start_time, 'Свободный слот выбран на сайте', pane); } }] });
          }));
        });
        f.append(h, g);
      });
      if (!days.length) f.appendChild(C.el('p', 'c-row-s', 'Свободных окон на 14 дней нет. Можно предложить своё время.'));
      f.appendChild(C.button('Предложить своё время', 'text', function () {
        var inp = document.createElement('input'); inp.type = 'datetime-local'; inp.step = 900;
        var ta = document.createElement('textarea'); ta.rows = 2; ta.maxLength = 300; ta.placeholder = 'Например: могу только после школы';
        var out = C.el('div');
        pane.replaceChildren(S.field('Дата и время', inp), S.field('Комментарий преподавателю', ta), C.button('Предложить перенос', 'primary', function () {
          if (!inp.value) { out.replaceChildren(S.note('bad', 'Выбери дату и время.')); return; }
          sendMove(l, inp.value, ta.value, pane);
        }), out);
      }));
      pane.replaceChildren(f);
    }, function (e) { pane.replaceChildren(C.error(e.message || 'Не получилось загрузить окна.')); });
  }

  /* ---- список ---- */
  function row(l, first) {
    var r = C.el('article', 'st-lesson'), main = C.el('div', 'st-lesson-main'), t = C.el('div', 'c-row-t');
    var tm = C.hhmm(S.stamp(l)), tend = C.hhmm(S.stamp(l, 'end')), dt = S.date(S.stamp(l));
    t.appendChild(C.el('div', 'c-big st-when', (dt ? dt + ', ' : '') + tm + (tend ? '–' + tend : '')));
    var meta = C.el('div', 'c-lesson-meta');
    meta.appendChild(C.el('span', 'c-tag', 'Индивидуально'));
    var sb = C.subjectLabel(l.subject); if (sb) meta.appendChild(C.el('span', '', sb));
    var g = C.subjectLabel(l.study_goal); if (g && g !== sb) meta.appendChild(C.el('span', '', g));
    if (l.duration_minutes) meta.appendChild(C.el('span', '', l.duration_minutes + ' мин'));
    var ls = LS[String(l.lesson_status || '').toUpperCase()]; if (ls) meta.appendChild(C.el('span', '', ls));
    var ps = C.payStatus(l.payment_status); if (ps) meta.appendChild(C.el('span', 'c-pay ' + ps.cls, ps.text));
    t.appendChild(meta); main.appendChild(t);
    var act = C.el('div', 'c-actions'), box = C.el('div', 'st-manage');
    if (isUp(l)) {
      if (first || l.started_at) act.appendChild(C.button(l.started_at ? 'Вернуться на урок' : 'Войти на урок', 'primary', function (ev) { join(l, ev.currentTarget); }));
      var mb = C.button('Перенос и отмена', 'secondary', function () { if (box.childNodes.length) { box.replaceChildren(); mb.setAttribute('aria-expanded', 'false'); } else { manage(l, box); mb.setAttribute('aria-expanded', 'true'); } });
      mb.setAttribute('aria-expanded', 'false'); act.appendChild(mb);
    } else act.appendChild(C.button('Открыть', 'secondary', A + 'lesson/?id=' + encodeURIComponent(l.id)));
    main.appendChild(act); r.append(main, box); return r;
  }

  function paint() {
    var up = items.filter(isUp).sort(function (a, b) { return ts(a) - ts(b); });
    var past = items.filter(function (x) { return up.indexOf(x) < 0; }).sort(function (a, b) { return ts(b) - ts(a); }).slice(0, 30);
    var f = document.createDocumentFragment();
    f.append(C.el('h1', 'cab-title', 'Занятия'), C.el('p', 'cab-sub', up.length ? 'Впереди: ' + up.length + ' ' + S.plural(up.length, 'занятие', 'занятия', 'занятий') : 'Ближайших занятий нет'));
    f.appendChild(S.tabs([['future', 'Предстоящие'], ['past', 'Прошедшие']], tab, function (k) { tab = k; paint(); }));
    var list = tab === 'future' ? up : past, s = C.section(tab === 'future' ? '01' : '02', tab === 'future' ? 'Ближайшие' : 'История');
    if (!list.length) s.appendChild(C.empty(tab === 'future' ? 'Предстоящих занятий нет. Напиши преподавателю, чтобы записаться.' : 'История занятий пока пуста.'));
    list.forEach(function (l, i) { s.appendChild(row(l, tab === 'future' && i === 0)); });
    f.appendChild(s); body.replaceChildren(f);
  }

  function load() {
    if (loading) return Promise.resolve(); loading = true;
    return C.api('/student/schedule?limit=60').then(function (d) { items = (d && d.items) || []; paint(); }, function (e) {
      if (e.status === 401) { location.replace(A); return; }
      if (!items.length) body.replaceChildren(C.error(e.message, load)); else C.toast('Не удалось обновить занятия.');
    }).then(function () { loading = false; });
  }

  C.boot({
    role: 'student', menu: C.STUDENT_MENU, active: 'lessons',
    render: function (main) {
      body = document.createElement('div'); body.setAttribute('aria-live', 'polite');
      for (var i = 0; i < 3; i++) body.appendChild(C.el('div', 'c-skel'));
      main.appendChild(body); document.title = 'Занятия — Аделия'; return load();
    }
  });
})();
