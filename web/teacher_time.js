(() => {
  'use strict';
  if (window.TeacherTime) return;
  const PRESETS = [['Europe/Moscow','Москва'],['Europe/Samara','Самара'],['Asia/Yekaterinburg','Екатеринбург'],['Asia/Omsk','Омск'],['Asia/Krasnoyarsk','Красноярск'],['Asia/Irkutsk','Иркутск'],['Europe/Istanbul','Турция · Стамбул'],['Asia/Dubai','ОАЭ · Дубай'],['Asia/Tbilisi','Грузия · Тбилиси'],['Europe/Berlin','Германия · Берлин'],['Asia/Bangkok','Таиланд · Бангкок'],['Asia/Makassar','Индонезия · Бали'],['Indian/Maldives','Мальдивы']];
  const DISMISS = 'adelia.teacher.display-timezone-dismiss.v1';
  const systemZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  const label = z => PRESETS.find(x => x[0] === z)?.[1] || String(z || '').split('/').pop().replace(/_/g, ' ');
  let value = null;

  function parts(date, zone) {
    return Object.fromEntries(new Intl.DateTimeFormat('en-GB', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'}).formatToParts(date).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));
  }
  function instant(raw) {
    if (!raw || !value) return null;
    if (/(?:Z|[+-]\d\d:\d\d)$/.test(String(raw))) { const date=new Date(raw); return Number.isNaN(date.getTime())?null:date; }
    // Legacy wall times belong to the schedule, never to the device timezone.
    const m=String(raw).match(/^(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d)(?:\.\d+)?)?$/);
    if (!m) return null;
    const numbers=m.slice(1).map(n=>Number(n||0)), guess=Date.UTC(numbers[0],numbers[1]-1,numbers[2],numbers[3],numbers[4],numbers[5]);
    const offsets=new Set([-36,0,36].map(hours=>{const ms=guess+hours*3600000,p=parts(new Date(ms),value.schedule_zone);return Date.UTC(+p.year,+p.month-1,+p.day,+p.hour,+p.minute,+p.second)-ms;}));
    const candidates=[...offsets].map(offset=>new Date(guess-offset)).filter(date=>{const p=parts(date,value.schedule_zone);return [p.year,p.month,p.day,p.hour,p.minute,p.second].every((n,i)=>+n===numbers[i]);});
    // Match Python's legacy fold=0 policy; a nonexistent DST wall time stays unknown.
    return candidates.sort((a,b)=>a-b)[0]||null;
  }
  function schedule(raw, options) { const date=instant(raw); return date?format(date,options):'—'; }
  function dateKey(raw) { const date=instant(raw); if(!date)return '';const p=parts(date,value.zone);return p.year+'-'+p.month+'-'+p.day; }
  function scheduleInput(raw) { const date=instant(raw);if(!date)return '';const p=parts(date,value.schedule_zone);return p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute; }
  function refreshLessonTimes() {
    for (const node of document.querySelectorAll?.('[data-teacher-lesson-time]')||[]) node.textContent=schedule(node.dataset.teacherLessonTime,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
  }

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
    clock.querySelector('small').textContent = value.zone === value.schedule_zone
      ? label(value.zone) + ' · как в расписании'
      : label(value.zone) + ' · расписание: ' + label(value.schedule_zone);
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
    refreshClock(); refreshLessonTimes(); suggest();
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
    overlay.innerHTML = '<section role="dialog" aria-modal="true" aria-labelledby="teacherTimezoneTitle"><button type="button" class="teacher-timezone-close" aria-label="Закрыть">×</button><h2 id="teacherTimezoneTitle">Мой регион</h2><p>Выберите регион отдыха: часы, время занятий и дни на экране «Сегодня» пересчитаются. Ученики продолжат видеть время в своих регионах. Рабочие часы и переносы вводятся в поясе расписания.</p><label for="teacherTimezoneSelect">Где показывать время</label><select id="teacherTimezoneSelect"></select><p data-timezone-preview></p><button type="button" data-device-zone>Выбрать регион устройства</button><button type="button" class="teacher-timezone-save">Сохранить</button><small role="status"></small></section>';
    const select = overlay.querySelector('select'), zones = [...PRESETS];
    for (const z of [value?.zone, systemZone()]) if (z && !zones.some(x => x[0] === z)) zones.unshift([z, label(z)]);
    if (typeof Intl.supportedValuesOf === 'function') for (const z of Intl.supportedValuesOf('timeZone')) if (!zones.some(x => x[0] === z)) zones.push([z, label(z) + ' · ' + z]);
    select.add(new Option('Как в расписании · ' + label(value?.schedule_zone), 'schedule'));
    for (const [z, name] of zones) select.add(new Option(name, z));
    select.value = value?.selected ? value.zone : 'schedule';
    const preview=()=>{const zone=select.value==='schedule'?value.schedule_zone:select.value,now=new Date(),opts={hour:'2-digit',minute:'2-digit',hourCycle:'h23'};overlay.querySelector('[data-timezone-preview]').textContent='Сейчас: '+new Intl.DateTimeFormat('ru-RU',{...opts,timeZone:zone}).format(now)+' · '+label(zone)+'. Расписание: '+new Intl.DateTimeFormat('ru-RU',{...opts,timeZone:value.schedule_zone}).format(now)+' · '+label(value.schedule_zone);};
    select.onchange=preview;preview();
    overlay.querySelector('[data-device-zone]').onclick=()=>{select.value=systemZone()||'schedule';preview();};
    const close = () => overlay.remove();
    overlay.querySelector('.teacher-timezone-close').onclick = close;
    overlay.addEventListener('click', event => { if (event.target === overlay) close(); });
    overlay.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
    overlay.querySelector('.teacher-timezone-save').onclick = async event => { const button = event.currentTarget; button.disabled = true; try { await save(select.value); close(); } catch (error) { overlay.querySelector('[role="status"]').textContent = error.message; button.disabled = false; } };
    document.body.appendChild(overlay); select.focus();
  }
  let loading = null;
  function load() {
    if (loading) return loading;
    const ctrl = new AbortController();
    let timer;
    const expired = new Promise((_, reject) => {
      timer = setTimeout(() => { ctrl.abort(); reject(new Error('NETWORK_TIMEOUT')); }, 12000);
    });
    const request = (async () => {
      const response = await fetch('/api/teacher/display-timezone', { credentials: 'same-origin', cache: 'no-store', signal: ctrl.signal });
      if (response.status === 401) return;
      if (!response.ok) throw new Error('timezone_unavailable');
      const data = await response.json();
      if (ctrl.signal.aborted) throw new Error('NETWORK_TIMEOUT');
      if (!data?.timezone?.zone) throw new Error('timezone_unavailable');
      changed(data.timezone);
    })();
    loading = Promise.race([request, expired]).catch(error => {
      if (error?.name === 'AbortError') throw new Error('NETWORK_TIMEOUT');
      throw error;
    }).finally(() => { clearTimeout(timer); loading = null; });
    return loading;
  }
  window.TeacherTime = { format, lessonDate, lesson, instant, schedule, dateKey, scheduleInput, label, load, save, open:async()=>{if(!value)await load();if(value)picker();}, ready:()=>value?Promise.resolve(value):load(), get preference() { return value; } };
  load().catch(() => {});
  setInterval(refreshClock, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { refreshClock(); load().catch(() => {}); } });
  window.addEventListener('adelia:teacher-login', () => load().catch(() => {}));
  window.addEventListener('adelia:schedule-timezone-changed', () => load().catch(() => {}));
})();
