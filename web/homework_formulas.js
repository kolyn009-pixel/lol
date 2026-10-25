(()=>{'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const norm=s=>String(s||'').toLowerCase().replace(/ё/g,'е');
const rules=[[/термодинамик|теплов[а-я]* машин|теплоемк|количеств[а-я]* теплот|перв[а-я]* начал/,'Термодинамика'],[/идеальн[а-я]* газ|молекулярн|газов[а-я]* закон/,'Молекулярная физика'],[/оптик|линз|преломлен|отражен[а-я]* свет/,'Оптика'],[/электростат|кулон/,'Электростатика'],[/постоянн[а-я]* ток|закон[а-я]* ома/,'Постоянный ток'],[/колебан|волн/,'Колебания и волны']];
function sections(text,items){const t=norm(text),out=new Set();for(const [re,label] of rules)if(re.test(t))out.add(label);for(const x of items){for(const name of [x.section,x.topic])if(name&&name.length>5&&t.includes(norm(name)))out.add(name);}return out;}
function matching(payload,items){const h=payload.homework||{},text=[h.title,h.description,...(payload.tasks||[]).flatMap(t=>[t.topic,t.section,t.title])].join(' '),keys=sections(text,items);return items.filter(x=>(!h.subject||x.subject===h.subject)&&(keys.has(x.section)||keys.has(x.topic)));}
async function catalog(){const r=await fetch('/api/student/formulas?limit=500&education_level=SCHOOL&level=0',{credentials:'same-origin'});if(!r.ok)throw Error('catalog');return (await r.json()).items||[];}
async function attach(id,payload,root){
 const anchor=root.querySelector('.student-hw-head');if(!anchor)return;
 const slot=document.createElement('section');slot.className='hw-formula-kit';slot.dataset.homework=String(id);slot.hidden=true;anchor.after(slot);
 try{const items=matching(payload,await catalog());if(!slot.isConnected||!root.querySelector('#studentHwBack')||!items.length)return;
 slot.hidden=false;slot.innerHTML='<div class="hw-formula-kit-head"><div><span>Подсказки к заданию</span><h3>Формулы по теме</h3><p>'+E([...new Set(items.map(x=>x.section))].join(' · '))+' · '+items.length+' формул</p></div></div><details><summary>Открыть формулы</summary><div class="hw-formula-grid">'+items.map(x=>'<article><h4>'+E(x.title)+'</h4><div class="hw-formula-math" data-fx-math="'+E(x.formula_latex)+'">'+E(x.formula_plain||x.formula_latex)+'</div><p>'+E(x.conditions||x.description)+'</p></article>').join('')+'</div></details>';
 await typeset(slot);
 }catch{if(slot.isConnected){slot.hidden=false;slot.innerHTML='<p>Не удалось загрузить формулы к заданию.</p><button type="button">Повторить</button>';slot.querySelector('button').onclick=()=>{slot.remove();attach(id,payload,root);};}}
}
let renderer;
async function typeset(root){if(!window.katex){if(!renderer)renderer=new Promise(resolve=>{const s=document.createElement('script');s.src='/app/vendor/katex.min.js?v=0.16.11';s.onload=()=>resolve(true);s.onerror=()=>{renderer=null;resolve(false)};document.head.append(s);});if(!await renderer)return;}if(!root.isConnected)return;root.querySelectorAll('[data-fx-math]').forEach(el=>{try{window.katex.render(el.dataset.fxMath,el,{output:'mathml',displayMode:true,throwOnError:true,trust:false,maxExpand:1000})}catch{}});}
function preview(){const title=document.querySelector('#hwTitle'),description=document.querySelector('#hwDescription');if(!title||!description||document.querySelector('#hwFormulaHint'))return;const hint=document.createElement('p');hint.id='hwFormulaHint';hint.className='hw-formula-hint';description.after(hint);const update=()=>{const labels=sections(title.value+' '+description.value,[]);hint.textContent=labels.size?'К этому ДЗ автоматически появятся формулы: '+[...labels].join(', ')+'.':'Укажите тему в названии или инструкции, например «Термодинамика»: ученик увидит соответствующие формулы рядом с ДЗ.';};title.addEventListener('input',update);description.addEventListener('input',update);update();}
if(document.querySelector('.teacher-shell')){new MutationObserver(preview).observe(document.querySelector('#app'),{childList:true,subtree:true});preview();}
window.AdeliaHomeworkFormulas={attach,matching};
})();
