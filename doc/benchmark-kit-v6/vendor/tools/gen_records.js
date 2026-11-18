'use strict';
// 私有种子记录生成器：node gen_records.js <seed> <n>  ->  stdout JSON
const crypto = require('node:crypto');
const seed = process.argv[2] || 'default';
const n = parseInt(process.argv[3] || '64', 10);
if (!(n >= 8)) { console.error('n must be >= 8'); process.exit(2); }

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const h = crypto.createHash('sha256').update(seed).digest();
const rnd = mulberry32(h.readUInt32BE(0));
const LEVELS = ['INFO', 'WARN', 'ERROR'];
const MSGS = ['boot', 'clock skew', 'upstream 502', 'retry', 'flush', 'rotate',
  'cache miss', 'slow query', 'socket reset', 'quota warn'];
const base = Date.UTC(2025, 11, 1, 0, 0, 0);
const span = 365 * 24 * 3600 * 1000;

const arr = [];
for (let i = 0; i < n - 8; i++) {
  const ts = base + Math.floor((rnd() * span) / 1000) * 1000;
  arr.push({
    seq: arr.length,
    ts,
    level: LEVELS[Math.floor(rnd() * LEVELS.length)],
    msg: MSGS[Math.floor(rnd() * MSGS.length)],
  });
}
// 固定棱角：同 ts 同 level 同 msg 三重复（应合并为 1）+ 同 ts 同 level 不同 msg（必须都留）+ 同 ts 不同 level
const T = 1767323045000;
arr.push({ seq: arr.length, ts: T, level: 'INFO', msg: 'dup' });
arr.push({ seq: arr.length, ts: T, level: 'INFO', msg: 'dup' });
arr.push({ seq: arr.length, ts: T, level: 'INFO', msg: 'dup' });
arr.push({ seq: arr.length, ts: T, level: 'INFO', msg: 'sibling' });
arr.push({ seq: arr.length, ts: T, level: 'WARN', msg: 'sibling' });
arr.push({ seq: arr.length, ts: T + 1000, level: 'INFO', msg: 'a|b' });
arr.push({ seq: arr.length, ts: T + 2000, level: 'WARN', msg: 'line1\nline2' });
arr.push({ seq: arr.length, ts: T + 3000, level: 'ERROR', msg: 'tab\there' });

for (let i = arr.length - 1; i > 0; i--) {
  const j = Math.floor(rnd() * (i + 1));
  const tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp;
}
process.stdout.write(JSON.stringify(arr, null, 2) + '\n');
