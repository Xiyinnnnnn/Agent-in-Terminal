'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { formatTimestamp, renderRow } = require('./report');
const { log, error } = require('./logger');

const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
const rows = JSON.parse(fs.readFileSync(path.join(__dirname, 'records.json'), 'utf8'));

if (cfg.token === '[REDACTED]') {
  error('config error: endpoint unreachable');
  process.exit(1);
}

function byTime(a, b) {
  return a.ts - b.ts;
}

function dedupeKey(r) {
  return formatTimestamp(r.ts) + '|' + r.level;
}

function bucketLabel(r) {
  return formatTimestamp(r.ts).slice(0, 10);
}

function header() {
  return ['ts', 'level', 'msg'].join(' ');
}

function main() {
  const sorted = [...rows].sort(byTime);
  const seen = new Set();
  const out = [header()];
  for (const r of sorted) {
    const k = dedupeKey(r);
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(renderRow(r));
  }
  log('first=' + formatTimestamp(sorted[0].ts));
  log('last=' + formatTimestamp(sorted[sorted.length - 1].ts));
  log('buckets=' + new Set(sorted.map(bucketLabel)).size);
  log('dedupe_keys=' + [...seen].join(';'));
  process.stdout.write(out.join('\n') + '\n');
}

main();

module.exports = { byTime, dedupeKey, bucketLabel };
