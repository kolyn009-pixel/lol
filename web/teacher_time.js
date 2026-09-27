(() => {
  'use strict';
  if (window.TeacherTime) return;
  const PRESETS = [['Europe/Moscow','Москва'],['Europe/Samara','Самара'],['Asia/Yekaterinburg','Екатеринбург'],['Asia/Omsk','Омск'],['Asia/Krasnoyarsk','Красноярск'],['Asia/Irkutsk','Иркутск'],['Europe/Istanbul','Стамбул'],['Asia/Dubai','Дубай'],['Asia/Tbilisi','Тбилиси'],['Europe/Berlin','Берлин'],['Asia/Bangkok','Бангкок']];
  const DISMISS = 'adelia.teacher.display-timezone-dismiss.v1';
  const systemZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  const label = z => PRESETS.find(x => x[0] === z)?.[1] || String(z || '').split('/').pop().replace(/_/g, ' ');
  let value = null;

  function format(date, options) {
    const d = date instanceof Date ? date : new Date(date);
    if (!value || Number.isNaN(d.getTime())) return '—';
    return new Intl.DateTimeFormat('ru-RU', { ...options, timeZone: value.zone }).format(d);
  }
  function lessonDate(lesson, field = 'start') {
    // Only an offset-aware instant can be converted safely. Legacy naive fields
    // remain in the schedule's own timezone and must not be guessed from the OS.
    const raw = lesson?.[field + '_at'];
    return raw && /(?:Z|[+-]\d\d:\d\d)$/.test(raw) ? new Date(raw) : null;
  }
  function lesson(lesson, options, field = 'start') {
    const instant = lessonDate(lesson, field);
    return instant ? format(instant, options) : '—';
  }
  function refreshClock() {
    const clock = document.querySelector('#teacherLocalClock');
    if (!clock || !value) return;
    clock.querySelector('strong').textContent = format(new Date(), { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
    clock.querySelector('small').textContent = label(value.zone);
    clock.title = 'Время для просмотра · ' + value.zone + '. Запись учеников: ' + value.schedule_zone;
  }
  function changed(payload) {
    if (!payload || typeof payload.zone !== 'string') return;
    try { new Intl.DateTimeFormat('ru-RU', { timeZone: payload.zone }); } catch (_) { return; }
    value = payload;
    if (!document.querySelector('#teacherLocalClock')) {
      const header = document.querySelector('.teacher-shell main header .header-actions');
      if (!header) return;
      const clock = document.createElement('button');
      clock.id = 'teacherLocalClock'; clock.className = 'teacher-local-clock'; clock.type = 'button';
      clock.setAttribute('aria-label', 'Выбрать часовой пояс отображения');
      clock.innerHTML = '<strong>--:--</strong><small></small>';
      clock.onclick = picker;
      header.prepend(clock);
    }
    refreshClock(); suggest();
    window.dispatchEvent(new Event('adelia:teacher-timezone-changed'));
  }
  async function save(zone) {
    const response = await fetch('/api/teacher/display-timezone', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ zone }) });
    if (!response.ok) throw new Error('Не удалось сохранить пояс. Попробуйте ещё раз.');
    const data = await response.json();
    if (!data?.timezone?.zone) throw new Error('Сервер не подтвердил пояс.');
    document.querySelector('#teacherTimezoneSuggestion')?.remove();
    changed(data.timezone);
  }
  function suggest() {
    const detected = systemZone(), existing = document.querySelector('#teacherTimezoneSuggestion');
    if (!value || !detected || detected === value.zone) { existing?.remove(); return; }
    try { new Intl.DateTimeFormat('ru-RU', { timeZone: detected }); } catch (_) { return; }
    const signature = value.zone + '|' + detected;
    try { const dismissed = JSON.parse(localStorage.getItem(DISMISS) || 'null'); if (dismissed?.signature === signature && Date.now() - dismissed.at < 7 * 86400000) { existing?.remove(); return; } } catch (_) {}
    if (existing?.dataset.zone === detected) return;
    existing?.remove();
    const box = document.createElement('section');
    box.id = 'teacherTimezoneSuggestion'; box.className = 'teacher-timezone-suggestion'; box.dataset.zone = detected;
    box.innerHTML = '<b>Вы сейчас в другом регионе?</b><p></p><div><button type="button" data-change>Показать местное время</button><button type="button" data-later>Не сейчас</button></div><small role="status"></small>';
    box.querySelector('p').textContent = 'На устройстве: ' + label(detected) + '. Переключить часы и время ближайших уроков? Рабочее расписание и записи учеников не изменятся.';
    box.querySelector('[data-later]').onclick = () => { try { localStorage.setItem(DISMISS, JSON.stringify({ signature, at: Date.now() })); } catch (_) {} box.remove(); };
    box.querySelector('[data-change]').onclick = async event => { const button = event.currentTarget; button.disabled = true; try { await save(detected); } catch (error) { box.querySelector('[role="status"]').textContent = error.message; button.disabled = false; } };
    document.body.appendChild(box);
  }
  function picker() {
    if (document.querySelector('#teacherTimezonePicker')) return;
    const overlay = document.createElement('div');
    overlay.id = 'teacherTimezonePicker'; overlay.className = 'teacher-timezone-overlay';
    overlay.innerHTML = '<section role="dialog" aria-modal="true" aria-labelledby="teacherTimezoneTitle"><button type="button" class="teacher-timezone-close" aria-label="Закрыть">×</button><h2 id="teacherTimezoneTitle">Время для просмотра</h2><p>Меняются только часы и время уроков на экране «Сегодня». Регион рабочего расписания, открытые слоты и существующие записи останутся прежними.</p><label for="teacherTimezoneSelect">Регион</label><select id="teacherTimezoneSelect"></select><button type="button" class="teacher-timezone-save">Сохранить</button><small role="status"></small></section>';
    const select = overlay.querySelector('select'), zones = [...PRESETS];
    for (const z of [value?.zone, systemZone()]) if (z && !zones.some(x => x[0] === z)) zones.unshift([z, label(z)]);
    if (typeof Intl.supportedValuesOf === 'function') for (const z of Intl.supportedValuesOf('timeZone')) if (!zones.some(x => x[0] === z)) zones.push([z, label(z) + ' · ' + z]);
    for (const [z, name] of zones) select.add(new Option(name, z));
    select.value = value?.zone || systemZone() || 'Europe/Moscow';
    const close = () => overlay.remove();
    overlay.querySelector('.teacher-timezone-close').onclick = close;
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    overlay.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    overlay.querySelector('.teacher-timezone-save').onclick = async event => { const button = event.currentTarget; button.disabled = true; try { await save(select.value); close(); } catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; button.disabled = false; } };
    document.body.appendChild(overlay); select.focus();
  }
  async function load() {
    const response = await fetch('/api/teacher/display-timezone', { credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 401) return;
    if (!response.ok) throw new Error('timezone_unavailable');
    changed((await response.json()).timezone);
  }
  window.TeacherTime = { format, lessonDate, lesson, load, save, get preference() { return value; } };
  load().catch(() => {});
  setInterval(refreshClock, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { refreshClock(); load().catch(() => {}); } });
  window.addEventListener('adelia:teacher-login', () => load().catch(() => {}));
})();
