const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict'),path=require('path');let parseHTML;try{({parseHTML}=require('../desktop/node_modules/linkedom'))}catch{({parseHTML}=require('../qa-deps/node_modules/linkedom'))}
const {window,document}=parseHTML('<html><body><div class="teacher-shell"><aside><nav><button data-view="schedule">Расписание</button></nav></aside><main><h1 id="title"></h1><div id="app"></div></main></div></body></html>');
// linkedom deliberately lacks browser select.value setter.
const proto=window.HTMLSelectElement.prototype;Object.defineProperty(proto,'value',{get(){return this.querySelector('option[selected]')?.getAttribute('value')||this.querySelector('option')?.getAttribute('value')||''},set(v){this.querySelectorAll('option').forEach(o=>o.toggleAttribute('selected',o.getAttribute('value')===String(v)))},configurable:true});
const NativeDate=Date;class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:['2026-10-30T09:00:00Z']))}static now(){return +new FixedDate()}}
const instant=s=>new NativeDate(/[Zz]|[+-]\d\d:\d\d$/.test(s)?s:s+'+03:00');const dateKey=s=>{const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(instant(s));const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return p.year+'-'+p.month+'-'+p.day};
window.TeacherTime={ready:async()=>{},preference:{zone:'Europe/Moscow'},label:()=> 'Москва',dateKey,instant,schedule:(s,o)=>new Intl.DateTimeFormat('ru-RU',{...o,timeZone:'Europe/Moscow'}).format(instant(s))};
let data=[{id:1,name:'Иван <script>',grade:10,subject:'PHYSICS',start_time:'2026-10-30T16:30:00',end_time:'2026-10-30T17:30:00',lesson_status:'CONFIRMED',payment_status:'PAID'},{id:2,name:'Мария',grade:11,subject:'CHEMISTRY',rescheduled:true,start_time:'2026-10-30T21:30:00Z',end_time:'2026-10-30T22:30:00Z',lesson_status:'CONFIRMED',payment_status:'PAID'},{id:'group-3',group_id:9,kind:'GROUP',name:'Группа ЕГЭ',subject:'PHYSICS',start_time:'2026-10-30T18:00:00',end_time:'2026-10-30T19:00:00',lesson_status:'SCHEDULED'},{id:4,name:'Отменённый',start_time:'2026-10-30T10:00:00',end_time:'2026-10-30T11:00:00',lesson_status:'CANCELLED'}];
let opened=[],groups=[],settings=0,calls=[],waiter=null;window.lesson=id=>opened.push(id);window.AdeliaGroupSettings={open:id=>groups.push(id)};window.teacherWorkingHours=()=>settings++;
const ctx={window,document,MutationObserver:class{observe(){}},matchMedia:()=>({matches:false}),Intl,Date:FixedDate,URLSearchParams,AbortController,setTimeout:()=>0,clearTimeout(){},fetch:async url=>{calls.push(url);if(waiter)await waiter;return {ok:true,json:async()=>({calendar_items:data,items:[]})}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/lesson_calendar.js'),'utf8'),ctx);
(async()=>{const m=window.AdeliaLessonCalendar.model;
assert.equal(m.add('2024-02-28',1),'2024-02-29');assert.equal(m.add('2024-02-29',1),'2024-03-01');assert.equal(m.month('2026-01-31',-1),'2025-12-01');assert.equal(m.monday('2027-01-03'),'2026-12-28');
assert.deepEqual(JSON.parse(JSON.stringify(m.bounds('2026-10-30','month'))),{start:'2026-09-28',end:'2026-11-02'});
await window.AdeliaLessonCalendar.open();assert(document.querySelector('.lc-app'));assert(calls[0].includes('limit=500'));assert(!document.querySelector('[data-lc-event="4"]'));assert(!document.querySelector('script'));assert(document.querySelector('[data-lc-event="1"]').getAttribute('aria-label').includes('10 класс'));
assert(document.querySelector('.lc-compact .lc-event-time').textContent.includes('16:30–17:30'));
assert(document.querySelector('.lc-compact .lc-event-main small').textContent.includes('10 класс'));
assert(document.querySelector('.lc-legend').textContent.includes('Перенесено'));
assert.equal(document.querySelector('.lc-selected-day h3 span').textContent,'2');
assert.equal(document.querySelector('[data-lc-day="2026-10-30"] .lc-date-disc').textContent,'30');
assert.equal(document.querySelector('[data-lc-day="2026-10-30"]').getAttribute('aria-current'),'date');
document.querySelector('[data-lc-cell="2026-10-29"]').click();
assert(document.querySelector('.lc-selected [data-lc-day="2026-10-29"]'));
document.querySelector('[data-lc-day="2026-10-30"]').click();
// The UTC event at 21:30 belongs to October 31 in Moscow, not October 30.
assert(document.querySelector('.lc-day.lc-selected [data-lc-day="2026-10-30"]'));document.querySelector('[data-lc-event="1"]').click();assert.deepEqual(opened,[1]);document.querySelector('[data-lc-event="group-3"]').click();assert.deepEqual(groups,[9]);
document.querySelector('[data-lc-day="2026-10-31"]').click();assert(document.querySelector('.lc-selected-day [data-lc-event="2"]'));
const filter=document.querySelector('select[aria-label="Статус занятия"]');filter.value='CANCELLED';filter.onchange({target:filter});assert(document.querySelector('[data-lc-event="4"]'));assert(!document.querySelector('[data-lc-event="1"]'));
filter.value='RESCHEDULED';filter.onchange({target:filter});assert(document.querySelector('[data-lc-event="2"]'));assert(!document.querySelector('[data-lc-event="1"]'));
document.querySelector('[data-lc-settings]').click();assert.equal(settings,1);
// A crowded month cell stays compact; the selected-day panel retains all events.
filter.value='';filter.onchange({target:filter});
data=[...data,...[10,11,12].map(id=>({...data[0],id,name:'Дополнительный '+id}))];
await window.AdeliaLessonCalendar.open();
assert.equal(document.querySelector('.lc-selected .lc-day-events').querySelectorAll('[data-lc-event]').length,2);
assert.equal(document.querySelector('.lc-selected .lc-more').textContent,'＋ ещё 3');
assert.equal(document.querySelector('.lc-selected-day').querySelectorAll('[data-lc-event]').length,5);
assert(document.querySelector('.lc-month-layout > .lc-selected-day'));
// A slow fetch must not replace another screen after navigation.
let resolve;waiter=new Promise(r=>resolve=r);const pending=window.AdeliaLessonCalendar.open();await Promise.resolve();document.querySelector('#app').innerHTML='<div id="another">Другой раздел</div>';resolve();await pending;assert(document.querySelector('#another'));
console.log('Lesson calendar: leap/year boundaries, Monday month grid, Moscow midnight, escaping, status filters, existing lesson/group/settings actions and stale fetch guard: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
