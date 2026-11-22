/* Open Journal on normal web entry. Shortcut, desktop and installed-app routes keep their handlers. */
(function () {
  'use strict';
  var path = location.pathname.replace(/\/index\.html$/, '').replace(/\/+$/, '');
  var role = {
    '/teacher': 'teacher', '/app/teacher.html': 'teacher', '/app/parent': 'parent', '/parent': 'parent', '/app': 'student'
  }[path];
  if (!role) return;

  var current = new URL(location.href);
  var next = '/app/cabinet/' + role + '.html';
  var section = current.searchParams.get('section');
  var check;
  var navigationDone = false;
  var authenticated = false;

  function standalone() {
    return !!(window.adeliaDesktop?.desktop || navigator.standalone ||
      window.matchMedia('(display-mode: standalone), (display-mode: fullscreen)').matches);
  }

  function prefersClassic() {
    try { return localStorage.getItem('adelia:cabinet') === 'old'; }
    catch (_) { return false; }
  }

  function addLink() {
    if (standalone()) return;
    var a = document.getElementById('cabSwitchLink');
    if (!a) {
      a = document.createElement('a');
      a.id = 'cabSwitchLink';
      a.href = next;
      a.textContent = 'Кабинет «Журнал»';
      a.addEventListener('click', function () {
        try { localStorage.removeItem('adelia:cabinet'); } catch (_) {}
      });
    }
    var host = document.querySelector('.header-actions, #root > header, .topbar');
    if (a.parentNode === (host || document.body)) return;
    a.className = 'journal-cabinet-link' + (host ? '' : ' is-floating');
    (host || document.body).appendChild(a);
  }

  function openSection() {
    if (navigationDone) return;
    var selector = role === 'teacher' && {
      schedule: '[data-view="schedule"]', groups: '[data-view="groups"]', students: '[data-view="students"]',
      library: '[data-view="library"]', formulas: '[data-view="formulas"]',
      finance: '[data-view="finance"]', analytics: '[data-view="analytics"]',
      health: '[data-view="health"]', plans: '[data-learning-open]', requests: '[data-request-center]',
      homework: '[data-view="newHomework"]'
    }[section];
    if (role === 'parent' && section === 'messages') selector = '#parentMessagesOpen';
    if (role === 'student' && section === 'formulas') selector = '[data-tab="formulas"]';
    if (typeof selector !== 'string') return;
    if (role === 'teacher' && document.querySelector('#app > .loading')) {
      var app = document.querySelector('#app');
      var observer = new MutationObserver(function () {
        if (!app.querySelector(':scope > .loading')) { observer.disconnect(); openSection(); }
      });
      observer.observe(app, { childList: true });
      setTimeout(function () { observer.disconnect(); }, 15000);
      return;
    }
    var button = document.querySelector(selector);
    if (button) {
      navigationDone = true;
      button.click();
    }
  }

  function inspectSession() {
    if (navigationDone) return;
    if (check) return check;
    check = fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (session) {
        if (!session || session.authenticated !== true || (session.role || session.session?.role) !== role) return;
        authenticated = true;
        if (!standalone() && !current.search && !current.hash && !prefersClassic()) {
          navigationDone = true;
          location.replace(next);
          return;
        }
        addLink();
        openSection();
      })
      .catch(function () { /* the current cabinet still handles connection and sign-in */ })
      .finally(function () { check = null; });
    return check;
  }

  if (role === 'parent') {
    window.addEventListener('adelia:parent-render', function (event) {
      if (!event.detail?.parentId) return;
      if (authenticated) { addLink(); openSection(); }
      else inspectSession();
    });
  } else {
    window.addEventListener(role === 'teacher' ? 'adelia:teacher-login' : 'adelia:student-authenticated',
      function () { if (check) check.then(inspectSession); else inspectSession(); }, { once: true });
  }
  inspectSession();
})();
