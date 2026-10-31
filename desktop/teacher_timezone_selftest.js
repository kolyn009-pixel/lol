'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const manifest = require('./bundled_ui_manifest');
assert(manifest.teacher.js.includes('teacher_time.js'));
const window = { addEventListener() {}, dispatchEvent() {} };
const document = { querySelector() { return null; }, addEventListener() {}, hidden: false };
let writes = 0;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', 'web', 'teacher_time.js'), 'utf8'), {
  window, document, Intl, Date, Event, AbortController, setTimeout, clearTimeout, setInterval() {},
  fetch: async (url, options) => {
    if (options?.method === 'POST') {
      writes += 1;
      assert.equal(url, '/api/teacher/display-timezone');
      assert.equal(JSON.parse(options.body).zone, 'Europe/Moscow');
      return { ok: true, json: async () => ({ timezone: { zone: 'Europe/Moscow', selected: true, schedule_zone: 'Europe/Samara' } }) };
    }
    return { ok: true, json: async () => ({ timezone: { zone: 'Europe/Samara', selected: false, schedule_zone: 'Europe/Samara' } }) };
  }
});
const time = window.TeacherTime;
(async () => {
  await time.load();
  const row = { start_time: '2026-09-27T20:00:00', start_at: '2026-09-27T20:00:00+04:00' };
  const options = { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' };
  assert.equal(time.lesson(row, options), '20:00');
  assert.equal(time.lesson({ start_time: row.start_time }, options), '—');
  await time.save('Europe/Moscow');
  assert.equal(writes, 1);
  assert.equal(time.lesson(row, options), '19:00');
  assert.equal(time.preference.schedule_zone, 'Europe/Samara');
  assert.equal(new Date(row.start_at).toISOString(), '2026-09-27T16:00:00.000Z');
  console.log('TEACHER_DISPLAY_TIMEZONE=PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
