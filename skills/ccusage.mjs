#!/usr/bin/env node
// ccusage — CommandCode 账号用量 / 额度面板
// 只读四个官方 /alpha/* 端点，零 token 消耗。key 只读内存，不落盘、不打印。
// 端点依据：官方 CLI `/usage` 命令的底层路由（docs/resources/usage-limits + 社区 provider 源码实证）
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';

const KEY_FILE = process.env.CC_KEY_FILE || path.join(os.homedir(), '.config/term_agent/key.bin');
const BASE = process.env.CC_API_BASE || 'https://api.commandcode.ai';
const WANT_JSON = process.argv.includes('--json');
const NO_COLOR = process.argv.includes('--no-color') || !process.stdout.isTTY;

function loadKey() {
  if (process.env.CC_KEY) return process.env.CC_KEY;
  let seed;
  try { seed = readFileSync('/etc/machine-id', 'utf8').trim(); }
  catch { seed = os.hostname() + os.homedir(); }
  const mk = createHash('sha256').update(seed).digest();
  const raw = Buffer.from(readFileSync(KEY_FILE, 'utf8').trim(), 'base64');
  const out = Buffer.alloc(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw[i] ^ mk[i % mk.length];
  return out.toString('utf8');
}

const KEY = loadKey();
if (!KEY) { console.error('无 key（CC_KEY 或 key.bin）'); process.exit(2); }

const headers = {
  Authorization: 'Bearer ' + KEY,
  'x-command-code-version': '1.88.5',
  'x-cli-environment': 'production',
  'User-Agent': 'cli',
  'Content-Type': 'application/json',
};

const ENDPOINTS = [
  ['account', '/alpha/whoami'],
  ['usage', '/alpha/usage/summary'],
  ['credits', '/alpha/billing/credits'],
  ['subscription', '/alpha/billing/subscriptions'],
];

const got = {};
const fails = [];
await Promise.all(ENDPOINTS.map(async ([k, p]) => {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 15000);
  try {
    const r = await fetch(BASE + p, { headers, signal: ctl.signal });
    const txt = await r.text();
    if (!r.ok && r.status !== 402 && r.status !== 429) throw new Error(`HTTP ${r.status} ${txt.slice(0, 120)}`);
    got[k] = JSON.parse(txt);
    got[k].__status = r.status;
  } catch (e) {
    fails.push(`${p}: ${e.message}`);
  } finally { clearTimeout(t); }
}));

if (WANT_JSON) { console.log(JSON.stringify({ ...got, fails }, null, 2)); process.exit(fails.length ? 1 : 0); }

// ── 渲染 ──
const C = (s) => NO_COLOR ? '' : s;
const dim = (s) => C('\x1b[2m') + s + (NO_COLOR ? '' : '\x1b[0m');
const bold = (s) => C('\x1b[1m') + s + (NO_COLOR ? '' : '\x1b[0m');
const usd = (n) => '$' + Number(n || 0).toFixed(2);

function bar(used, cap, w = 10) {
  const p = cap > 0 ? Math.min(1, used / cap) : 0;
  const fill = Math.round(p * w);
  const color = p >= 0.9 ? '\x1b[31m' : p >= 0.7 ? '\x1b[33m' : '\x1b[32m';
  return (NO_COLOR ? '' : color) + '█'.repeat(fill) + (NO_COLOR ? '' : '\x1b[0m')
    + dim('░'.repeat(w - fill)) + ` ${String(Math.round(p * 100)).padStart(3)}%`;
}
function rel(ms) {
  const d = Math.max(0, ms - Date.now());
  const h = Math.floor(d / 3.6e6), m = Math.floor((d % 3.6e6) / 6e4);
  const dd = Math.floor(h / 24);
  return dd > 0 ? `${dd}d${h % 24}h` : h > 0 ? `${h}h${m}m` : `${m}m`;
}
function at(ms) { const d = new Date(ms); return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; }
const nfmt = (n) => Number(n || 0).toLocaleString('en-US');

const u = got.account?.user, cr = got.credits || {}, wl = cr.windowLimits || {};
const s = got.usage || {}, sub = got.subscription?.data || {};

const lines = [];
lines.push(bold('CommandCode 用量 / 额度'));
if (u) lines.push(`${dim('账号')}   ${u.name} <${u.email}>`);
if (sub.planId) {
  const pe = sub.currentPeriodEnd ? ` · 周期至 ${at(Date.parse(sub.currentPeriodEnd))}（剩 ${rel(Date.parse(sub.currentPeriodEnd))}）` : '';
  lines.push(`${dim('计划')}   ${sub.planId} ${sub.status}${sub.cancelAtPeriodEnd ? ' (已取消续订)' : ''}${pe}`);
}

const monthLeft = cr.credits?.monthlyCredits;
const monthUsed = s.totalCredits;
if (monthLeft !== undefined) {
  const capM = monthUsed !== undefined ? monthLeft + monthUsed : undefined;
  const extra = [cr.credits?.purchasedCredits ? `含购入 ${usd(cr.credits.purchasedCredits)}` : '', cr.credits?.freeCredits ? `含赠送 ${usd(cr.credits.freeCredits)}` : ''].filter(Boolean).join(' ');
  lines.push(`${dim('月额度')} ${capM ? bar(monthUsed, capM) + '  ' : ''}剩余 ${bold(usd(monthLeft))}${capM ? ' / ' + usd(capM) : ''}${extra ? '  ' + dim(extra) : ''}`);
}

for (const [key, label] of [['fiveHour', '5小时'], ['weekly', '每周 ']]) {
  const w = wl[key];
  if (!w) continue;
  const flag = w.exceeded ? C('\x1b[31m') + '已用尽' : '';
  lines.push(`${dim(label)} ${bar(w.used, w.cap)}  ${usd(w.used)} / ${usd(w.cap)}${flag}${NO_COLOR ? '' : ''}${w.resetAt ? `  ·  重置 ${at(w.resetAt)}（${rel(w.resetAt)} 后）` : ''}`);
}

if (s.totalCount !== undefined) {
  lines.push(`${dim('本周期')} ${nfmt(s.totalCount)} 次请求 · 成功 ${s.successRate}%${s.failedCount ? `（失败 ${s.failedCount}）` : ''} · tokens ${(Number(s.totalTokens) / 1e6).toFixed(2)}M（入 ${(Number(s.totalTokensIn) / 1e6).toFixed(2)}M / 出 ${(Number(s.totalTokensOut) / 1e6).toFixed(2)}M）`);
  if (s.periodStart) lines.push(`${dim('起始')}   ${at(Date.parse(s.periodStart))}${s.periodBasis ? dim(' · ' + s.periodBasis) : ''}`);
}

if (fails.length) lines.push(C('\x1b[31m') + '失败端点: ' + fails.join(' | '));
console.log(lines.join('\n'));
process.exit(fails.length ? 1 : 0);
