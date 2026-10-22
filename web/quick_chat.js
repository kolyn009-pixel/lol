(()=>{'use strict';
let role='',visible=true,started=false;
const app=document.querySelector('#app');
const notify=type=>{if(parent!==window)parent.postMessage({type},location.origin)};
function script(src){return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=src;s.onload=resolve;s.onerror=reject;document.head.append(s)})}
async function boot(){
 try{
  const r=await fetch('/api/auth/me',{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(10000)});if(!r.ok)throw new Error('auth');const me=await r.json();if(!me.authenticated||!me.session)throw new Error('auth');role=String(me.session.role||'').toLowerCase();
  // Bound requests so a stalled service cannot leave the composer loading forever.
  const nativeFetch=window.fetch.bind(window);window.fetch=(input,init={})=>nativeFetch(input,{...init,signal:init.signal||AbortSignal.timeout(12000)});
  if(role==='teacher'){await script('/app/teacher_messages_stage10.js?v=20261022-workspace3');await window.teacherMessages()}
  else if(role==='student'){await script('/app/student_time.js');await script('/app/student_messenger_v2.js?v=20261022-workspace3');app.innerHTML=await window.AdeliaStudentMessenger.screen();window.AdeliaStudentMessenger.mount()}
  else throw new Error('role');
  started=true;notify('adelia:chat-ready');if(!visible)pause();
 }catch{app.replaceChildren();const box=document.createElement('section');box.className='error';box.textContent='Не удалось загрузить сообщения. Проверьте соединение и вход в кабинет.';const retry=document.createElement('button');retry.textContent='Повторить';retry.onclick=()=>location.reload();box.append(document.createElement('br'),retry);app.append(box);notify('adelia:chat-error')}
}
function pause(){if(role==='teacher')window.AdeliaTeacherMessenger?.pause();else window.AdeliaStudentMessenger?.stop()}
async function resume(){if(role==='teacher')await window.teacherMessages();else{window.AdeliaStudentMessenger?.mount();await window.AdeliaStudentMessenger?.refresh()}}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent||e.data?.type!=='adelia:chat-visibility'||typeof e.data.visible!=='boolean')return;const changed=visible!==e.data.visible;visible=e.data.visible;if(!started||!changed)return;if(visible)resume().catch(()=>notify('adelia:chat-error'));else pause()});
boot();
})();
