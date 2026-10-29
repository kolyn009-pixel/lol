/* Actual workshop module, simulated browser speech API; no microphone/provider. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function fixture(voices){const utterances=[],statuses=[];let cancelled=0;const window={speechSynthesis:{getVoices:()=>voices,speak:u=>utterances.push(u),cancel:()=>cancelled++},SpeechSynthesisUtterance:class {constructor(text){this.text=text;}}};vm.runInNewContext(fs.readFileSync('web/self_study_workshop.js','utf8'),{window,SpeechSynthesisUtterance:window.SpeechSynthesisUtterance});return {app:window.AdeliaStudyWorkshop,utterances,statuses,cancelled:()=>cancelled};}
{
 const f=fixture([{lang:'en-GB',name:'English'},{lang:'de-DE',name:'Deutsch'}]);assert.equal(f.app.speak('Guten Tag','de',.75,t=>f.statuses.push(t)),true);assert.equal(f.utterances[0].voice.lang,'de-DE');assert.equal(f.utterances[0].rate,.75);f.app.stopSpeech();assert.equal(f.cancelled(),1);console.log('PASS: explicit playback selects the target-language voice, speed and cancellation.');
}
{
 const f=fixture([{lang:'en-GB'}]);assert.equal(f.app.speak('سلام','fa',1,t=>f.statuses.push(t)),false);assert.equal(f.utterances.length,0);assert.match(f.statuses[0],/Голос этого языка/);console.log('PASS: missing target-language voice gives a fallback message, not incorrect-language playback.');
}
{
 const f=fixture([{lang:'en-GB'}]);f.app.speak('First','en');const first=f.utterances[0];f.app.speak('Second','en');first.onend();f.app.stopSpeech();assert.equal(f.cancelled(),2);console.log('PASS: stale speech completion cannot detach the next utterance from cancellation.');
}
