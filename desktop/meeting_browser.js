'use strict';
// Web compatibility only: retain the actual Chromium/OS versions and storage.
// Electron's product token can select a native-client path on third-party sites.
function browserUserAgent(value){
 return String(value||'').replace(/\s(?:Electron|Adelia|adelia-desktop)\/[^\s]+/gi,'').replace(/\s{2,}/g,' ').trim();
}
function configure(contents){
 const ua=browserUserAgent(contents.getUserAgent());
 if(!/Chrome\/\d+/.test(ua))throw new Error('Meeting browser has no Chromium user agent');
 contents.setUserAgent(ua);
 return ua;
}
module.exports={browserUserAgent,configure};
