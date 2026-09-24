'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto');
const pairs=[
 ['icon.png','adelia-icon-512.png'],
 ['icon.icns','adelia-icon-macos.icns'],
 ['icon.ico','adelia-icon-windows.ico'],
 ['icon-macos.png','adelia-icon-macos-1024.png']
];
const digest=x=>crypto.createHash('sha256').update(x).digest('hex');
for(const [built,canonical] of pairs){
 const a=path.join(__dirname,'build',built),b=path.join(__dirname,'..','brand','adelia_icon',canonical);
 if(!fs.existsSync(a)||!fs.existsSync(b)){console.error('Desktop build blocked: missing icon asset',built);process.exit(2)}
 const av=fs.readFileSync(a),bv=fs.readFileSync(b);
 if(digest(av)!==digest(bv)){console.error('Desktop build blocked: stale icon asset',built);process.exit(3)}
}
console.log('Desktop native icon check: PASS',pairs.map(x=>x[0]).join(', '));
