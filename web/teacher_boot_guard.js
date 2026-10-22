/* Embedded before stylesheets so stalled defer scripts cannot block recovery. */
(() => {
  'use strict';
  if (window.AdeliaTeacherBootGuard) return;
  window.AdeliaTeacherBootGuard = true;
  const failed = new Set();
  window.addEventListener('error', event => {
    const raw = event.target?.src || event.target?.href;
    if (!raw) return;
    try {
      const url = new URL(raw, location.origin);
      if (url.origin === location.origin) failed.add(url.pathname.split('/').pop());
    } catch (_) {}
  }, true);
  setTimeout(() => {
    const root = document.querySelector('#app');
    if (!root || !root.querySelector(':scope > .loading')) return;
    root.innerHTML = '<section class="error" style="padding:24px;background:#fff;border:1px solid #ded6ed;border-radius:18px;font:16px system-ui;color:#282132"><b>Не удалось завершить загрузку кабинета</b><p>Проверьте соединение и повторите загрузку. Если проблема повторится, передайте преподавателю результат проверки ниже.</p><p data-boot-details role="status"></p><div style="display:flex;gap:12px;flex-wrap:wrap"><button type="button" data-boot-check>Проверить соединение</button><button type="button" data-boot-reload>Обновить файлы кабинета</button></div></section>';
    const panel = root.firstElementChild;
    const details = panel.querySelector('[data-boot-details]');
    details.textContent = failed.size ? 'Не загрузились файлы: ' + [...failed].join(', ') : 'Загрузка интерфейса или данных не завершилась.';
    panel.querySelector('[data-boot-check]').onclick = async event => {
      const button = event.currentTarget;
      button.disabled = true;
      const ctrl = new AbortController();
      let timer;
      try {
        const request = (async () => {
          const response = await fetch('/api/health', { cache: 'no-store', credentials: 'same-origin', signal: ctrl.signal });
          const data = await response.json();
          if (!response.ok || data.ok !== true) throw new Error('health_failed');
        })();
        await Promise.race([request, new Promise((_, reject) => { timer = setTimeout(() => { ctrl.abort(); reject(new Error('timeout')); }, 5000); })]);
        details.textContent = 'Сервер отвечает. ' + (failed.size ? 'Не загрузились файлы: ' + [...failed].join(', ') : 'Нужно повторить загрузку кабинета.');
      } catch (_) { details.textContent = 'Проверка соединения с сервером не прошла. Попробуйте другую сеть и повторите проверку.'; }
      finally { clearTimeout(timer); button.disabled = false; }
    };
    panel.querySelector('[data-boot-reload]').onclick = async event => {
      event.currentTarget.disabled = true;
      try {
        if ('caches' in window) for (const name of await caches.keys()) {
          if (!name.startsWith('adelia-')) continue;
          const cache = await caches.open(name);
          for (const request of await cache.keys()) {
            const url = new URL(request.url);
            if (url.origin === location.origin && (/^\/app\/teacher(?:[_.-]|\/)/.test(url.pathname) || url.pathname === '/teacher/')) await cache.delete(request);
          }
        }
      } catch (_) {}
      const url = new URL(location.href);
      url.searchParams.set('boot_refresh', String(Date.now()));
      location.replace(url.href);
    };
  }, 18000);
})();
