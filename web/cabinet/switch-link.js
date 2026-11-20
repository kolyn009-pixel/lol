/* Ссылка «Попробовать новый кабинет» в старых кабинетах (преподаватель / ученик). */
(function () {
  'use strict';
  var p = location.pathname;
  if (p.indexOf('/app/parent') === 0 || p.indexOf('/parent') === 0 || p.indexOf('/app/cabinet/') === 0) return;
  if (document.getElementById('cabSwitchLink')) return;
  var href = /^\/teacher/.test(p) ? '/app/cabinet/teacher.html' : '/app/cabinet/student.html';
  function add() {
    if (document.getElementById('cabSwitchLink')) return;
    var a = document.createElement('a');
    a.id = 'cabSwitchLink'; a.href = href; a.textContent = 'Попробовать новый кабинет';
    var host = document.querySelector('.header-actions') || document.querySelector('main > header');
    if (host) { a.style.cssText = 'font:inherit;font-size:13px;font-weight:600;color:inherit;text-decoration:underline;text-underline-offset:3px;padding:12px 8px;min-height:44px;display:inline-flex;align-items:center'; host.insertBefore(a, host.firstChild); }
    else { a.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:300;font:600 13px/1.2 system-ui,sans-serif;color:#111;background:#fff;border:1px solid #111;padding:10px 12px;text-decoration:none'; document.body.appendChild(a); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
