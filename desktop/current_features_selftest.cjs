'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const manifest=require('./bundled_ui_manifest'),repo=path.resolve(__dirname,'..');
for(const [role,assets] of Object.entries(manifest)){
 assert(assets.css.includes('learning_hub.css'),role+' learning styles missing');
 assert(assets.js.includes('learning_hub.js'),role+' learning workspace missing');
 for(const name of [...assets.css,...assets.js])assert(fs.existsSync(path.join(repo,'web',name)),name+' missing');
}
assert(manifest.student.js.indexOf('student_messenger_v2.js')<manifest.student.js.indexOf('student_stage4_workspace.js'));
const source=fs.readFileSync(path.join(repo,'web/student_stage4_workspace.js'),'utf8');
const content={innerHTML:'',querySelectorAll(){return []},querySelector(){return null}},title={textContent:''};let mounted=0,stopped=0;
const window={adeliaDesktop:{desktop:true},addEventListener(){},AdeliaStudentMessenger:{stop(){stopped++},screen:async()=>'<div>Current chat with attachments and receipts</div>',mount(){mounted++}}};
const document={body:{dataset:{}},querySelector(s){return s==='#content'?content:s==='#pageTitle'?title:null},querySelectorAll(){return []}};
const context={window,document,Intl,Date,console,fetch:async()=>({ok:true,json:async()=>({name:'Ученик',items:[]})})};
vm.runInNewContext(source,context);const first=window.StudentStage4;vm.runInNewContext(source,context);assert.equal(window.StudentStage4,first);
(async()=>{await first.messages();assert.match(content.innerHTML,/Current chat/);assert.equal(mounted,1);assert.equal(stopped,1);await first.profile();assert.match(content.innerHTML,/data-learning-open/);assert.equal(stopped,2);console.log('DESKTOP_CURRENT_FEATURES=PASS: all roles, current chat, draft lifecycle, learning entry, single registration');})().catch(e=>{console.error(e);process.exitCode=1;});
