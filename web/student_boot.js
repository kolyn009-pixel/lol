(()=>{
'use strict';
const modules=[
 'student_messenger_v2.js','student_homework_plus.js','student_formulas.js','student_self_service.js',
 'student_vacation.js','student_cascade.js','student_booking.js','student_finance.js',
 'student_finance_live.js','student_events.js','student_group_space.js'
];
let started=false;
function load(src){return new Promise(resolve=>{const s=document.createElement('script');s.src='/app/'+src+'?v=20261022-group-media1';s.async=true;s.onload=resolve;s.onerror=resolve;document.body.append(s)})}
async function boot(){
 if(started)return;
 try{
  const ctrl=new AbortController(),timer=setTimeout(()=>ctrl.abort(),8000);
  let r;try{r=await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store',signal:ctrl.signal})}finally{clearTimeout(timer)}
  const d=await r.json().catch(()=>({}));
  if(!d.authenticated||d.session?.role!=='student')return;
  started=true;
  // Profile onboarding owns the first authenticated screen. Load it first so
  // other feature modules cannot race it, then fetch independent modules in parallel.
  await load('registration_profile.js');
  await Promise.all(modules.map(load));
 }catch{}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,0));else setTimeout(boot,0);
window.addEventListener('adelia:student-authenticated',boot);
})();

