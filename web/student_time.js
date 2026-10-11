(() => {
  'use strict';
  if (window.StudentTime) return;

  let preference = null;
  let loading = null;
  let lastLoad = 0;
  let failed = false;
  const CLOCK_REFRESH_MS = 5 * 60 * 1000;
  const DISMISS_KEY = 'adelia.desktop.timezone-suggestion.v1';
  const PRESETS = [
    ['Europe/Moscow', 'Москва'], ['Europe/Samara', 'Самара'],
    ['Asia/Yekaterinburg', 'Екатеринбург'], ['Asia/Omsk', 'Омск'],
    ['Asia/Krasnoyarsk', 'Красноярск'], ['Asia/Irkutsk', 'Иркутск'],
    ['Europe/Istanbul', 'Стамбул'], ['Asia/Dubai', 'Дубай'],
    ['Asia/Tbilisi', 'Тбилиси'], ['Europe/Berlin', 'Берлин'],
    ['Asia/Bangkok', 'Бангкок']
  ];
  const systemZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  const zoneLabel = zone => PRESETS.find(item => item[0] === zone)?.[1]
    || String(zone || '').split('/').pop().replace(/_/g, ' ');

  function setTimezone(value) {
    if (!value || typeof value.zone !== 'string') return false;
    try { new Intl.DateTimeFormat('ru-RU', { timeZone: value.zone }); }
    catch (_) { return false; }
    preference = {
      zone: value.zone,
      label: String(value.label || value.zone),
      selected: value.selected === true
    };
    failed = false;
    lastLoad = Date.now();
    updateClock();
    maybeSuggest();
    return true;
  }

  async function saveTimezone(zone) {
    const response = await fetch('/api/student/timezone', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zone })
    });
    if (!response.ok) throw new Error('Не удалось сохранить часовой пояс. Попробуйте ещё раз.');
    const data = await response.json();
    if (!setTimezone(data?.timezone)) throw new Error('Сервер не подтвердил часовой пояс.');
    document.querySelector('#studentTimezoneSuggestion')?.remove();
    window.dispatchEvent(new Event('adelia:student-timezone-changed'));
    return preference;
  }

  function maybeSuggest() {
    if (!preference || !document.body) return;
    const detected = systemZone();
    const existing = document.querySelector('#studentTimezoneSuggestion');
    if (!detected || detected === preference.zone) { existing?.remove(); return; }
    try { new Intl.DateTimeFormat('ru-RU', { timeZone: detected }); }
    catch (_) { return; }
    const signature = preference.zone + '|' + detected;
    try {
      const dismissed = JSON.parse(localStorage.getItem(DISMISS_KEY) || 'null');
      if (dismissed?.signature === signature && Date.now() - dismissed.at < 7 * 86400000) return;
    } catch (_) {}
    if (existing?.dataset.zone === detected) return;
    existing?.remove();
    const prompt = document.createElement('section');
    prompt.id = 'studentTimezoneSuggestion';
    prompt.className = 'student-timezone-suggestion';
    prompt.dataset.zone = detected;
    prompt.setAttribute('aria-label', 'Предложение сменить часовой пояс');
    prompt.innerHTML = '<b>Вы в другом часовом поясе?</b><p></p><div><button type="button" data-change>Переключить</button><button type="button" data-dismiss>Не сейчас</button></div><small role="status"></small>';
    prompt.querySelector('p').textContent = 'На компьютере выбран пояс «' + zoneLabel(detected) + '». Показать часы и занятия по этому времени?';
    prompt.querySelector('[data-dismiss]').onclick = () => {
      try { localStorage.setItem(DISMISS_KEY, JSON.stringify({ signature, at: Date.now() })); }
      catch (_) {}
      prompt.remove();
    };
    prompt.querySelector('[data-change]').onclick = async event => {
      event.currentTarget.disabled = true;
      try { await saveTimezone(detected); }
      catch (error) { prompt.querySelector('[role="status"]').textContent = error.message; event.currentTarget.disabled = false; }
    };
    document.body.appendChild(prompt);
  }

  function openPicker() {
    if (document.querySelector('#studentTimezonePicker')) return;
    const overlay = document.createElement('div');
    overlay.id = 'studentTimezonePicker';
    overlay.className = 'student-timezone-overlay';
    overlay.innerHTML = '<section role="dialog" aria-modal="true" aria-labelledby="studentTimezoneTitle"><button type="button" class="student-timezone-close" aria-label="Закрыть">×</button><span class="student-timezone-kicker">Время занятий</span><h2 id="studentTimezoneTitle">Ваш часовой пояс</h2><p>Выберите регион, чтобы часы и занятия отображались по местному времени. Время начала самого урока не изменится.</p><label for="studentTimezoneSelect">Регион</label><select id="studentTimezoneSelect"></select><button type="button" class="student-timezone-save">Сохранить регион</button><small role="status"></small></section>';
    const select = overlay.querySelector('select');
    const zones = [...PRESETS];
    const detected = systemZone();
    if (detected && !zones.some(item => item[0] === detected)) zones.unshift([detected, zoneLabel(detected) + ' · пояс компьютера']);
    if (preference?.zone && !zones.some(item => item[0] === preference.zone)) zones.unshift([preference.zone, preference.label]);
    if (typeof Intl.supportedValuesOf === 'function') {
      for (const zone of Intl.supportedValuesOf('timeZone')) {
        if (!zones.some(item => item[0] === zone)) zones.push([zone, zoneLabel(zone) + ' · ' + zone]);
      }
    }
    for (const [zone, label] of zones) select.add(new Option(label, zone));
    select.value = preference?.zone || detected || 'Europe/Moscow';
    const close = () => overlay.remove();
    overlay.querySelector('.student-timezone-close').onclick = close;
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    overlay.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    overlay.querySelector('.student-timezone-save').onclick = async event => {
      event.currentTarget.disabled = true;
      try { await saveTimezone(select.value); close(); }
      catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; event.currentTarget.disabled = false; }
    };
    document.body.appendChild(overlay);
    select.focus();
  }

  async function load(force = false) {
    if (!force && preference && Date.now() - lastLoad < CLOCK_REFRESH_MS) return preference;
    if (loading) return loading;
    loading = fetch('/api/student/dashboard', { credentials: 'same-origin', cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error('timezone_unavailable');
        return response.json();
      })
      .then(data => {
        if (!setTimezone(data?.student?.timezone)) throw new Error('timezone_unavailable');
        return preference;
      })
      .catch(error => { failed = true; updateClock(); throw error; })
      .finally(() => { loading = null; });
    return loading;
  }

  function lessonDate(lesson, field = 'start') {
    const raw = lesson?.[field + '_at'] || lesson?.[field + '_time'];
    if (!raw) return null;
    const date = new Date(raw);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDate(date, options) {
    if (!preference || !(date instanceof Date) || Number.isNaN(date.getTime())) return '—';
    return new Intl.DateTimeFormat('ru-RU', {
      ...options,
      timeZone: preference.zone
    }).format(date);
  }

  function formatLesson(lesson, options, field = 'start') {
    return formatDate(lessonDate(lesson, field), options);
  }

  function mountClock() {
    const topbar = document.querySelector('.topbar');
    if (!topbar || document.querySelector('#studentLocalClock')) return;
    const clock = document.createElement('button');
    clock.id = 'studentLocalClock';
    clock.className = 'student-local-clock';
    clock.type = 'button';
    clock.setAttribute('aria-label', 'Изменить часовой пояс ученика');
    clock.innerHTML = '<span class="student-local-clock-face">--:--</span><span class="student-local-clock-zone">Определяем часовой пояс…</span>';
    clock.onclick = openPicker;
    topbar.insertBefore(clock, topbar.querySelector('#roleButton'));
    updateClock();
  }

  function updateClock() {
    const clock = document.querySelector('#studentLocalClock');
    if (!clock) return;
    const face = clock.querySelector('.student-local-clock-face');
    const zone = clock.querySelector('.student-local-clock-zone');
    if (!preference) {
      face.textContent = '--:--';
      zone.textContent = failed ? 'Часовой пояс недоступен' : 'Определяем часовой пояс…';
      return;
    }
    face.textContent = formatDate(new Date(), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    zone.textContent = preference.selected
      ? preference.label + ' · ваше время'
      : preference.label + ' · по умолчанию';
    clock.title = 'Изменить часовой пояс · ' + preference.zone;
  }

  window.StudentTime = { load, setTimezone, saveTimezone, lessonDate, formatDate, formatLesson, get preference() { return preference; } };
  if (window.adeliaDesktop?.desktop) { mountClock(); load().catch(updateClock); }
  window.addEventListener('adelia:student-authenticated', () => { mountClock(); load(true).catch(updateClock); });
  setInterval(() => { updateClock(); load().catch(() => {}); }, 60 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { updateClock(); load().catch(() => {}); }
  });
})();
