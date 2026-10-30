const fs=require('fs'),assert=require('node:assert/strict');
const {parseHTML}=require('../qa-deps/node_modules/linkedom');
const {cascade}=require('./mobile_cascade_selftest.cjs');
const source=fs.readFileSync(require('path').join(__dirname,'../web/lesson_calendar.css'),'utf8');

const {document}=parseHTML('<html><body><div id="app"><section class="lc-app"><div class="lc-day lc-today"><button class="lc-day-number">30</button><button class="lc-event lc-compact lc-done"><span class="lc-event-main"><small>Физика · 10 класс</small></span></button><button class="lc-event lc-compact lc-moved"></button><button class="lc-event lc-compact lc-unpaid"></button></div></section></div></body></html>');
for(const width of [390,650,900,1440,1920]){
 const c=cascade(document,width,source);
 assert.equal(c('.lc-day-number','border').value,'0');
 assert.equal(c('.lc-day-number','padding').value,'0');
 assert.equal(c('.lc-day-number','min-height').value,'25px');
 assert.equal(c('.lc-day-number','background').value,'#7952d1');
 assert.equal(c('.lc-done','background').value,'var(--lc-surface)');
 assert.equal(c('.lc-done','--lc-surface').value,'#eef7f3');
 assert.equal(c('.lc-moved','--lc-surface').value,'#edf7f8');
 assert.equal(c('.lc-unpaid','--lc-surface').value,'#fbf6ea');
 assert.equal(c('.lc-event-main small','font-size').value,width>=1600?'9px':'8px');
 assert.equal(c('.lc-done','height').value,'47px');
 if(width<=650)assert.equal(c('.lc-day','height').value,'61px');else assert.equal(c('.lc-day','height').value,'158px');
 assert.equal(c('.lc-done','border').value,'0');
}
console.log('Calendar style: compact date buttons, distinct semantic surfaces, readable class metadata and mobile day heights: OK');
