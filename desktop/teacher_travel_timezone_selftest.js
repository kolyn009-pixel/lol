'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
let selected='Europe/Moscow',scheduleZone='Europe/Moscow';
const window={addEventListener(){},dispatchEvent(){}},document={querySelector(){return null;},addEventListener(){}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'..','web','teacher_time.js'),'utf8'),{
 window,document,Intl,Date,Event,setInterval(){},fetch:async(url,options)=>{
  if(options?.method==='POST')selected=JSON.parse(options.body).zone;
  return {ok:true,json:async()=>({timezone:{zone:selected==='schedule'?scheduleZone:selected,schedule_zone:scheduleZone,selected:selected!=='schedule'}})};
 }
});
(async()=>{
 const time=window.TeacherTime,options={hour:'2-digit',minute:'2-digit',hourCycle:'h23'};
 await time.load();
 const raw='2026-10-01T19:00:00',timestamp='2026-10-01T16:00:00.000Z';
 for(const [zone,expected,day] of [
  ['Europe/Moscow','19:00','2026-10-01'],['Europe/Samara','20:00','2026-10-01'],
  ['Asia/Dubai','20:00','2026-10-01'],['Asia/Bangkok','23:00','2026-10-01'],
  ['Asia/Makassar','00:00','2026-10-02'],['Indian/Maldives','21:00','2026-10-01']]){
  await time.save(zone);
  assert.equal(time.instant(raw).toISOString(),timestamp);
  assert.equal(time.schedule(raw,options),expected);
  assert.equal(time.dateKey(raw),day);
  assert.equal(time.scheduleInput(raw),'2026-10-01T19:00');
 }
 await time.save('Asia/Bangkok');
 assert.equal(time.dateKey('2026-10-01T23:30:00+03:00'),'2026-10-02');
 await time.save('schedule');assert.equal(time.schedule(raw,options),'19:00');
 scheduleZone='Europe/Berlin';await time.load();
 assert.equal(time.instant('2026-03-29T02:30:00'),null,'DST gap is not silently shifted');
 assert.equal(time.instant('2026-10-25T02:30:00').toISOString(),'2026-10-25T00:30:00.000Z','legacy DST fold chooses earlier instant');
 assert.equal(time.instant('2026-02-31T12:00:00'),null);
 console.log('TEACHER_TRAVEL_TIMEZONE=PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
