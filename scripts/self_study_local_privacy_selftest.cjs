const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
async function run(owner,expected){
 const keys=['101:en-01','101:conversation:2:0','1010:en-01','-101:en-01','-1000000000101:en-01'],removed=[];let closed=false;
 const db={close(){closed=true;},transaction(){const tx={objectStore(){return{openCursor(){const req={};let i=0;function next(){queueMicrotask(()=>{if(i>=keys.length){req.result=null;req.onsuccess();queueMicrotask(()=>tx.oncomplete());return;}const key=keys[i++];req.result={key,delete(){removed.push(key);},continue:next};req.onsuccess();});}next();return req;}};}};return tx;}};
 const window={},indexedDB={open(){const req={};queueMicrotask(()=>{req.result=db;req.onsuccess();});return req;}};
 vm.runInNewContext(fs.readFileSync('web/self_study_voice.js','utf8'),{window,indexedDB,Promise,Set,Number,Error});
 await window.AdeliaStudyVoice.clearOwn(owner);assert.deepEqual(removed,expected);assert.equal(closed,true);
 await assert.rejects(()=>window.AdeliaStudyVoice.clearOwn('101'),/invalid_owner/);
}
(async()=>{await run(101,['101:en-01','101:conversation:2:0']);await run(-101,['-101:en-01']);await run(-1000000000101,['-1000000000101:en-01']);await run(999,[]);console.log('PASS: 4 local privacy scenarios; other accounts retained; invalid IDs rejected.');})().catch(e=>{console.error(e);process.exitCode=1;});
