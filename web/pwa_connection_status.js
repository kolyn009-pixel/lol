(() => {
  'use strict';
  if (window.adeliaDesktop?.desktop || document.querySelector('#adeliaConnectionStatus')) return;
  const bar = document.createElement('aside');
  bar.id = 'adeliaConnectionStatus';
  bar.className = 'adelia-connection-status';
  bar.setAttribute('role', 'status');
  bar.setAttribute('aria-live', 'polite');
  bar.hidden = true;
  bar.innerHTML = '<span></span><button type="button">Повторить</button>';
  bar.querySelector('button').onclick = () => location.reload();
  let wasOffline = false;
  function update() {
    const offline = navigator.onLine === false;
    if (offline) {
      wasOffline = true;
      bar.querySelector('span').textContent = 'Нет соединения. Последние открытые экраны могут быть доступны, новые данные появятся после подключения.';
      bar.querySelector('button').hidden = false;
      bar.hidden = false;
    } else if (wasOffline) {
      bar.querySelector('span').textContent = 'Соединение восстановлено. Обновите данные.';
      bar.querySelector('button').hidden = false;
      bar.hidden = false;
    } else {
      bar.hidden = true;
    }
  }
  function mount() { if (!bar.isConnected) document.body.appendChild(bar); update(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, { once: true });
  else mount();
  window.addEventListener('online', update);
  window.addEventListener('offline', update);
})();
