'use strict';
const fs = require('fs');
const path = require('path');

const source = path.join(__dirname, '..', 'brand', 'adelia_icon', 'adelia-icon-512.png');
const dir = path.join(__dirname, 'build');
const target = path.join(dir, 'icon.png');
const tmp = target + '.tmp';
const PNG = Buffer.from([137,80,78,71,13,10,26,10]);

function validatePng(buffer) {
  if (buffer.length < 33 || !buffer.subarray(0, 8).equals(PNG)) throw new Error('Canonical Adelia icon is not a PNG');
  const width = buffer.readUInt32BE(16);
  const height = buffer.readUInt32BE(20);
  if (width !== 512 || height !== 512) throw new Error(`Canonical Adelia icon must be 512x512, got ${width}x${height}`);
}

try {
  const buffer = fs.readFileSync(source);
  validatePng(buffer);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(tmp, buffer);
  fs.renameSync(tmp, target);
  console.log('Synced repository canonical Adelia desktop icon:', source, `${buffer.length} bytes`);
} catch (error) {
  try { fs.rmSync(tmp, { force: true }); } catch (_) {}
  console.error('Desktop icon sync failed:', error && error.message ? error.message : error);
  process.exit(2);
}
