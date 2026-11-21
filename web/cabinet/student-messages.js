/* Ученик: «Сообщения». API как в старом чате: GET /student/messages?limit=200 ({items:[{direction:'IN'=ты, text,
   created_at, read_at, status, attachment}]}), POST /student/message-media/upload (FormData file → {attachment}),
   POST /student/message {text, attachment} */
(function () {
  'use strict';
  var A = '/app/', hist, form, ta, fileInp, fname, state, sig = '', busy = false, polling = false;
  function atts(a) { return !a ? [] : Array.isArray(a) ? a : Array.isArray(a.items) ? a.items : [a]; }
  function stamp(iso) { var d = S.date(iso), t = C.hhmm(iso); return (d ? d + ', ' : '') + t; }
  function signature(it) { var l = it[it.length - 1] || {}; return it.length + ':' + (l.id || '') + ':' + (l.read_at || '') + ':' + (l.status || ''); }

  function bubble(x) {
    var mine = x.direction === 'IN', b = C.el('article', 'st-msg' + (mine ? ' mine' : ''));
    var m = C.el('div', 'st-msg-meta'); m.append(C.el('b', '', mine ? 'Ты' : 'Преподаватель'), C.el('span', '', stamp(x.created_at))); b.appendChild(m);
    if (x.text) b.appendChild(C.el('div', 'st-msg-text', x.text));
    atts(x.attachment).forEach(function (a) {
      var u = S.safeUrl(a.url); if (!u) return;
      var l = C.el('a', 'st-msg-file'); l.href = u; l.target = '_blank'; l.rel = 'noopener';
      if (String(a.kind || '').toLowerCase() === 'photo') { var im = document.createElement('img'); im.src = u; im.alt = a.name || 'Вложение'; im.loading = 'lazy'; l.appendChild(im); } else l.textContent = 'Файл: ' + (a.name || 'вложение');
      b.appendChild(l);
    });
    if (mine) { var st = x.read_at ? 'Прочитано' : String(x.status || '').toLowerCase() === 'failed' ? 'Не отправлено' : String(x.status || '').toLowerCase() === 'delivered' ? 'Доставлено' : 'Отправлено'; b.appendChild(C.el('div', 'st-msg-st', st)); }
    return b;
  }

  function draw(items, force) {
    var stick = hist.scrollHeight - hist.scrollTop - hist.clientHeight < 90;
    if (!items.length) hist.replaceChildren(C.empty('Начни диалог: спроси о занятии, ДЗ или расписании.'));
    else hist.replaceChildren.apply(hist, items.map(bubble));
    if (stick || force) hist.scrollTop = hist.scrollHeight;
  }

  function refresh(force) {
    if (polling || document.hidden) return Promise.resolve(); polling = true;
    return C.api('/student/messages?limit=200').then(function (d) {
      var it = (d && d.items) || [], n = signature(it); if (force || n !== sig) { draw(it, force); sig = n; }
      C.setBell(0); if (state.dataset.net) { state.textContent = ''; delete state.dataset.net; }
    }, function (e) {
      if (e.status === 401) { location.replace(A); return; }
      if (!sig && !hist.querySelector('.st-msg')) hist.replaceChildren(C.error(e.message, function () { refresh(true); }));
      else if (!busy) { state.textContent = 'Нет соединения. Показана прежняя переписка.'; state.dataset.net = '1'; }
    }).then(function () { polling = false; });
  }

  function upload(f) {
    var fd = new FormData(); fd.append('file', f);
    return fetch('/api/student/message-media/upload', { method: 'POST', credentials: 'same-origin', body: fd }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { if (!r.ok) throw new Error(d.error || 'Не удалось загрузить файл'); return d.attachment; });
    });
  }

  function send(ev) {
    ev.preventDefault(); if (busy) return;
    var f = fileInp.files && fileInp.files[0], text = ta.value.trim(); if (!text && !f) return;
    if (f && f.size > 15 * 1024 * 1024) { state.textContent = 'Файл больше 15 МБ.'; return; }
    busy = true; ta.disabled = true; form.querySelector('button[type=submit]').disabled = true; state.textContent = f ? 'Загружаю файл…' : 'Отправляю…';
    (f ? upload(f) : Promise.resolve(null)).then(function (att) { return C.api('/student/message', { method: 'POST', body: { text: text, attachment: att } }); }).then(function () {
      ta.value = ''; fileInp.value = ''; fname.textContent = ''; state.textContent = 'Отправлено'; return refresh(true);
    }, function (e) { state.textContent = 'Не получилось отправить: ' + (e.message || 'ошибка') + '. Текст сохранён, попробуй ещё раз.'; }).then(function () {
      busy = false; ta.disabled = false; form.querySelector('button[type=submit]').disabled = false;
    });
  }

  C.boot({
    role: 'student', menu: C.STUDENT_MENU, active: 'messages',
    render: function (main) {
      document.title = 'Сообщения — Аделия'; main.classList.add('st-chat-main');
      main.append(C.el('h1', 'cab-title', 'Сообщения'), C.el('p', 'cab-sub', 'Переписка с преподавателем'));
      hist = C.el('div', 'st-hist'); hist.setAttribute('role', 'log'); hist.setAttribute('aria-label', 'История сообщений'); hist.setAttribute('aria-live', 'polite'); hist.appendChild(C.el('div', 'c-skel'));
      form = C.el('form', 'st-compose'); form.addEventListener('submit', send);
      ta = document.createElement('textarea'); ta.rows = 2; ta.maxLength = 4000; ta.placeholder = 'Сообщение преподавателю…'; ta.setAttribute('aria-label', 'Сообщение преподавателю');
      ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) form.requestSubmit(); });
      fileInp = document.createElement('input'); fileInp.type = 'file'; fileInp.accept = 'image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt'; fileInp.hidden = true;
      fname = C.el('span', 'c-row-s'); fileInp.addEventListener('change', function () { fname.textContent = fileInp.files[0] ? fileInp.files[0].name : ''; });
      var att = C.button('Прикрепить файл', 'secondary', function () { fileInp.click(); });
      var go = C.el('button', 'c-btn primary', 'Отправить'); go.type = 'submit';
      var row = C.el('div', 'c-actions'); row.append(att, fname, go);
      state = C.el('p', 'c-row-s st-state'); state.setAttribute('aria-live', 'polite');
      form.append(ta, fileInp, row, state); main.append(hist, form);
      document.addEventListener('visibilitychange', function () { if (!document.hidden) refresh(); });
      setInterval(refresh, 15000); return refresh(true);
    }
  });
})();
