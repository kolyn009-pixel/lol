(() => {
  'use strict';
  if (window.AdeliaOnlinePayment) return;
  const endpoint = '/api/payments/robokassa/';
  async function request(path, options = {}) {
    const response = await fetch(endpoint + path, {credentials: 'same-origin', cache: 'no-store', ...options});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'payment_unavailable');
    return data;
  }
  async function mount(container, paymentId, studentId = null, manualNodes = []) {
    if (!container || container.dataset.onlineMounted) return;
    container.dataset.onlineMounted = '1';
    let status;
    try { status = await request('status'); } catch (_) { return; }
    if (!status.enabled || !container.isConnected) return;
    const box = document.createElement('section');
    box.style.cssText = 'display:grid;gap:8px;margin:12px 0';
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'finance-primary';
    button.style.minHeight = '44px';
    const label = status.test ? 'Тестовая оплата · Робокасса' : 'Оплатить онлайн · Робокасса';
    button.textContent = label;
    const hint = document.createElement('small');
    hint.textContent = status.test ? 'Тестовый режим: баланс занятий не изменится.' : 'Сумма уже указана. Оплата подтвердится автоматически после ответа Робокассы.';
    const message = document.createElement('p'); message.setAttribute('role', 'status');
    message.style.margin = '0';
    box.append(button, hint, message); container.prepend(box);
    if (manualNodes.length) {
      const manual = document.createElement('details');
      const summary = document.createElement('summary'); summary.textContent = 'Перевести по QR Сбера';
      summary.style.cssText = 'cursor:pointer;padding:12px 0'; manual.append(summary);
      for (const node of manualNodes) if (node?.isConnected) manual.append(node);
      box.after(manual);
    }
    button.onclick = async () => {
      button.disabled = true; button.textContent = 'Открываю оплату…'; message.textContent = '';
      try {
        const data = await request('checkout', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({payment_id: paymentId, student_id: studentId})});
        const url = new URL(data.url);
        if (url.origin !== 'https://auth.robokassa.ru' || url.pathname !== '/Merchant/Index.aspx') throw new Error('invalid_payment_url');
        const link = document.createElement('a'); link.href = url.href;
        link.textContent = 'Открыть страницу оплаты'; link.rel = 'noopener noreferrer'; link.target = '_blank';
        message.replaceChildren(link);
        // Desktop handles external navigation through its existing browser policy.
        window.location.assign(url.href);
      } catch (_) {
        message.textContent = 'Не удалось открыть оплату. Обновите статус счёта и попробуйте ещё раз. Если деньги уже списаны, повторно не оплачивайте.';
      } finally {
        button.disabled = false; button.textContent = label;
      }
    };
  }
  window.AdeliaOnlinePayment = {mount};
})();
