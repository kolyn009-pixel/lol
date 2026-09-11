(()=>{
'use strict';
const modules=[
 'registration_profile.js','student_chat.js','student_homework_plus.js','student_formulas.js',
 'student_self_service.js','student_vacation.js','student_cascade.js','student_booking.js',
 'student_finance.js','student_finance_live.js','student_events.js','student_group_space.js'
];
let started=false;
function load(src){return new Promise(resolve=>{const s=document.createElement('script');s.src='/app/'+src+'?v=20260911b';s.defer=true;s.onload=resolve;s.onerror=resolve;document.body.append(s)})}
async function boot(){
 if(started)return;
 try{
  const r=await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store'});
  const d=await r.json().catch(()=>({}));
  if(!d.authenticated||d.session?.role!=='student')return;
  started=true;
  for(const src of modules)await load(src);
 }catch{}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,0));else setTimeout(boot,0);
window.addEventListener('adelia:student-authenticated',boot);
})();
