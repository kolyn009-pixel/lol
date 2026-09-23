(()=>{'use strict';
if(window.__adeliaDesktopTeacherDensity)return;
window.__adeliaDesktopTeacherDensity=true;
const S=(el,prop,val)=>{try{el.style.setProperty(prop,val,'important')}catch(_){}};
function apply(){
  document.documentElement.dataset.adeliaDesktopDensity='v1';
  if(document.body)document.body.dataset.adeliaDesktopDensity='v1';

  const heroSel='.v4-page-head,.finance-head:not(.compact),.health-hero,.lesson-hero';
  document.querySelectorAll(heroSel).forEach(el=>{
    S(el,'background','linear-gradient(135deg,#242943,#343966)');S(el,'color','#fff');S(el,'border-color','rgba(255,255,255,.08)');
    el.querySelectorAll('h1,h2,h3,h4,b,strong').forEach(x=>{S(x,'color','#fff');S(x,'opacity','1');S(x,'text-shadow','none')});
    el.querySelectorAll('p,span,small,.muted,.sub,.meta').forEach(x=>{S(x,'color','rgba(255,255,255,.82)');S(x,'opacity','1')});
    el.querySelectorAll('.v4-kicker,.health-kicker,.badge').forEach(x=>{S(x,'color','#d9d4ff');S(x,'opacity','1')});
  });
  document.querySelectorAll('.panel,.row,.card,.v4-empty-state,.health-card,.health-panel,.health-google,.tb-card,.finance-overview-toolbar,.dashboard-panel').forEach(el=>{
    S(el,'color','#211d2a');
    el.querySelectorAll('h1,h2,h3,h4,b,strong').forEach(x=>S(x,'color','#211d2a'));
    el.querySelectorAll('p,small,.muted,.sub,.meta').forEach(x=>S(x,'color','#6f6878'));
  });

  document.querySelectorAll('.v4-page-head,.finance-head:not(.compact),.health-hero').forEach(el=>{
    S(el,'padding','10px 13px');S(el,'min-height','0');S(el,'margin','0 0 10px');S(el,'border-radius','14px');
    S(el,'display','flex');S(el,'align-items','center');S(el,'justify-content','space-between');S(el,'gap','12px');
  });
  document.querySelectorAll('.v4-page-head h1,.v4-page-head h2,.finance-head:not(.compact) h1,.finance-head:not(.compact) h2,.health-hero h1,.health-hero h2').forEach(el=>{
    S(el,'font-size','18px');S(el,'line-height','1.15');S(el,'margin','2px 0 3px');
  });
  document.querySelectorAll('.v4-page-head p,.finance-head:not(.compact) p,.health-hero p').forEach(el=>{
    S(el,'font-size','10px');S(el,'line-height','1.35');S(el,'margin','2px 0');
  });
  document.querySelectorAll('.v4-kicker,.health-kicker').forEach(el=>{S(el,'font-size','8px');S(el,'letter-spacing','.07em')});

  document.querySelectorAll('.v4-group-grid').forEach(el=>{if(el.querySelector('.v4-empty-state')){S(el,'display','block');S(el,'grid-template-columns','none')}});
  document.querySelectorAll('.v4-empty-state').forEach(el=>{
    S(el,'width','min(100%,520px)');S(el,'min-height','0');S(el,'padding','18px');S(el,'margin','0');S(el,'text-align','left');
  });
  document.querySelectorAll('.v4-empty-state .primary').forEach(el=>{
    S(el,'width','auto');S(el,'min-width','180px');S(el,'max-width','280px');S(el,'min-height','34px');S(el,'padding','7px 13px');
  });

  document.querySelectorAll('.finance-tabs,.payments-tabs').forEach(el=>S(el,'margin','0 0 9px'));
  document.querySelectorAll('.finance-tabs button,.payments-tabs button').forEach(el=>{S(el,'min-height','32px');S(el,'padding','5px 10px');S(el,'font-size','10px')});
  document.querySelectorAll('.finance-overview-toolbar').forEach(el=>S(el,'padding','10px 12px'));

  document.querySelectorAll('.health-grid').forEach(el=>S(el,'gap','8px'));
  document.querySelectorAll('.health-card').forEach(el=>{S(el,'min-height','66px');S(el,'padding','10px 12px')});

  document.querySelectorAll('.tb-grid').forEach(el=>S(el,'gap','10px'));
  document.querySelectorAll('.tb-card').forEach(el=>{S(el,'padding','10px 12px');S(el,'margin-bottom','8px')});
  document.querySelectorAll('.tb-card h3').forEach(el=>{S(el,'font-size','14px');S(el,'margin','4px 0')});
  document.querySelectorAll('.tb-card p').forEach(el=>{S(el,'font-size','10px');S(el,'margin','5px 0')});

  document.querySelectorAll('.msg-shell').forEach(el=>{S(el,'height','calc(100vh - 108px)');S(el,'min-height','540px')});
}
let queued=false;
function schedule(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;apply()})}
apply();
window.addEventListener('adelia:desktop-ui-ready',schedule);
document.addEventListener('click',e=>{if(e.target.closest('[data-view]'))setTimeout(apply,80)},true);
const root=document.querySelector('#app')||document.body;
if(root)new MutationObserver(schedule).observe(root,{childList:true,subtree:true});
})();