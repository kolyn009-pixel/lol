(()=>{
 'use strict';
 if(!document.querySelector('.teacher-shell'))return;
 function learningTabs(){
  const panel=document.querySelector('#learningHubPanel'),grid=panel?.querySelector('.lh-grid');
  if(!grid||panel.querySelector('[role=tablist],.lh-tabs'))return;
  const sections=[...grid.children].filter(x=>x.classList.contains('lh-section'));
  if(sections.length<2)return;
  const tabs=document.createElement('div');tabs.className='lh-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Разделы учебного плана');
  const select=i=>{sections.forEach((s,n)=>{s.hidden=n!==i;const b=tabs.children[n];b.setAttribute('aria-selected',String(n===i));b.tabIndex=n===i?0:-1;});};
  sections.forEach((s,i)=>{const b=document.createElement('button');b.type='button';b.textContent=s.querySelector('h3')?.textContent||'Раздел';b.id='lh-tab-'+i;s.id='lh-section-'+i;s.setAttribute('role','tabpanel');s.setAttribute('aria-labelledby',b.id);b.setAttribute('role','tab');b.setAttribute('aria-controls',s.id);b.onclick=()=>select(i);b.onkeydown=e=>{let next;if(e.key==='ArrowRight')next=(i+1)%sections.length;if(e.key==='ArrowLeft')next=(i+sections.length-1)%sections.length;if(e.key==='Home')next=0;if(e.key==='End')next=sections.length-1;if(next!==undefined){e.preventDefault();select(next);tabs.children[next].focus();}};tabs.append(b);});
  grid.before(tabs);select(0);
 }
 function shortcuts(){
  if(!document.querySelector('nav [data-view=messages]'))return;
  document.querySelectorAll('button,a').forEach(el=>{
   if(el.closest('.teacher-shell>aside,#learningHubOverlay')||el.classList.contains('teacher-message-shortcut')||el.textContent.trim()!=='Сообщения')return;
   let node=el;for(let i=0;node&&node!==document.body&&i<3;i++,node=node.parentElement){if(getComputedStyle(node).position==='fixed'){el.classList.add('teacher-message-shortcut');break;}}
  });
 }
 let pending=false;
 function update(){if(pending)return;pending=true;requestAnimationFrame(()=>{pending=false;learningTabs();shortcuts();});}
 new MutationObserver(update).observe(document.body,{childList:true,subtree:true});update();
})();
