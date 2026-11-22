/* Кабинет «Журнал»: Ученики и группы. Эндпоинты — как в старом кабинете. */
(function () {
  'use strict';
  var T = C.legacy('teacher', 'students');
  var E = C.el, DAYS = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'];
  var ERR = { student_not_found: 'Ученик не найден.', unauthorized: 'Войдите заново.', invalid_request: 'Проверьте данные.', invalid_value: 'Проверьте значение поля.', cross_origin_forbidden: 'Обновите страницу и повторите.', group_not_found: 'Группа не найдена.' };
  var st = { tab: 'students', q: '', fmt: 'ALL', subj: 'ALL' }, students = [], groups = [], glessons = [], host, listEl, lastErr;

  function subjKey(s) { var x = String(s || '').toUpperCase(); if (/PHYS|ФИЗ/.test(x)) return 'PHYSICS'; if (/CHEM|ХИМ/.test(x)) return 'CHEMISTRY'; return x; }
  function msg(e) { return ERR[e.message] || (e.field ? 'Проверьте поле: ' + e.field : e.message) || 'Не получилось. Попробуйте ещё раз.'; }
  function api(p, o) { return C.api(p, o).catch(function (e) { if (e.status === 401) { location.replace(T); } throw e; }); }
  function dt(s) { if (!s) return ''; var d = new Date(String(s).replace(' ', 'T')); if (isNaN(d)) return String(s); return d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'long' }) + ', ' + C.hhmm(s); }
  function gl(s) { return [C.subjectLabel(s.subject || s.main_subject), C.subjectLabel(s.study_goal)].filter(Boolean).join(' · '); }
  function errBox(t) { var p = E('p', 'stu-err', t); p.setAttribute('role', 'alert'); return p; }
  function line(a, b) { var d = E('div', 'stu-line'); d.append(E('span', '', a)); if (b != null) { if (typeof b === 'string') d.append(E('span', 'stu-meta', b)); else d.append(b); } return d; }

  /* ---------- список ---------- */
  function loadAll() {
    return Promise.all([
      api('/teacher/crm/students?limit=500'),
      api('/teacher/groups').catch(function (e) { lastErr = e; return { items: [] }; }),
      api('/teacher/group-lessons').catch(function () { return { items: [] }; })
    ]).then(function (a) { students = a[0].items || []; groups = a[1].items || []; glessons = a[2].items || []; });
  }
  function match(txt) { return !st.q || String(txt).toLowerCase().indexOf(st.q.toLowerCase()) >= 0; }
  function subjOk(s) { return st.subj === 'ALL' || subjKey(s) === st.subj; }

  function drawList() {
    var out = document.createDocumentFragment(), n = 0;
    if (st.tab === 'students') {
      students.filter(function (s) { return match([s.name, s.telegram_username, s.phone, s.main_subject, s.study_goal].join(' ')) && subjOk(s.main_subject); }).forEach(function (s) {
        n++; var b = E('button', 'stu-row'); b.type = 'button'; b.append(E('span', 'stu-name', s.name || 'Ученик'));
        var m = E('span', 'stu-meta');
        if (s.grade) m.append(E('span', '', s.grade + ' класс'));
        var g = gl(s); if (g) m.append(E('span', '', g));
        m.append(E('span', '', s.next_lesson ? 'Ближайший: ' + dt(s.next_lesson) : 'Ближайшего урока нет'));
        if (Number(s.payment_waiting) > 0) m.append(E('span', 'c-pay due', 'Ждём ' + Number(s.payment_waiting).toLocaleString('ru-RU') + ' ₽'));
        b.append(m); b.addEventListener('click', function () { openStudent(s.id); }); out.appendChild(b);
      });
      if (!n) out.appendChild(C.empty(students.length ? 'Никого не нашли. Измените поиск или фильтры.' : 'Учеников пока нет.'));
    } else {
      groups.filter(function (g) { return match(g.name) && subjOk(g.subject); }).forEach(function (g) {
        n++; var b = E('button', 'stu-row'); b.type = 'button'; b.append(E('span', 'stu-name', g.name || 'Группа'));
        var m = E('span', 'stu-meta'); var x = gl(g); if (x) m.append(E('span', '', x));
        m.append(E('span', '', 'Участники: ' + (g.member_count || 0) + (g.max_members ? '/' + g.max_members : '')));
        if (g.next_lesson) m.append(E('span', '', 'Ближайшее: ' + dt(g.next_lesson)));
        b.append(m); b.addEventListener('click', function () { openGroup(g.id); }); out.appendChild(b);
      });
      if (!n) out.appendChild(C.empty(groups.length ? 'Ничего не нашли. Измените поиск или фильтры.' : (lastErr ? msg(lastErr) : 'Групп пока нет.')));
    }
    listEl.replaceChildren(out);
  }

  function drawMain() {
    var f = document.createDocumentFragment();
    var tabs = E('div', 'stu-tabs'); tabs.setAttribute('role', 'tablist');
    [['students', 'Ученики'], ['groups', 'Группы']].forEach(function (t) {
      var b = E('button', 'stu-tab', t[1]); b.type = 'button'; b.setAttribute('role', 'tab'); b.setAttribute('aria-selected', String(st.tab === t[0]));
      b.addEventListener('click', function () { st.tab = t[0]; st.fmt = t[0] === 'students' ? 'IND' : 'GRP'; drawMain(); }); tabs.appendChild(b);
    });
    var fl = E('div', 'stu-filters');
    var q = document.createElement('input'); q.type = 'search'; q.placeholder = 'Поиск по имени, предмету…'; q.value = st.q; q.setAttribute('aria-label', 'Поиск');
    q.addEventListener('input', function () { st.q = q.value; drawList(); });
    var fm = document.createElement('select'); fm.setAttribute('aria-label', 'Формат');
    [['ALL', 'Все форматы'], ['IND', 'Индивидуально'], ['GRP', 'Группы']].forEach(function (o) { var x = document.createElement('option'); x.value = o[0]; x.textContent = o[1]; if (st.fmt === o[0]) x.selected = true; fm.appendChild(x); });
    fm.addEventListener('change', function () { st.fmt = fm.value; if (fm.value === 'IND') st.tab = 'students'; if (fm.value === 'GRP') st.tab = 'groups'; drawMain(); });
    var sj = document.createElement('select'); sj.setAttribute('aria-label', 'Предмет');
    [['ALL', 'Все предметы'], ['PHYSICS', 'Физика'], ['CHEMISTRY', 'Химия']].forEach(function (o) { var x = document.createElement('option'); x.value = o[0]; x.textContent = o[1]; if (st.subj === o[0]) x.selected = true; sj.appendChild(x); });
    sj.addEventListener('change', function () { st.subj = sj.value; drawList(); });
    fl.append(q, fm, sj); listEl = E('div'); listEl.setAttribute('aria-live', 'polite');
    f.append(tabs, fl, listEl); host.replaceChildren(f); drawList();
  }

  function back(fn) { var b = C.button('← К списку', 'text', fn); b.classList.add('stu-back'); return b; }
  function showList() { host.replaceChildren(); drawMain(); }
  function busyView() { host.replaceChildren(E('div', 'c-skel'), E('div', 'c-skel')); }

  /* ---------- карточка ученика ---------- */
  var FIELDS = [['grade', 'Класс', 'number'], ['study_goal', 'Цель обучения'], ['main_subject', 'Основной предмет'], ['phone', 'Телефон'], ['parent_name', 'Родитель'], ['parent_phone', 'Телефон родителя']];
  function openStudent(id) {
    busyView();
    api('/teacher/crm/student?id=' + encodeURIComponent(id)).then(function (d) {
      var s = d.student || {}, stt = d.stats || {}, v = document.createDocumentFragment();
      v.appendChild(back(showList)); v.appendChild(E('h2', 'cab-title', s.name || 'Ученик'));
      var sub = [s.grade ? s.grade + ' класс' : '', gl(s)].filter(Boolean).join(' · '); if (sub) v.appendChild(E('p', 'cab-sub', sub));
      var acts = E('div', 'c-actions');
      acts.append(C.button('Записать на урок', 'primary', function () { window.__schAfterCreate = function () { openStudent(id); }; window.CabSchedule.create({ user_id: id }); }));
      acts.append(C.button('Написать', 'secondary', '/app/cabinet/messages.html?student=' + encodeURIComponent(id)));
      if (s.board_url) { var bd = C.button('Доска', 'secondary', s.board_url); bd.target = '_blank'; bd.rel = 'noopener'; acts.append(bd); }
      v.appendChild(acts);
      var grid = E('div', 'stu-grid'), left = E('div'), right = E('div');
      var sec = C.section('01', 'Профиль'), f = E('form', 'stu-form'), inputs = {};
      FIELDS.forEach(function (x) { var l = E('label', '', x[1]), i = document.createElement('input'); i.name = x[0]; i.type = x[2] || 'text'; i.value = s[x[0]] == null ? '' : s[x[0]]; inputs[x[0]] = i; l.appendChild(i); f.appendChild(l); });
      var out = E('div'); out.setAttribute('aria-live', 'polite'); var sv = C.button('Сохранить', 'primary'); sv.type = 'submit'; f.append(out, sv);
      f.addEventListener('submit', function (e) {
        e.preventDefault(); out.replaceChildren(); sv.disabled = true; var fields = {};
        FIELDS.forEach(function (x) { fields[x[0]] = inputs[x[0]].value; });
        api('/teacher/crm/student/update', { method: 'POST', body: { user_id: Number(id), fields: fields } }).then(function () { C.toast('Сохранено.'); sv.disabled = false; loadAll(); }, function (er) { sv.disabled = false; out.replaceChildren(errBox(msg(er))); });
      });
      sec.appendChild(f); left.appendChild(sec);
      var s2 = C.section('02', 'Сейчас');
      s2.append(line('Занятий завершено', String(stt.lessons_completed || 0)), line('Активных ДЗ', String(stt.homework_open || 0)), line('Ждут проверки', String(stt.submissions_waiting || 0)), line('Ожидает оплаты', Number(stt.payment_waiting || 0).toLocaleString('ru-RU') + ' ₽'));
      right.appendChild(s2);
      var s3 = C.section('03', 'Ближайшее занятие');
      s3.appendChild(d.next_lesson ? line(dt(d.next_lesson.start_time), [C.subjectLabel(d.next_lesson.subject), d.next_lesson.lesson_status].filter(Boolean).join(' · ')) : C.empty('Ближайших занятий нет.'));
      right.appendChild(s3);
      var s4 = C.section('04', 'Прошедшие занятия');
      (d.recent_lessons || []).forEach(function (x) { s4.appendChild(line(dt(x.start_time), [C.subjectLabel(x.subject), x.lesson_status].filter(Boolean).join(' · '))); });
      if (!(d.recent_lessons || []).length) s4.appendChild(C.empty('Занятий пока нет.'));
      right.appendChild(s4);
      grid.append(left, right); v.appendChild(grid); host.replaceChildren(v);
    }, function (e) { host.replaceChildren(back(showList), C.error(msg(e), function () { openStudent(id); })); });
  }

  /* ---------- карточка группы ---------- */
  function openGroup(id) {
    busyView();
    api('/teacher/group/settings?id=' + encodeURIComponent(id)).then(function (d) {
      var g = d.group || {}, v = document.createDocumentFragment(), members = g.members || [], slots = g.slots || [];
      v.appendChild(back(showList)); v.appendChild(E('h2', 'cab-title', g.name || 'Группа'));
      v.appendChild(E('p', 'cab-sub', [gl(g), 'Участники: ' + members.length + (g.max_members ? '/' + g.max_members : '')].filter(Boolean).join(' · ')));
      var grid = E('div', 'stu-grid'), left = E('div'), right = E('div');
      var s1 = C.section('01', 'Участники');
      members.forEach(function (m) { s1.appendChild(line(m.name || 'Ученик', m.status === 'PAUSED' ? 'Пауза' : '')); });
      if (!members.length) s1.appendChild(C.empty('Участников пока нет.'));
      left.appendChild(s1);
      var s2 = C.section('02', 'Расписание');
      slots.forEach(function (s) { s2.appendChild(line(DAYS[s.weekday] || '', String(s.start_time || '').slice(0, 5))); });
      if (!slots.length) s2.appendChild(C.empty('Постоянного времени нет.'));
      s2.appendChild(C.button('Добавить занятие', 'secondary', function () {
        window.CabSchedule.createGroup({ id: id, name: g.name }, function () {
          return loadAll().then(function () { openGroup(id); }, function () { openGroup(id); });
        });
      }));
      left.appendChild(s2);
      var s3 = C.section('03', 'Ссылка-приглашение'), url = d.invite_path ? new URL(d.invite_path, location.origin).href : '';
      var inp = document.createElement('input'); inp.className = 'stu-invite'; inp.readOnly = true; inp.value = url; inp.setAttribute('aria-label', 'Ссылка-приглашение');
      var ia = E('div', 'c-actions'), iout = E('div'); iout.setAttribute('aria-live', 'polite');
      ia.append(C.button('Скопировать', 'secondary', function () {
        var ok = function () { C.toast('Ссылка скопирована.'); };
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(inp.value).then(ok, function () { inp.select(); iout.replaceChildren(errBox('Скопируйте ссылку вручную.')); });
        else { inp.select(); iout.replaceChildren(errBox('Скопируйте ссылку вручную.')); }
      }));
      ia.append(C.button('Заменить ссылку', 'secondary', function () {
        C.modal({ title: 'Заменить приглашение?', body: 'Старые ссылки перестанут работать, участники останутся в группе.', actions: [{ text: 'Отмена', kind: 'secondary' }, { text: 'Заменить', kind: 'primary', onClick: function () {
          api('/teacher/group/invite', { method: 'POST', body: { group_id: Number(id), rotate: true } }).then(function (r) { inp.value = new URL(r.invite_path, location.origin).href; C.toast('Новая ссылка готова.'); }, function (e) { iout.replaceChildren(errBox(msg(e))); });
        } }] });
      }));
      s3.append(inp, ia, iout); left.appendChild(s3);
      var s4 = C.section('04', 'Ближайшие занятия'), mine = glessons.filter(function (x) { return x.group_id != null ? String(x.group_id) === String(id) : x.group_name === g.name; });
      var now = new Date().toISOString().slice(0, 10);
      mine = mine.filter(function (x) { return String(x.start_time).slice(0, 10) >= now; }).sort(function (a, b) { return String(a.start_time).localeCompare(String(b.start_time)); });
      mine.forEach(function (x) { var b = E('button', 'stu-row'); b.type = 'button'; b.append(E('span', 'stu-name', dt(x.start_time)), E('span', 'stu-meta', 'Были: ' + (x.attended || 0) + ' из ' + (x.participants || 0))); b.addEventListener('click', function () { openLesson(x.id, id); }); s4.appendChild(b); });
      if (!mine.length) s4.appendChild(C.empty('Ближайших групповых занятий нет.'));
      right.appendChild(s4);
      grid.append(left, right); v.appendChild(grid); host.replaceChildren(v);
    }, function (e) { host.replaceChildren(back(showList), C.error(msg(e), function () { openGroup(id); })); });
  }

  function openLesson(lid, gid) {
    busyView();
    api('/teacher/group-lesson?id=' + encodeURIComponent(lid)).then(function (d) {
      var l = d.lesson || {}, v = document.createDocumentFragment(), out = E('div'); out.setAttribute('aria-live', 'polite');
      v.appendChild(back(function () { openGroup(gid); })); v.appendChild(E('h2', 'cab-title', dt(l.start_time)));
      v.appendChild(E('p', 'cab-sub', [l.group_name, gl(l)].filter(Boolean).join(' · ')));
      var sec = C.section('01', 'Участники занятия');
      (d.participants || []).forEach(function (p) {
        var a = p.attendance || {}, ps = C.payStatus(p.payment_status), status = a.present ? 'Здесь' : (a.first_joined_at ? 'Выходил' : 'Не пришёл');
        var b = C.button(a.present ? 'Ушёл' : (a.first_joined_at ? 'Вернулся' : 'Пришёл'), 'secondary', function () {
          b.disabled = true; out.replaceChildren();
          api('/teacher/group/attendance', { method: 'POST', body: { lesson_id: Number(lid), user_id: Number(p.user_id), event_type: a.present ? 'LEAVE' : 'JOIN', happened_at: null } }).then(function () { openLesson(lid, gid); }, function (e) { b.disabled = false; out.replaceChildren(errBox(msg(e))); });
        });
        var info = E('span', '', (p.name || 'Ученик') + ' — ' + status + (ps ? ' · ' + ps.text : (p.payment_status ? '' : '')));
        sec.appendChild(line('', b)); sec.lastChild.replaceChild(info, sec.lastChild.firstChild);
      });
      if (!(d.participants || []).length) sec.appendChild(C.empty('Участников нет.'));
      v.append(out, sec); host.replaceChildren(v);
    }, function (e) { host.replaceChildren(back(function () { openGroup(gid); }), C.error(msg(e), function () { openLesson(lid, gid); })); });
  }

  C.boot({
    role: 'teacher', menu: C.TEACHER_MENU, active: 'students',
    render: function (main) {
      main.appendChild(E('h1', 'cab-title', 'Ученики и группы'));
      host = E('div'); main.appendChild(host); document.title = 'Ученики и группы — Аделия'; busyView();
      var params = new URLSearchParams(location.search), group = Number(params.get('group')), lesson = Number(params.get('lesson'));
      return loadAll().then(function () {
        if (Number.isSafeInteger(group) && group > 0 && groups.some(function (g) { return Number(g.id) === group; })) {
          if (Number.isSafeInteger(lesson) && lesson > 0 && glessons.some(function (l) { return Number(l.id) === lesson && Number(l.group_id) === group; })) {
            openLesson(lesson, group);
          } else openGroup(group);
        } else drawMain();
      }, function (e) { host.replaceChildren(C.error(msg(e), function () { location.reload(); })); });
    }
  });
})();
