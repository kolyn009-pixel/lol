'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const manifest = require('./bundled_ui_manifest');

assert.equal(manifest.student.js[0], 'student_time.js');
assert.equal(manifest.student.css.at(-1), 'desktop_premium.css');

const window = { adeliaDesktop: { desktop: true } };
const document = {
  querySelector: () => null,
  addEventListener: () => {},
  hidden: false
};
vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, '..', 'web', 'student_time.js'), 'utf8'),
  { window, document, Date, Intl, fetch: () => Promise.reject(new Error('offline')), setInterval: () => 0 }
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
console.log('STUDENT_DESKTOP_TIMEZONE=PASS');
