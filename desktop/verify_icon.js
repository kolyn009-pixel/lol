'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const canonical=path.join(__dirname,'..','brand','adelia_icon','adelia-icon-512.png');
const build=path.join(__dirname,'build');
const digest=x=>crypto.createHash('sha256').update(x).digest('hex');
const source=fs.readFileSync(canonical),web=fs.readFileSync(path.join(build,'icon.png'));
if(digest(source)!==digest(web)){console.error('Desktop build blocked: stale canonical web icon');process.exit(3)}
const nativePng=fs.readFileSync(path.join(build,'icon-macos.png'));
if(nativePng.length<100||nativePng.subarray(0,8).toString('hex')!=='89504e470d0a1a0a'){console.error('Desktop build blocked: invalid transparent native PNG');process.exit(4)}
const icns=fs.readFileSync(path.join(build,'icon.icns')),ico=fs.readFileSync(path.join(build,'icon.ico'));
if(icns.toString('ascii',0,4)!=='icns'){console.error('Desktop build blocked: invalid ICNS');process.exit(5)}
if(!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0)){console.error('Desktop build blocked: invalid ICO');process.exit(6)}
console.log('Desktop generated native icon check: PASS icon.png, icon-macos.png, icon.icns, icon.ico');
