'use strict';
const fs=require('fs'),path=require('path'),manifest=require('./bundled_ui_manifest');
const src=path.resolve(__dirname,'..','web'),dst=path.join(__dirname,'bundled_web');
fs.rmSync(dst,{recursive:true,force:true});fs.mkdirSync(dst,{recursive:true});
const names=[...new Set(Object.values(manifest).flatMap(x=>[...x.css,...x.js]))];
for(const name of names){const from=path.join(src,name);if(!fs.existsSync(from))throw new Error('Missing desktop UI asset: '+name);fs.copyFileSync(from,path.join(dst,name));}
console.log('Synced desktop UI assets:',names.length);
