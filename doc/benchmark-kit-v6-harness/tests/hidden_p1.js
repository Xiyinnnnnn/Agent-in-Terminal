'use strict';

const assert = require('node:assert');
const dir = process.env.REPORT_DIR || '../stage1/report';
const { formatTimestamp } = require(dir + '/report');

const cases = [
  [1767323045000, '2026-01-02 03:04:05'],
  [1782864000000, '2026-07-01 00:00:00'],
  [1767225599000, '2025-12-31 23:59:59'],
  [1793570400000, '2026-11-01 22:00:00'],
  [1764556800000, '2025-12-01 02:40:00'],
];

for (const [ms, want] of cases) {
  assert.strictEqual(formatTimestamp(ms), want, 'TZ=' + process.env.TZ + ' ms=' + ms);
}

console.log('p1 ok TZ=' + process.env.TZ);
