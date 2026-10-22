'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const root=path.join(__dirname,'..'),canonical=path.join(root,'brand','adelia_icon','adelia-icon-512.png'),build=path.join(__dirname,'build'),webIcons=path.join(root,'web','assets','icons');
const digest=x=>crypto.createHash('sha256').update(x).digest('hex');
const pngSize=b=>b.length>24&&b.subarray(0,8).toString('hex')==='89504e470d0a1a0a'?[b.readUInt32BE(16),b.readUInt32BE(20)]:null;
const source=fs.readFileSync(canonical),desktop=fs.readFileSync(path.join(build,'icon.png'));
if(digest(source)!==digest(desktop)){console.error('Desktop build blocked: stale canonical icon.png');process.exit(3)}
for(const size of [32,180,192,256,512]){const b=fs.readFileSync(path.join(webIcons,`adelia-icon-${size}.png`)),dims=pngSize(b);if(!dims||dims[0]!==size||dims[1]!==size){console.error(`Desktop build blocked: invalid Web/PWA icon ${size}x${size}`);process.exit(7)}if(size===512&&digest(b)!==digest(source)){console.error('Desktop build blocked: Web/PWA 512 icon differs from canonical icon');process.exit(8)}}
const nativePng=fs.readFileSync(path.join(build,'icon-macos.png')),nativeDims=pngSize(nativePng);if(!nativeDims||nativeDims[0]!==1024||nativeDims[1]!==1024){console.error('Desktop build blocked: invalid 1024x1024 native PNG');process.exit(4)}
const icns=fs.readFileSync(path.join(build,'icon.icns')),ico=fs.readFileSync(path.join(build,'icon.ico'));
if(icns.toString('ascii',0,4)!=='icns'){console.error('Desktop build blocked: invalid ICNS');process.exit(5)}
if(!(ico[0]===0&&ico[1]===0&&ico[2]===1&&ico[3]===0)){console.error('Desktop build blocked: invalid ICO');process.exit(6)}
const versions=['20260925-brand4','20261022-unified2'],textFiles=['web/index.html','web/parent/index.html','web/teacher.html','web/manifest.webmanifest','web/parent/manifest.webmanifest','web/teacher-manifest.webmanifest'];
for(const rel of textFiles){const s=fs.readFileSync(path.join(root,rel),'utf8');if(!versions.some(version=>s.includes(version))){console.error(`Desktop build blocked: stale icon cache-buster in ${rel}`);process.exit(9)}if(!/\/app\/assets\/icons\/adelia-(icon|mark)-/.test(s)){console.error(`Desktop build blocked: icon URL outside published /app namespace in ${rel}`);process.exit(10)}if(/adelia-icon\.svg/.test(s)){console.error(`Desktop build blocked: legacy SVG icon reference in ${rel}`);process.exit(10)}}
for(const legacy of ['brand/adelia_icon/adelia-icon-macos-1024.png','brand/adelia_icon/adelia-icon-macos.icns','brand/adelia_icon/adelia-icon-windows.ico','web/adelia-icon.svg','web/assets/icons/adelia-icon.svg']){if(fs.existsSync(path.join(root,legacy))){console.error(`Desktop build blocked: legacy icon copy still exists: ${legacy}`);process.exit(11)}}
console.log('Canonical Adelia icon guard: PASS single source, Desktop, Web/PWA, manifests and cache-buster');

