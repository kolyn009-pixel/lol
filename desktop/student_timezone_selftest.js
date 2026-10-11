'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const manifest = require('./bundled_ui_manifest');

assert.equal(manifest.student.js[0], 'student_time.js');
assert(manifest.student.css.includes('desktop_premium.css'));
assert.equal(manifest.student.css.at(-1), 'interface_unified.css');
assert(manifest.student.css.indexOf('desktop_premium.css')<manifest.student.css.indexOf('interface_unified.css'));

const events = [], writes = [];
const window = { adeliaDesktop: { desktop: true }, addEventListener: () => {}, dispatchEvent: event => events.push(event.type) };
const document = {
  querySelector: () => null,
  addEventListener: () => {},
  hidden: false
};
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, '..', 'web', 'student_time.js'), 'utf8'),
  { window, document, Date, Intl, Event: class { constructor(type) { this.type = type; } },
    fetch: (url, options) => {
      if (options?.method !== 'POST') return Promise.reject(new Error('offline'));
      writes.push({ url, options });
      return Promise.resolve({ ok: true, json: async () => ({ timezone: { zone: 'Europe/Istanbul', label: 'Стамбул', selected: true } }) });
    }, setInterval: () => 0 }
);
const time = window.StudentTime;
const lesson = {
  start_at: '2026-09-27T20:00:00+04:00',
  end_at: '2026-09-27T21:00:00+04:00'
};
const format = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };

assert.equal(time.setTimezone({ zone: 'Europe/Samara', label: 'Самара', selected: true }), true);
assert.equal(time.formatLesson(lesson, format), '20:00');
assert.equal(time.formatLesson(lesson, format, 'end'), '21:00');
assert.equal(time.setTimezone({ zone: 'Europe/Moscow', label: 'Москва', selected: true }), true);
assert.equal(time.formatLesson(lesson, format), '19:00');
assert.equal(time.setTimezone({ zone: 'Not/AZone', label: 'Ошибка', selected: true }), false);
assert.equal(time.formatLesson(lesson, format), '19:00');
assert.equal(time.lessonDate(lesson).toISOString(), '2026-09-27T16:00:00.000Z');

const workspace = { exports: {} };
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, 'lesson_workspace.js'), 'utf8'),
  {
    module: workspace,
    require: name => {
      if (name !== 'electron') throw new Error('unexpected import: ' + name);
      return { app: {}, BrowserWindow: {}, Notification: {} };
    },
    Date, Intl, URL, Set, process, setTimeout, setInterval
  }
);
const normalized = workspace.exports.normalizeLesson(
  { id: 1, start_time: '2026-09-27T20:00:00', start_at: lesson.start_at },
  { zone: 'Europe/Samara', label: 'Самара' }
);
assert.equal(normalized.start.toISOString(), '2026-09-27T16:00:00.000Z');
assert.equal(workspace.exports.formatTime(normalized.start, normalized.timezone), '20:00');
assert.equal(workspace.exports.formatTime(normalized.start, { zone: 'Europe/Moscow' }), '19:00');
time.saveTimezone('Europe/Istanbul').then(() => {
  assert.equal(writes.length, 1);
  assert.equal(writes[0].url, '/api/student/timezone');
  assert.equal(JSON.parse(writes[0].options.body).zone, 'Europe/Istanbul');
  assert.equal(time.preference.zone, 'Europe/Istanbul');
  assert.deepEqual(events, ['adelia:student-timezone-changed']);
  console.log('STUDENT_DESKTOP_TIMEZONE=PASS');
}).catch(error => { console.error(error); process.exitCode = 1; });
