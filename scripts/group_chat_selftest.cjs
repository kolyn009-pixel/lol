const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
let nodes={},items=[],requests=[],intervals=[],failure=false,pending=null;
const content={isConnected:true,querySelector(s){return nodes[s]||null},querySelectorAll(){return []},set innerHTML(value){Object.values(nodes).forEach(x=>x.isConnected=false);nodes={'.empty':{isConnected:true}};for(const match of value.matchAll(/id="([^"]+)"/g))nodes['#'+match[1]]={value:'',textContent:'',innerHTML:'',isConnected:true,dataset:{},disabled:false,scrollHeight:200,scrollTop:200,clientHeight:100};},get innerHTML(){return ''}};
const title={textContent:''};
const context={AbortController,setTimeout,clearTimeout,console,document:{hidden:false,body:{},querySelector(s){return s==='#content'?content:s==='#pageTitle'?title:null}},window:{},MutationObserver:class{observe(){}},setInterval(fn){intervals.push(fn);return intervals.length},clearInterval(){},fetch:async(url,opt={})=>{requests.push([url,opt]);if(url.includes('/presence'))return {ok:true,json:async()=>({})};if(url.includes('/summary'))return {ok:true,json:async()=>({group:{name:'Физика'},upcoming_lessons:[]})};if(url.includes('/members'))return {ok:true,json:async()=>({items:[]})};if(opt.method==='POST'){if(pending)await pending;if(failure)return {ok:false,json:async()=>({error:'group_chat_read_only'})};items.push({body:JSON.parse(opt.body).body,mine:true});return {ok:true,json:async()=>({status:'ok'})};}return {ok:true,json:async()=>({items:items.slice()})};}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/student_group_space.js'),'utf8'),context);
(async()=>{
 await context.window.AdeliaGroupSpace.openGroup(1);let ta=nodes['#groupMessage'];ta.value='Черновик';ta.oninput();
 items.push({body:'Новое сообщение',sender_name:'Ученик'});await intervals.at(-1)();assert.match(nodes['#groupChat'].innerHTML,/Новое сообщение/);assert.equal(ta.value,'Черновик');
 failure=true;await nodes['#groupSend'].onclick();assert.equal(ta.value,'Черновик');assert.match(nodes['#groupChatStatus'].textContent,/публикует преподаватель/);assert.equal(nodes['#groupSend'].disabled,false);
 await context.window.AdeliaGroupSpace.openGroup(2);assert.equal(nodes['#groupMessage'].value,'');await context.window.AdeliaGroupSpace.openGroup(1);assert.equal(nodes['#groupMessage'].value,'Черновик');
 failure=false;let resolve;pending=new Promise(r=>resolve=r);const button=nodes['#groupSend'],sending=button.onclick();await button.onclick();assert.equal(requests.filter(x=>x[1].method==='POST'&&!x[0].includes('presence')).length,2);resolve();await sending;pending=null;
 assert.equal(nodes['#groupMessage'].value,'');assert.match(nodes['#groupChat'].innerHTML,/Черновик/);assert.equal(button.disabled,false);
 await context.window.AdeliaGroupSpace.openGroup(1);assert.equal(nodes['#groupMessage'].value,'');
 console.log('GROUP_CHAT=PASS: live updates, draft isolation, failed retry, duplicate prevention, successful clear');
})().catch(e=>{console.error(e);process.exitCode=1;});
