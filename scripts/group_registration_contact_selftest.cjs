const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'web/start/group.js'), 'utf8');
const cases = JSON.parse(fs.readFileSync(path.join(__dirname, 'group_registration_contact_cases.json'), 'utf8'));
new vm.Script(source);
const start = source.indexOf('  function normalizeContact(');
const end = source.indexOf('  function validateContact(');
assert(start >= 0 && end > start);
const context = { URL };
vm.runInNewContext(source.slice(start, end), context);
for (const [input, expected] of cases) {
  assert.equal(context.normalizeContact(input), expected, JSON.stringify(input));
}
console.log(`CONTACT_VALIDATION_OK: ${cases.length} cases`);
