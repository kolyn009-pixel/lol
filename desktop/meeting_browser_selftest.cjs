'use strict';
const assert=require('node:assert/strict'),fs=require('fs'),vm=require('vm'),{EventEmitter}=require('events');
const {browserUserAgent,configure}=require('./meeting_browser');
const ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Adelia/0.3.1 Chrome/140.0.7339.41 Electron/38.0.0 Safari/537.36';
const clean=browserUserAgent(ua);assert(!clean.includes('Electron/'));assert(!clean.includes('Adelia/'));assert(clean.includes('Chrome/140.0.7339.41'));assert(clean.includes('Windows NT 10.0'));
const mac=ua.replace('Windows NT 10.0; Win64; x64','Macintosh; Intel Mac OS X 14_7_5');assert(browserUserAgent(mac).includes('Mac OS X 14_7_5'));assert.equal(browserUserAgent(clean),clean);
let set;configure({getUserAgent:()=>ua,setUserAgent:v=>set=v});assert.equal(set,clean);
// Verify real room code applies compatibility before navigating, keeps board UA,
// shares its original auth partition and does not touch storage/permissions.
let views=[],actions=new Map(),external=[],configured=[];
class WC extends EventEmitter{getUserAgent(){return ua}setUserAgent(v){this.ua=v;configured.push(this)}setWindowOpenHandler(f){this.popup=f}async loadURL(url){assert(this.ua||url.includes('moyadoska'));this.url=url}isDestroyed(){return false}async executeJavaScript(){}async insertCSS(){return 'css'}async removeInsertedCSS(){}close(){}reloadIgnoringCache(){this.reloaded=true}}
class View{constructor(options){this.options=options;this.webContents=new WC();views.push(this)}setBounds(){}setVisible(){}}
class Window extends EventEmitter{constructor(options){super();this.options=options;this.webContents=new WC()}async loadURL(u){return this.webContents.loadURL(u)}isDestroyed(){return false}close(){this.emit('closed')}}
let choice=0;const moduleObj={exports:{}};
const electron={WebContentsView:View,BrowserWindow:Window,ipcMain:{handle:(k,f)=>actions.set(k,f)},shell:{openExternal:async u=>external.push(u)},dialog:{showMessageBox:async()=>({response:choice})}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'lesson_room.js'),'utf8'),{require:n=>n==='electron'?electron:n==='./meeting_browser'?require('./meeting_browser'):null,module:moduleObj,URL,console});
const win=new EventEmitter();win.webContents=new WC();win.contentView={addChildView(){},removeChildView(){}};win.isDestroyed=()=>false;win.getContentSize=()=>[1440,900];
const trusted=u=>{try{return new URL(u).origin==='https://telemost.yandex.ru'}catch{return false}};
(async()=>{const room=moduleObj.exports.create(win,{trustedMeeting:trusted,trustedBoard:u=>u.startsWith('https://app.moyadoska.com/')});
await room.open('meeting','https://telemost.yandex.ru/j/123');assert.equal(views[0].webContents.ua,clean);assert.equal(views[0].options.webPreferences.partition,'persist:adelia-lesson');
await room.open('board','https://app.moyadoska.com/board/123');assert.equal(views[1].webContents.ua,undefined);
await room.reloadMeeting();assert.equal(views[0].webContents.reloaded,true);
await room.externalMeeting();assert.deepEqual(external,['https://telemost.yandex.ru/j/123']);
choice=1;views[0].webContents.reloaded=false;await room.reloadMeeting();assert.equal(views[0].webContents.reloaded,false);
assert.equal(await room.open('meeting','https://evil.example'),false);
console.log('Meeting compatibility: original Chromium/OS retained, browser UA before load, board unchanged, room reload/external confirmations and trusted URL guard: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
