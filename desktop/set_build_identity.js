'use strict';
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process');
const file=path.join(__dirname,'package.json');
const sha=String(process.env.ADELIA_BUILD_SHA||process.env.GITHUB_SHA||cp.execFileSync('git',['rev-parse','HEAD'],{cwd:path.resolve(__dirname,'..'),encoding:'utf8'})).trim();
if(!/^[a-f0-9]{40}$/.test(sha))throw new Error('Build source commit must be a full Git SHA');
const pkg=JSON.parse(fs.readFileSync(file,'utf8'));pkg.adeliaBuildSha=sha;
fs.writeFileSync(file,JSON.stringify(pkg,null,2)+'\n');console.log('Desktop source commit: '+sha);
