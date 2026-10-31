'use strict';
const assert=require('node:assert/strict'),{EventEmitter}=require('events'),vm=require('vm'),fs=require('fs'),path=require('path');
let windows=[],choice=0,configured=[],loaded=[],closed=0;
class WC extends EventEmitter{setWindowOpenHandler(f){this.popup=f}}
class Window extends EventEmitter{constructor(options){super();this.options=options;this.webContents=new WC();windows.push(this)}isDestroyed(){return false}async loadURL(url){assert(configured.includes(this.webContents));loaded.push(url)}close(){this.emit('closed')}}
const result={exports:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'board_account.js'),'utf8'),{module:result,URL,require:n=>n==='electron'?{BrowserWindow:Window,dialog:{showMessageBox:async()=>({response:choice})}}:{configure:wc=>configured.push(wc)}});
const b=result.exports,board='https://app.moyadoska.com/board/123';
assert.equal(b.target(board),'https://app.moyadoska.com/');assert.equal(b.target('https://evil.example/'),null);
for(const u of ['https://oauth.yandex.ru/authorize','https://passport.yandex.ru/auth','https://id.vk.com/authorize','https://app.moyadoska.com/?code=example'])assert(b.allowed(u,board));
for(const u of ['http://app.moyadoska.com','https://app.moyadoska.com.evil.example','https://evil.example','javascript:alert(1)','https://id.vk.com.evil.example'])assert(!b.allowed(u,board));
assert(!b.allowed('https://oauth.yandex.ru/authorize','https://myboard.io/board/1'));
(async()=>{const parent={isDestroyed:()=>false};const win=await b.open(parent,board,()=>closed++);
assert.equal(win.options.webPreferences.partition,'persist:adelia-board');assert.equal(win.options.webPreferences.nodeIntegration,false);assert.equal(win.options.webPreferences.webSecurity,true);assert.equal(win.options.webPreferences.sandbox,true);assert.equal(loaded[0],'https://app.moyadoska.com/');
let blocked=false;win.webContents.emit('will-redirect',{preventDefault(){blocked=true}},'https://evil.example');assert(blocked);
blocked=false;win.webContents.emit('will-redirect',{preventDefault(){blocked=true}},'https://id.vk.com/authorize');assert(!blocked);
assert.equal(win.webContents.popup({url:'https://evil.example'}).action,'deny');
const allowed=win.webContents.popup({url:'https://oauth.yandex.ru/authorize'});assert.equal(allowed.action,'allow');assert.equal(allowed.overrideBrowserWindowOptions.webPreferences.partition,'persist:adelia-board');
win.close();assert.equal(closed,1);choice=1;assert.equal(await b.open(parent,board),null);assert.equal(windows.length,1);
console.log('Board account: persistent partition shared with board, provider redirects, malicious origins rejected, browser profile before load, close refresh callback and cancel: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
