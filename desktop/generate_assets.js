'use strict';
const fs = require('fs');
const path = require('path');
const https = require('https');

const ICON_URL = process.env.ADELIA_DESKTOP_ICON_URL || 'https://adeliatutor.ru/assets/icons/adelia-icon-512.png';
const dir = path.join(__dirname, 'build');
const target = path.join(dir, 'icon.png');
const tmp = target + '.tmp';
const PNG = Buffer.from([137,80,78,71,13,10,26,10]);

function download(url, redirects = 0) {
  if (redirects > 5) return Promise.reject(new Error('Too many icon redirects'));
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { 'User-Agent': 'Adelia-Desktop-Build' } }, response => {
      const status = Number(response.statusCode || 0);
      if (status >= 300 && status < 400 && response.headers.location) {
        response.resume();
        const next = new URL(response.headers.location, url).toString();
        download(next, redirects + 1).then(resolve, reject);
        return;
      }
      if (status !== 200) {
        response.resume();
        reject(new Error(`Canonical icon HTTP ${status}`));
        return;
      }
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('end', () => resolve(Buffer.concat(chunks)));
      response.on('error', reject);
    }).on('error', reject);
  });
}

function validatePng(buffer) {
  if (buffer.length < 33 || !buffer.subarray(0, 8).equals(PNG)) throw new Error('Canonical Adelia icon is not a PNG');
  const width = buffer.readUInt32BE(16);
  const height = buffer.readUInt32BE(20);
  if (width !== 512 || height !== 512) throw new Error(`Canonical Adelia icon must be 512x512, got ${width}x${height}`);
}

(async () => {
  const buffer = await download(ICON_URL);
  validatePng(buffer);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(tmp, buffer);
  fs.renameSync(tmp, target);
  console.log('Synced canonical Adelia desktop icon:', ICON_URL, `${buffer.length} bytes`);
})().catch(error => {
  try { fs.rmSync(tmp, { force: true }); } catch (_) {}
  console.error('Desktop icon sync failed:', error && error.message ? error.message : error);
  process.exit(2);
});
