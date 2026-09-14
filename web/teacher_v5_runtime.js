(()=>{'use strict';
const MAP={PHYSICS:'Физика',CHEMISTRY:'Химия',MATH:'Математика',SCHOOL:'Школьная программа',OGE:'ОГЭ',EGE:'ЕГЭ',OLYMPIAD:'Олимпиада',CONFIRMED:'Подтверждено',AWAITING_PAYMENT:'Ожидает оплаты',PAID:'Оплачено',NEW:'Новая',EXPIRED:'Завершено',OPEN:'Открыт набор',WAITLIST:'Лист ожидания',CLOSED:'Набор закрыт'};
window.AdeliaStatusText=v=>MAP[String(v||'').trim().toUpperCase()]||v;
function humanize(root=document){
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
  nodes.forEach(n=>{const p=n.parentElement;if(!p||['SCRIPT','STYLE','TEXTAREA','INPUT','OPTION'].includes(p.tagName))return;let s=n.nodeValue;if(!s||!s.trim())return;
    Object.entries(MAP).forEach(([k,v])=>{s=s.replace(new RegExp('\\b'+k+'\\b','g'),v)});
    s=s.replace(/\bStage\s*\d+\b/gi,'').replace(/\s+·\s+·/g,' · ');if(s!==n.nodeValue)n.nodeValue=s;
  });
  root.querySelectorAll?.('.badge,.chip,.status,.v4-chip').forEach(el=>{const t=String(el.textContent||'').trim().toUpperCase();if(MAP[t])el.textContent=MAP[t]});
}
function decorateEmpty(root=document){root.querySelectorAll?.('.empty').forEach(el=>{if(el.dataset.v5done)return;el.dataset.v5done='1';const text=(el.textContent||'').trim();if(!text)return;el.classList.add('v5-empty');});}
function polish(root=document){humanize(root);decorateEmpty(root);}
let queued=false;const schedule=()=>{if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;polish(document.querySelector('#app')||document)});};
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
document.addEventListener('DOMContentLoaded',()=>polish());schedule();
})();