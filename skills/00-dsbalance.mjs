#!/usr/bin/env -S node
// 00-dsbalance — DeepSeek 官方余额 / 额度查询（GET /user/balance）
// 官方只有余额接口，没有 token 用量接口；消耗由本地余额快照差推算。
import { readFileSync, writeFileSync, appendFileSync, existsSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';

const BASE = (process.env.DS_BASE || 'https://api.deepseek.com').replace(/\/+$/, '');
const HIST = process.env.DS_HIST_FILE || path.join(os.homedir(), '.local/share/dsbalance/history.jsonl');
const HIST_KEEP = 2000;
const args = process.argv.slice(2);
const WANT_JSON = args.includes('--json');
const NO_SAVE = args.includes('--no-save');
const NO_COLOR = args.includes('--no-color') || !process.stdout.isTTY;
const keyArg = (() => { const i = args.indexOf('--key'); return i >= 0 ? args[i + 1] : ''; })();

function keyFromBin() {
  // 与宿主一致：base64(明文 ^ sha256(machine-id)[i%32])；非 sk- 开头视为非 DeepSeek key
  try {
    const f = path.join(os.homedir(), '.config/term_agent/key.bin');
    let seed;
    try { seed = readFileSync('/etc/machine-id', 'utf8').trim(); }
    catch { seed = os.hostname() + os.homedir(); }
    const mk = createHash('sha256').update(seed).digest();
    const raw = Buffer.from(readFileSync(f, 'utf8').trim(), 'base64');
    const out = Buffer.alloc(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw[i] ^ mk[i % mk.length];
    const s = out.toString('utf8');
    return /^sk-/.test(s) ? s : '';
  } catch { return ''; }
}

function loadKey() {
  if (keyArg) return keyArg;
  if (process.env.DEEPSEEK_API_KEY) return process.env.DEEPSEEK_API_KEY.trim();
  for (const p of [process.env.DEEPSEEK_KEY_FILE,
    path.join(os.homedir(), '.config/term_agent/deepseek.key')].filter(Boolean)) {
    try { const s = readFileSync(p, 'utf8').trim(); if (s) return s; } catch {}
  }
  return keyFromBin();
}

const KEY = loadKey();
if (!KEY) {
  console.error('无 DeepSeek key：设 DEEPSEEK_API_KEY，或写入 ~/.config/term_agent/deepseek.key');
  process.exit(2);
}

const t0 = Date.now();
let res, body;
try {
  res = await fetch(BASE + '/user/balance', {
    headers: { Authorization: 'Bearer ' + KEY, 'Content-Type': 'application/json', Accept: 'application/json' },
    signal: AbortSignal.timeout(20000),
  });
  body = await res.text();
} catch (e) {
  console.error(`网络失败: ${e.name}: ${e.message}`);
  process.exit(1);
}
const ms = Date.now() - t0;

let data = null;
try { data = JSON.parse(body); } catch {}
if (!res.ok) {
  const msg = (data && data.error && data.error.message) || body.slice(0, 200);
  if (WANT_JSON) console.log(JSON.stringify({ ok: false, status: res.status, error: msg }, null, 2));
  else console.error(`HTTP ${res.status} · ${msg}`);
  process.exit(res.status === 401 || res.status === 403 ? 4 : 1);
}

// ── 快照 ──
const now = Date.now();
const infos = Array.isArray(data.balance_infos) ? data.balance_infos : [];
let hist = [];
if (existsSync(HIST)) {
  try { hist = readFileSync(HIST, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { hist = []; }
}
const prevSame = (cur) => hist.filter(h => h.currency === cur);

if (!NO_SAVE) {
  try {
    mkdirSync(path.dirname(HIST), { recursive: true });
    for (const b of infos) {
      const rec = { ts: now, currency: b.currency, total: Number(b.total_balance),
        granted: Number(b.granted_balance), topped: Number(b.topped_up_balance) };
      appendFileSync(HIST, JSON.stringify(rec) + '\n');
      hist.push(rec);
    }
    if (hist.length > HIST_KEEP) {
      const keep = hist.slice(-HIST_KEEP);
      writeFileSync(HIST, keep.map(x => JSON.stringify(x)).join('\n') + '\n');
      hist = keep;
    }
  } catch {}
}

if (WANT_JSON) {
  console.log(JSON.stringify({ ok: true, status: res.status, ms, ...data, history: hist.length }, null, 2));
  process.exit(0);
}

// ── 渲染 ──
const C = (s) => NO_COLOR ? '' : s;
const dim = (s) => C('\x1b[2m') + s + (NO_COLOR ? '' : '\x1b[0m');
const bold = (s) => C('\x1b[1m') + s + (NO_COLOR ? '' : '\x1b[0m');
const SYM = { CNY: '¥', USD: '$' };
const money = (cur, v) => (SYM[cur] || '') + Number(v || 0).toFixed(2);

const lines = [bold('DeepSeek 余额')];
lines.push(`${dim('状态')}   ${data.is_available ? C('\x1b[32m') + '可调用' + (NO_COLOR ? '' : '\x1b[0m') : C('\x1b[31m') + '不可调用（余额不足）' + (NO_COLOR ? '' : '\x1b[0m')}`);
if (!infos.length) lines.push(dim('（balance_infos 为空）'));

for (const b of infos) {
  const cur = b.currency;
  lines.push(`${dim(cur.padEnd(4))} 总 ${bold(money(cur, b.total_balance))}  ·  充值 ${money(cur, b.topped_up_balance)}  ·  赠金 ${money(cur, b.granted_balance)}`);
  // 速率：取同币种内最早一条 ≥1h 前的快照
  const older = prevSame(cur).filter(h => now - h.ts >= 3600e3).sort((a, b2) => a.ts - b2.ts)[0];
  if (older) {
    const spent = older.total - Number(b.total_balance);
    const days = (now - older.ts) / 864e5;
    const perDay = spent / days;
    if (perDay > 0.0001) {
      const left = Number(b.total_balance) / perDay;
      lines.push(`${dim('     ')}${dim(`近 ${days.toFixed(1)}d 消耗 ${money(cur, spent)}（${money(cur, perDay)}/天）· 按此速率可用 ${left >= 1 ? left.toFixed(0) + ' 天' : (left * 24).toFixed(1) + ' 小时'}`)}`);
    } else if (spent < 0) {
      lines.push(dim(`     期间充值 ${money(cur, -spent)}`));
    }
  }
}
lines.push(dim(`${ms}ms · 快照 ${NO_SAVE ? '未写入' : hist.length + ' 条'} · ${HIST}`));
console.log(lines.join('\n'));
process.exit(data.is_available ? 0 : 3);
