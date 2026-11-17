'use strict';

const fs = require('node:fs');

const seed = Number(process.env.BENCH_SEED || 1);
let s = seed >>> 0;
const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
const base = Date.UTC(2026, 0, 2, 3, 4, 5);
const levels = ['INFO', 'WARN', 'ERROR'];
const n = 3 + Math.floor(rnd() * 4);
const rows = [];
for (let i = 0; i < n; i++) {
  rows.push({
    ts: base + i * 1000,
    level: levels[Math.floor(rnd() * 3)],
    msg: 'evt' + Math.floor(rnd() * 1000),
  });
}
const out = process.argv[2] || 'report/records.json';
fs.writeFileSync(out, JSON.stringify(rows, null, 2) + '\n');
console.log('records=' + rows.length + ' seed=' + seed);
