'use strict';
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');

const icon=path.join(__dirname,'build','icon.png');
const canonical=path.join(__dirname,'..','brand','adelia_icon','adelia-icon-512.png');
if(!fs.existsSync(icon)||!fs.existsSync(canonical)){
  console.error('Desktop build blocked: missing canonical Adelia icon.');
  process.exit(2);
}
const b=fs.readFileSync(icon), expected=fs.readFileSync(canonical);
const png=Buffer.from([137,80,78,71,13,10,26,10]);
if(b.length<64||!b.subarray(0,8).equals(png)||b.readUInt32BE(16)!==512||b.readUInt32BE(20)!==512){
  console.error('Desktop build blocked: desktop/build/icon.png is not a valid 512x512 PNG.');
  process.exit(3);
}
const digest=x=>crypto.createHash('sha256').update(x).digest('hex');
if(digest(b)!==digest(expected)){
  console.error('Desktop build blocked: build/icon.png differs from repository canonical Adelia icon.');
  process.exit(4);
}
console.log('Desktop icon check: PASS',digest(b).slice(0,12));
