/* Старые кабинеты: автопереход в новый кабинет своей роли + ссылка «Новый кабинет» при ?classic=1. */
(function () {
  'use strict';
  var p = location.pathname.replace(/\/index\.html$/, '/').replace(/\/+$/, '/') || '/';
  var NEW = { teacher: '/app/cabinet/teacher.html', student: '/app/cabinet/student.html', parent: '/app/cabinet/parent.html' };
  var kind = null;
  if (p === '/teacher/' || p === '/app/teacher.html/' || /^\/app\/teacher\.html$/.test(location.pathname)) kind = 'teacher';
  else if (p === '/app/parent/' || p === '/parent/') kind = 'parent';
  else if (p === '/app/' || p === '/app') kind = 'student';
  if (!kind || document.getElementById('cabSwitchLink')) return;
  var classic = /[?&]classic=1(&|#|$)/.test(location.search);
  var pref = null; try { pref = localStorage.getItem('adelia:cabinet'); } catch (e) {}

  if (!classic && pref !== 'old') {
    try {
      fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (d) {
        if (!d || d.authenticated !== true) return;
        var role = d.role || (d.session && d.session.role);
        if (false && NEW[role]) location.replace(NEW[role] + (location.hash || ''));
      }).catch(function () {});
    } catch (e) {}
    return;
  }

  var href = NEW[kind];
  function add() {
    if (document.getElementById('cabSwitchLink')) return;
    var a = document.createElement('a');
    a.id = 'cabSwitchLink'; a.href = href; a.textContent = 'Новый кабинет';
    a.addEventListener('click', function () { try { localStorage.removeItem('adelia:cabinet'); } catch (e) {} });
    var host = document.querySelector('.header-actions') || document.querySelector('main > header');
    if (host) { a.style.cssText = 'font:inherit;font-size:13px;font-weight:600;color:inherit;text-decoration:underline;text-underline-offset:3px;padding:12px 8px;min-height:44px;display:inline-flex;align-items:center'; host.insertBefore(a, host.firstChild); }
    else { a.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:300;font:600 13px/1.2 system-ui,sans-serif;color:#111;background:#fff;border:1px solid #111;padding:10px 12px;text-decoration:none'; document.body.appendChild(a); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
})();
