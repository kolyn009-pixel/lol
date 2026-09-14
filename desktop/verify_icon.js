'use strict';
const fs=require('fs');
const path=require('path');

const icon=path.join(__dirname,'build','icon.png');
if(!fs.existsSync(icon)){
  console.error('Desktop build blocked: missing canonical Adelia icon at '+icon);
  console.error('Copy the approved server icon into desktop/build/icon.png before building.');
  process.exit(2);
}
const b=fs.readFileSync(icon);
const png=Buffer.from([137,80,78,71,13,10,26,10]);
if(b.length<64||!b.subarray(0,8).equals(png)){
  console.error('Desktop build blocked: desktop/build/icon.png is not a valid PNG.');
  process.exit(3);
}
console.log('Desktop icon check: PASS');
