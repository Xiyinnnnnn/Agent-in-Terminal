'use strict';

const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');

const root = process.argv[2] || 'stage1/report';
const entries = [];
for (const f of fs.readdirSync(root).sort()) {
  const p = path.join(root, f);
  if (!fs.statSync(p).isFile()) continue;
  const buf = fs.readFileSync(p);
  entries.push({
    file: p,
    bytes: buf.length,
    sha256: crypto.createHash('sha256').update(buf).digest('hex'),
  });
}
fs.mkdirSync('stage1', { recursive: true });
fs.writeFileSync('stage1/lock.json',
  JSON.stringify({ generated_at: new Date().toISOString(), entries }, null, 2) + '\n');
console.log('lock entries=' + entries.length);
