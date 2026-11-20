/* Кабинет «Журнал»: Сообщения преподавателя. Эндпоинты: teacher/messages, history, read, send, upload. */
(function () {
  'use strict';
  var el = function (t, c, x) { return C.el(t, c, x); };
  var st = { items: [], active: null, hist: [], drafts: {}, file: null, sending: false, q: '', unreadOnly: false };
  var shell, listBox, threadBox, histBox, ta, fileName, stateEl, timer, polling = false;

  function when(s) { var m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/); if (!m) return ''; var d = new Date(); var same = Number(m[3]) === d.getDate() && Number(m[2]) === d.getMonth() + 1; return same ? m[4] + ':' + m[5] : m[3] + '.' + m[2] + ' ' + m[4] + ':' + m[5]; }
  function err(e) { var m = e && e.message || ''; return /^[a-z_]+$/.test(m) ? 'Не получилось. Повторите ещё раз.' : m || 'Не получилось. Повторите ещё раз.'; }
  function isParent(x) { return x && x.participant_type === 'PARENT'; }
  function jsonBody(o) { return o; }

  /* ---- список ---- */
  function paintList() {
    var q = st.q.trim().toLowerCase(), unread = st.items.reduce(function (n, x) { return n + (Number(x.unread) || 0); }, 0);
    var rows = st.items.filter(function (x) { return (!st.unreadOnly || Number(x.unread) > 0) && (!q || [x.name, x.student_name, x.last_body].join(' ').toLowerCase().indexOf(q) >= 0); });
    var f = document.createDocumentFragment();
    var fb = el('div', 'msg-filter');
    [[false, 'Все'], [true, 'Непрочитанные' + (unread ? ' · ' + unread : '')]].forEach(function (p) {
      var b = el('button', 'msg-fbtn', p[1]); b.type = 'button'; b.setAttribute('aria-pressed', String(st.unreadOnly === p[0]));
      b.addEventListener('click', function () { st.unreadOnly = p[0]; paintList(); }); fb.appendChild(b);
    });
    f.appendChild(fb);
    var inp = el('input', 'msg-search'); inp.type = 'search'; inp.placeholder = 'Поиск по имени и сообщениям'; inp.setAttribute('aria-label', 'Поиск'); inp.value = st.q;
    inp.addEventListener('input', function () { st.q = inp.value; var keep = inp.selectionStart; paintList(); var n = listBox.querySelector('.msg-search'); n.focus(); n.setSelectionRange(keep, keep); });
    f.appendChild(inp);
    if (!rows.length) f.appendChild(C.empty(st.items.length ? 'Ничего не найдено.' : 'Диалогов пока нет. Они появятся, когда напишет ученик.'));
    rows.forEach(function (x) {
      var b = el('button', 'msg-conv'); b.type = 'button'; if (st.active && st.active.id === x.id) b.setAttribute('aria-current', 'true');
      var main = el('span', 'msg-conv-main');
      main.appendChild(el('span', 'msg-conv-name', x.name || 'Без имени'));
      main.appendChild(el('span', 'msg-conv-last', (isParent(x) ? 'Родитель' + (x.student_name ? ' · ' + x.student_name : '') + ' · ' : '') + String(x.last_body || 'Нет сообщений').slice(0, 70)));
      b.appendChild(main);
      var side = el('span', 'msg-conv-side'); side.appendChild(el('span', 'msg-time', when(x.last_at || x.updated_at)));
      if (Number(x.unread) > 0) { var u = el('span', 'msg-badge', String(x.unread)); u.setAttribute('aria-label', 'Непрочитанных: ' + x.unread); side.appendChild(u); }
      b.appendChild(side); b.addEventListener('click', function () { openConv(x.id); }); f.appendChild(b);
    });
    listBox.replaceChildren(f);
    C.setBell(unread);
  }

  /* ---- диалог ---- */
  function bubble(m) {
    var b = el('article', 'msg-b ' + (m.direction === 'OUT' ? 'out' : 'in'));
    if (m.body) b.appendChild(el('div', 'msg-text', m.body));
    var at = m.attachment; (Array.isArray(at) ? at : at && Array.isArray(at.items) ? at.items : at ? [at] : []).forEach(function (a) {
      if (!a || !/^\/api\//.test(String(a.url || ''))) return;
      var l = el('a', 'msg-att', String(a.kind || '').toLowerCase() === 'photo' ? 'Фото: ' + (a.name || 'открыть') : 'Файл: ' + (a.name || 'открыть')); l.href = a.url; l.target = '_blank'; l.rel = 'noopener'; b.appendChild(l);
    });
    b.appendChild(el('small', 'msg-b-t', when(m.created_at) + (m.direction === 'OUT' && m.read_at ? ' · прочитано' : '')));
    if (m.direction === 'OUT' && !isParent(st.active)) b.appendChild(statusLine(m));
    return b;
  }
  var CH = { TELEGRAM: 'Telegram', VK: 'VK' };
  var DST = { SENT: '✓', DELIVERED: '✓', READ: '✓ прочитано', QUEUED: 'в очереди', FAILED: 'не доставлено', SKIPPED: 'не привязан' };
  function statusLine(m) {
    var line = el('div', 'msg-status'), ext = (m.deliveries || []).filter(function (d) { return CH[String(d.channel).toUpperCase()]; }), bad = [];
    line.appendChild(el('span', '', 'Аделия ✓'));
    ext.forEach(function (d) {
      var c = String(d.channel).toUpperCase(), k = String(d.status).toUpperCase(); if (k === 'FAILED') bad.push(c);
      line.appendChild(el('span', 'msg-st' + (k === 'FAILED' ? ' bad' : ''), ' · ' + CH[c] + ' ' + (DST[k] || k)));
    });
    if (bad.length) { var r = el('button', 'msg-retry', 'Повторить'); r.type = 'button'; r.addEventListener('click', function () { r.disabled = true; sendExternal(m.id, bad); }); line.appendChild(r); }
    return line;
  }
  /* каналы диалога: доступность берётся из conversation.channels (telegram/vk привязаны) */
  function avail(x, c) { return !x.channels || !!x.channels[c.toLowerCase()]; }
  function chKey(x) { return 'adelia:msgch:' + x.id; }
  function chLoad(x) { var v = []; try { v = JSON.parse(localStorage.getItem(chKey(x)) || '[]'); } catch (e) {} return (Array.isArray(v) ? v : []).filter(function (c) { return CH[c] && avail(x, c); }); }
  function chSave(x, list) { try { localStorage.setItem(chKey(x), JSON.stringify(list)); } catch (e) {} }
  function rawExternal(id, channels) {
    return fetch('/api/teacher/messages/send-external', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message_id: Number(id), channels: channels }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, j: j }; }); }, function () { throw new Error('Нет связи с сервером.'); });
  }
  function extReport(res, channels) {
    var d = (res.j && res.j.deliveries) || {}, bad = channels.filter(function (c) { var x = d[c.toLowerCase()]; return !x || ['SENT', 'DELIVERED', 'READ'].indexOf(String(x.status).toUpperCase()) < 0; });
    if (!res.ok && !res.j.deliveries) return 'В Аделии сохранено, но внешний канал не ответил. Можно повторить.';
    return bad.length ? 'В Аделии сохранено. Не доставлено: ' + bad.map(function (c) { return CH[c]; }).join(', ') + '. Можно повторить.' : 'Отправлено: Аделия, ' + channels.map(function (c) { return CH[c]; }).join(', ');
  }
  function sendExternal(id, channels) {
    var x = st.active; if (!x) return Promise.resolve();
    return rawExternal(id, channels).then(function (res) { if (stateEl) stateEl.textContent = extReport(res, channels); }, function (e) { if (stateEl) stateEl.textContent = 'Не удалось повторить: ' + err(e); })
      .then(function () { return loadHist(x.id); }).then(function (h) { if (st.active && st.active.id === x.id) { st.hist = h; paintHist(false); } });
  }
  function paintHist(stick) {
    var near = !histBox || histBox.scrollHeight - histBox.scrollTop - histBox.clientHeight < 90;
    histBox.replaceChildren.apply(histBox, st.hist.length ? st.hist.map(bubble) : [C.empty('Сообщений пока нет. Можно написать первым.')]);
    if (stick || near) histBox.scrollTop = histBox.scrollHeight;
  }
  function buildThread() {
    var x = st.active; threadBox.replaceChildren();
    if (!x) { threadBox.appendChild(C.empty('Выберите диалог слева.')); return; }
    var head = el('div', 'msg-head'), back = el('button', 'msg-back', '←'); back.type = 'button'; back.setAttribute('aria-label', 'К списку диалогов');
    back.addEventListener('click', function () { saveDraft(); st.active = null; shell.classList.remove('has-active'); buildThread(); paintList(); });
    var t = el('div'); t.appendChild(el('b', 'msg-head-n', x.name || '')); t.appendChild(el('small', '', isParent(x) ? 'Родитель' + (x.student_name ? ' · ' + x.student_name : '') : 'Ученик'));
    head.append(back, t); threadBox.appendChild(head);
    histBox = el('div', 'msg-hist'); histBox.setAttribute('role', 'log'); histBox.setAttribute('aria-live', 'polite'); histBox.tabIndex = 0;
    histBox.addEventListener('scroll', ack, { passive: true }); threadBox.appendChild(histBox);
    var form = el('form', 'msg-form'); ta = el('textarea', 'msg-ta'); ta.maxLength = 4000; ta.rows = 2; ta.setAttribute('aria-label', 'Текст сообщения'); ta.placeholder = 'Сообщение';
    ta.value = (st.drafts[x.id] || {}).text || '';
    ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
    var row = el('div', 'msg-form-row'), pick = el('label', 'c-btn msg-pick', 'Прикрепить'), fi = el('input'); fi.type = 'file'; fi.hidden = true; fi.accept = 'image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt';
    fileName = el('span', 'msg-fname'); st.file = (st.drafts[x.id] || {}).file || null; fileName.textContent = st.file ? st.file.name : '';
    fi.addEventListener('change', function () { st.file = fi.files[0] || null; fileName.textContent = st.file ? st.file.name : ''; });
    pick.appendChild(fi);
    var chs = el('div', 'msg-chs'); chs.setAttribute('role', 'group'); chs.setAttribute('aria-label', 'Куда отправить');
    var a0 = el('label', 'msg-ch on fixed'), ai = el('input'); ai.type = 'checkbox'; ai.checked = true; ai.disabled = true; a0.append(ai, document.createTextNode(' Аделия')); chs.appendChild(a0);
    var sel = chLoad(x); st.sel = sel;
    if (isParent(x)) chs.appendChild(el('span', 'msg-ch-note', 'Родителю — только в Аделии'));
    else ['TELEGRAM', 'VK'].forEach(function (c) {
      var ok = avail(x, c), l = el('label', 'msg-ch' + (ok ? '' : ' off')), i = el('input'); i.type = 'checkbox'; i.checked = ok && sel.indexOf(c) >= 0; i.disabled = !ok;
      if (!ok) l.title = CH[c] + ' не привязан';
      i.addEventListener('change', function () { st.sel = st.sel.filter(function (k) { return k !== c; }); if (i.checked) st.sel.push(c); chSave(x, st.sel); });
      l.append(i, document.createTextNode(' ' + CH[c] + (ok ? '' : ' — не привязан'))); chs.appendChild(l);
    });
    var sb = el('button', 'c-btn primary', 'Отправить'); sb.type = 'submit';
    row.append(pick, fileName, sb); stateEl = el('div', 'msg-state'); stateEl.setAttribute('aria-live', 'polite');
    form.append(ta, chs, row, stateEl); form.addEventListener('submit', function (e) { e.preventDefault(); send(); });
    threadBox.appendChild(form); paintHist(true);
  }
  function saveDraft() { if (st.active && ta) st.drafts[st.active.id] = { text: ta.value, file: st.file }; }

  function loadHist(id) { return C.api('/teacher/messages/history?conversation_id=' + encodeURIComponent(id) + '&limit=200').then(function (d) { return d.items || []; }); }
  function openConv(id) {
    saveDraft(); var x = st.items.filter(function (i) { return i.id === id; })[0]; if (!x) return;
    st.active = x; st.hist = []; shell.classList.add('has-active'); buildThread(); paintList();
    loadHist(id).then(function (h) { if (!st.active || st.active.id !== id) return; st.hist = h; paintHist(true); ack(); },
      function (e) { if (stateEl) stateEl.textContent = 'Не удалось открыть диалог: ' + err(e); });
  }
  var readBusy = false;
  function ack() {
    if (readBusy || !st.active || document.hidden || !histBox) return;
    if (histBox.scrollHeight - histBox.scrollTop - histBox.clientHeight > 90) return;
    var un = st.hist.filter(function (m) { return m.direction === 'IN' && !m.read_at; }); if (!un.length) return;
    var cid = st.active.id, through = Math.max.apply(null, st.hist.map(function (m) { return Number(m.id) || 0; })); readBusy = true;
    C.api('/teacher/messages/read', { method: 'POST', body: { conversation_id: cid, through_id: through } }).then(function (r) {
      st.hist.forEach(function (m) { if (m.direction === 'IN' && !m.read_at && Number(m.id) <= through) m.read_at = (r && r.read_at) || 'read'; });
      var a = st.items.filter(function (i) { return i.id === cid; })[0]; if (a) a.unread = 0; paintList();
    }, function () { if (stateEl) stateEl.textContent = 'Не удалось отметить прочитанным. Повторим при обновлении.'; }).then(function () { readBusy = false; });
  }

  function upload(file) {
    var x = st.active, fd = new FormData(); fd.append(isParent(x) ? 'conversation_id' : 'user_id', String(isParent(x) ? x.id : x.student_id)); fd.append('file', file);
    return fetch('/api/teacher/messages/upload', { method: 'POST', credentials: 'same-origin', body: fd }).then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.error && !/^[a-z_]+$/.test(j.error) ? j.error : 'Не удалось загрузить файл.'); return j.attachment; }); });
  }
  function send() {
    var x = st.active, text = ta.value.trim(), file = st.file; if (!x || st.sending || (!text && !file)) return;
    st.sending = true; var btns = threadBox.querySelectorAll('button[type=submit]'); [].forEach.call(btns, function (b) { b.disabled = true; }); stateEl.textContent = file ? 'Загружаю вложение…' : 'Отправляю…';
    Promise.resolve(file ? upload(file) : null).then(function (att) {
      var body = isParent(x) ? { conversation_id: x.id, text: text, attachment: att } : { user_id: x.student_id, text: text, attachment: att };
      return C.api('/teacher/messages/send', { method: 'POST', body: jsonBody(body) });
    }).then(function (created) {
      delete st.drafts[x.id]; ta.value = ''; st.file = null; fileName.textContent = ''; stateEl.textContent = 'Отправлено';
      var ext = isParent(x) ? [] : (st.sel || []).filter(function (c) { return avail(x, c); });
      if (!ext.length || !created || created.message_id == null) return;
      stateEl.textContent = 'Отправляю: ' + ext.map(function (c) { return CH[c]; }).join(', ') + '…';
      return rawExternal(created.message_id, ext).then(function (res) { stateEl.textContent = extReport(res, ext); }, function (e) { stateEl.textContent = 'В Аделии сохранено, но внешний канал не ответил: ' + err(e); });
    }).then(function () {
      return loadHist(x.id).then(function (h) { if (st.active && st.active.id === x.id) { st.hist = h; paintHist(true); } }).then(refreshList);
    }, function (e) { stateEl.textContent = 'Не удалось отправить: ' + err(e); }).then(function () { st.sending = false; [].forEach.call(btns, function (b) { b.disabled = false; }); });
  }

  function refreshList() {
    return C.api('/teacher/messages?limit=200').then(function (d) {
      st.items = d.items || []; if (st.active) st.active = st.items.filter(function (i) { return i.id === st.active.id; })[0] || st.active; paintList();
    });
  }
  function poll() {
    if (polling || document.hidden || st.sending) return; polling = true;
    var cid = st.active && st.active.id;
    refreshList().then(function () { return cid ? loadHist(cid) : null; }).then(function (h) {
      if (h && st.active && st.active.id === cid && !st.sending && JSON.stringify(h) !== JSON.stringify(st.hist)) { st.hist = h; paintHist(false); }
      if (h) ack();
    }).catch(function (e) { if (e && e.status === 401) location.replace('/app/teacher.html'); }).then(function () { polling = false; });
  }

  C.boot({
    role: 'teacher', menu: C.TEACHER_MENU, active: 'messages',
    render: function (main) {
      main.classList.add('msg-main'); main.append(el('h1', 'cab-title', 'Сообщения'));
      shell = el('div', 'msg-shell'); listBox = el('div', 'msg-list'); threadBox = el('div', 'msg-thread'); shell.append(listBox, threadBox); main.appendChild(shell);
      document.title = 'Сообщения — Аделия'; buildThread();
      document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
      return C.api('/teacher/messages?limit=200').then(function (d) {
        st.items = d.items || []; paintList(); timer = setInterval(poll, 15000);
      }, function (e) { if (e.status === 401) { location.replace('/app/teacher.html'); return; } shell.replaceChildren(C.error(err(e), function () { location.reload(); })); });
    }
  });
})();
