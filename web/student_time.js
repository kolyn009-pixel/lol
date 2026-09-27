(() => {
  'use strict';
  if (!window.adeliaDesktop?.desktop || window.StudentTime) return;

  let preference = null;
  let loading = null;
  let lastLoad = 0;
  let failed = false;
  const CLOCK_REFRESH_MS = 5 * 60 * 1000;

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
    return true;
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
    const clock = document.createElement('div');
    clock.id = 'studentLocalClock';
    clock.className = 'student-local-clock';
    clock.setAttribute('role', 'status');
    clock.setAttribute('aria-label', 'Текущее время ученика');
    clock.innerHTML = '<span class="student-local-clock-face">--:--</span><span class="student-local-clock-zone">Определяем часовой пояс…</span>';
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
    clock.title = preference.zone;
  }

  window.StudentTime = { load, setTimezone, lessonDate, formatDate, formatLesson, get preference() { return preference; } };
  mountClock();
  load().catch(updateClock);
  setInterval(() => { updateClock(); load().catch(() => {}); }, 60 * 1000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { updateClock(); load().catch(() => {}); }
  });
})();
