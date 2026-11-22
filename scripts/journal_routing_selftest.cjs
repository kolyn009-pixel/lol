'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const cabinet = path.resolve(__dirname, '../web/cabinet');
const switchSource = fs.readFileSync(path.join(cabinet, 'switch-link.js'), 'utf8');
const settle = () => new Promise(resolve => setImmediate(resolve));

function fixture(route, initialRole, options = {}) {
  const next = [], links = [], clicked = [];
  const events = new Map();
  let sessionRole = initialRole, pref = options.preference;
  const host = { appendChild(link) { link.parentNode = this; links.push(link); } };
  const href = 'https://example.test' + route;
  const window = {
    adeliaDesktop: options.desktop && { desktop: true },
    matchMedia: () => ({ matches: Boolean(options.installed) }),
    addEventListener(name, listener) { events.set(name, listener); },
  };
  const document = {
    body: host,
    getElementById: () => links[0],
    createElement: () => ({ addEventListener(_name, listener) { this.onClick = listener; } }),
    querySelector(selector) {
      if (selector.includes('.header-actions')) return host;
      if (selector === options.sectionSelector) return { click() { clicked.push(selector); } };
      return null;
    },
  };
  vm.runInNewContext(switchSource, {
    window, document, URL,
    location: { href, pathname: new URL(href).pathname, replace: url => next.push(url) },
    navigator: {},
    localStorage: { getItem: () => pref, removeItem() { pref = null; } },
    fetch: async () => {
      if (options.offline) throw new Error('offline');
      return { ok: true, json: async () => ({ authenticated: Boolean(sessionRole), session: { role: sessionRole } }) };
    },
  });
  return {
    next, links, clicked, preference: () => pref,
    login(event, role) { sessionRole = role; events.get(event)?.({ detail: { parentId: 4 } }); },
  };
}

(async () => {
  for (const [route, role] of [['/teacher/', 'teacher'], ['/app/teacher.html', 'teacher'],
    ['/app/index.html', 'student'], ['/app/parent/', 'parent']]) {
    const f = fixture(route, role);
    await settle();
    assert.deepEqual(f.next, ['/app/cabinet/' + role + '.html']);
  }

  for (const [route, role, options] of [
    ['/teacher/#schedule', 'teacher', {}],
    ['/app/?homework=27', 'student', {}],
    ['/app/?classic=1', 'student', {}],
    ['/app/', 'student', { desktop: true }],
    ['/app/parent/', 'parent', { installed: true }],
    ['/app/', 'student', { preference: 'old' }],
    ['/app/', 'parent', {}],
    ['/app/', null, { offline: true }],
  ]) {
    const f = fixture(route, role, options);
    await settle();
    assert.deepEqual(f.next, [], route);
    if (options.desktop || options.installed || options.offline) assert.equal(f.links.length, 0);
    if (options.preference) {
      assert.equal(f.links[0].href, '/app/cabinet/student.html');
      f.links[0].onClick();
      assert.equal(f.preference(), null);
    }
  }

  const pending = fixture('/app/teacher.html', null);
  pending.login('adelia:teacher-login', 'teacher');
  await settle();
  assert.deepEqual(pending.next, ['/app/cabinet/teacher.html']);

  const selector = '#parentMessagesOpen';
  const messages = fixture('/app/parent/?section=messages&classic=1', 'parent', { sectionSelector: selector });
  await settle();
  messages.login('adelia:parent-render', 'parent');
  await settle();
  assert.deepEqual(messages.clicked, [selector]);
  assert.deepEqual(messages.next, []);

  const context = { window: {}, document: { addEventListener() {} } };
  vm.runInNewContext(fs.readFileSync(path.join(cabinet, 'core.js'), 'utf8'), context);
  const C = context.window.C;
  assert.equal(C.classic('/app/?homework=27#start'), '/app/?homework=27&classic=1#start');
  assert.equal(C.classic('/app/?classic=1#start'), '/app/?classic=1#start');
  assert.equal(C.classic('/app/cabinet/schedule.html'), '/app/cabinet/schedule.html');
  for (const { href } of C.TEACHER_MENU) {
    assert.ok(fs.existsSync(path.join(cabinet, href.split('/').pop().split('?')[0])), href);
  }
  console.log('JOURNAL_ROUTING=PASS: role entry, login, deep links, classic choice, offline, PWA and Electron');
})().catch(error => { console.error(error); process.exitCode = 1; });
