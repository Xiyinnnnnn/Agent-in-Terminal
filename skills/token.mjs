#!/usr/bin/env node
// token.mjs — 四供应商 token 消耗 / 额度查询（单脚本，provider 字段切换）
//   deepseek     GET /user/balance（无 usage 接口，消耗靠本地余额快照差推算）
//   openrouter   GET /key + /credits（余额 = total_credits - total_usage）
//   opencode     仅 GET /inference/v1/models 探测 key，官方无公开余额接口
//   commandcode  /alpha/{whoami,usage/summary,billing/credits,billing/subscriptions}
// 用法：token.mjs <provider> [--json] [--key K] [--timeout N] [--no-color] [--no-save]
// 兼容：argv[1] 为 dsbalance / wallet / ccusage 软链时按名字推断 provider
import { readFileSync, writeFileSync, appendFileSync, existsSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import os from 'node:os';
import path from 'node:path';

const CFG = path.join(os.homedir(), '.config/term_agent');
const KEYBIN = path.join(CFG, 'key.bin');

// ── 参数 ──
const ARGV = process.argv.slice(2);
const VOPTS = new Set(['--key', '--provider', '--timeout']);
const has = (n) => ARGV.includes(n);
const opt = (n) => { const i = ARGV.indexOf(n); return i >= 0 && i + 1 < ARGV.length && !ARGV[i + 1].startsWith('--') ? ARGV[i + 1] : ''; };
const positional = [];
for (let i = 0; i < ARGV.length; i++) {
  if (ARGV[i].startsWith('--')) { if (VOPTS.has(ARGV[i])) i++; continue; }
  positional.push(ARGV[i]);
}
const WANT_JSON = has('--json');
const NO_SAVE = has('--no-save');
const NO_COLOR = has('--no-color') || !process.stdout.isTTY;
const TIMEOUT = Math.max(3, Number(opt('--timeout') || 20)) * 1000;

// ── 渲染工具 ──
const dim = (s) => NO_COLOR ? s : '\x1b[2m' + s + '\x1b[0m';
const bold = (s) => NO_COLOR ? s : '\x1b[1m' + s + '\x1b[0m';
const green = (s) => NO_COLOR ? s : '\x1b[32m' + s + '\x1b[0m';
const yellow = (s) => NO_COLOR ? s : '\x1b[33m' + s + '\x1b[0m';
const red = (s) => NO_COLOR ? s : '\x1b[31m' + s + '\x1b[0m';
const usd = (n) => '$' + Number(n || 0).toFixed(2);
const nfmt = (n) => Number(n || 0).toLocaleString('en-US');
function bar(used, cap, w = 10) {
  const p = cap > 0 ? Math.min(1, Math.max(0, used / cap)) : 0;
  const fill = Math.round(p * w);
  const c = p >= 0.9 ? red : p >= 0.7 ? yellow : green;
  return c('█'.repeat(fill)) + dim('░'.repeat(w - fill)) + ` ${String(Math.round(p * 100)).padStart(3)}%`;
}

// ── key.bin 解码（base64(明文 ^ sha256(machine-id)[i%32])）──
function decodeKeyBin() {
  try {
    let seed;
    try { seed = readFileSync('/etc/machine-id', 'utf8').trim(); }
    catch { seed = os.hostname() + os.homedir(); }
    const mk = createHash('sha256').update(seed).digest();
    const raw = Buffer.from(readFileSync(KEYBIN, 'utf8').trim(), 'base64');
    const out = Buffer.alloc(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw[i] ^ mk[i % mk.length];
    return out.toString('utf8');
  } catch { return ''; }
}
function keyFile(p) {
  try { const s = readFileSync(p, 'utf8').trim(); return s || ''; } catch { return ''; }
}

// ── provider 解析 ──
const ALIAS = {
  ds: 'deepseek', deepseek: 'deepseek',
  or: 'openrouter', openrouter: 'openrouter',
  oc: 'opencode', zen: 'opencode', opencode: 'opencode',
  cc: 'commandcode', commandcode: 'commandcode',
};
function resolveProvider() {
  let raw = opt('--provider') || positional[0] || '';
  if (!raw) {
    const n = path.basename(process.argv[1] || '');
    raw = /dsbalance/i.test(n) ? 'deepseek' : /wallet/i.test(n) ? 'openrouter' : /ccusage/i.test(n) ? 'commandcode' : '';
  }
  return ALIAS[raw.toLowerCase()] || '';
}

const HELP = `token.mjs — 多供应商 token 消耗 / 额度查询

  token.mjs deepseek|ds      [--json] [--no-save] [--key K]   官方余额 + 本地快照推消耗
  token.mjs openrouter|or    [--json] [--key K]              余额（购-用）+ key 限额
  token.mjs opencode|oc|zen  [--json] [--key K]              key 有效性（无公开余额接口）
  token.mjs commandcode|cc   [--json] [--key K]              月额度 / 5h / 每周 / 本周期用量

  通用：--timeout N（秒，默认 20）  --no-color
  旧命令兼容：dsbalance / wallet / ccusage 软链自动推断 provider

退出码：0 成功 · 1 网络或非鉴权 HTTP 失败 · 2 缺 key · 3 余额不足 · 4 鉴权失败 401/403 · 5 未知 provider`;

// ── DeepSeek 官方 ──
async function runDeepSeek() {
  const BASE = (process.env.DS_BASE || 'https://api.deepseek.com').replace(/\/+$/, '');
  const HIST = process.env.DS_HIST_FILE || path.join(os.homedir(), '.local/share/dsbalance/history.jsonl');
  const HIST_KEEP = 2000;
  let KEY = opt('--key');
  if (!KEY && process.env.DEEPSEEK_API_KEY) KEY = process.env.DEEPSEEK_API_KEY.trim();
  if (!KEY) for (const p of [process.env.DEEPSEEK_KEY_FILE, path.join(CFG, 'deepseek.key')].filter(Boolean)) {
    const s = keyFile(p); if (s) { KEY = s; break; }
  }
  if (!KEY) { const s = decodeKeyBin(); if (/^sk-/.test(s)) KEY = s; }
  if (!KEY) {
    console.error('无 DeepSeek key：设 DEEPSEEK_API_KEY，或写入 ~/.config/term_agent/deepseek.key');
    return 2;
  }

  const t0 = Date.now();
  let res, body;
  try {
    res = await fetch(BASE + '/user/balance', {
      headers: { Authorization: 'Bearer ' + KEY, 'Content-Type': 'application/json', Accept: 'application/json' },
      signal: AbortSignal.timeout(TIMEOUT),
    });
    body = await res.text();
  } catch (e) {
    console.error(`网络失败: ${e.name}: ${e.message}`);
    return 1;
  }
  const ms = Date.now() - t0;

  let data = null;
  try { data = JSON.parse(body); } catch {}
  if (!res.ok) {
    const msg = (data && data.error && data.error.message) || body.slice(0, 200);
    if (WANT_JSON) console.log(JSON.stringify({ ok: false, provider: 'deepseek', status: res.status, error: msg }, null, 2));
    else console.error(`HTTP ${res.status} · ${msg}`);
    return (res.status === 401 || res.status === 403) ? 4 : 1;
  }

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
    console.log(JSON.stringify({ ok: true, provider: 'deepseek', status: res.status, ms, ...data, history: hist.length }, null, 2));
    return 0;
  }

  const SYM = { CNY: '¥', USD: '$' };
  const money = (cur, v) => (SYM[cur] || '') + Number(v || 0).toFixed(2);
  const lines = [bold('DeepSeek 余额')];
  lines.push(`${dim('状态')}   ${data.is_available ? green('可调用') : red('不可调用（余额不足）')}`);
  if (!infos.length) lines.push(dim('（balance_infos 为空）'));

  for (const b of infos) {
    const cur = b.currency;
    lines.push(`${dim(cur.padEnd(4))} 总 ${bold(money(cur, b.total_balance))}  ·  充值 ${money(cur, b.topped_up_balance)}  ·  赠金 ${money(cur, b.granted_balance)}`);
    const older = prevSame(cur).filter(h => now - h.ts >= 3600e3).sort((a, b2) => a.ts - b2.ts)[0];
    if (older) {
      const spent = older.total - Number(b.total_balance);
      const days = (now - older.ts) / 864e5;
      const perDay = spent / days;
      if (perDay > 0.0001) {
        const left = Number(b.total_balance) / perDay;
        lines.push(dim(`     近 ${days.toFixed(1)}d 消耗 ${money(cur, spent)}（${money(cur, perDay)}/天）· 按此速率可用 ${left >= 1 ? left.toFixed(0) + ' 天' : (left * 24).toFixed(1) + ' 小时'}`));
      } else if (spent < 0) {
        lines.push(dim(`     期间充值 ${money(cur, -spent)}`));
      }
    }
  }
  lines.push(dim(`${ms}ms · 快照 ${NO_SAVE ? '未写入' : hist.length + ' 条'} · ${HIST}`));
  console.log(lines.join('\n'));
  return data.is_available ? 0 : 3;
}

// ── 通用 GET ──
async function get(url, key) {
  try {
    const r = await fetch(url, {
      headers: { Authorization: 'Bearer ' + key, Accept: 'application/json', 'Content-Type': 'application/json', 'User-Agent': 'cli' },
      signal: AbortSignal.timeout(TIMEOUT),
    });
    return { status: r.status, text: await r.text() };
  } catch (e) {
    return { status: 0, text: `${e.name}: ${e.message}` };
  }
}
const jparse = (t) => { try { return JSON.parse(t); } catch { return null; } };
const authExit = (st) => (st === 401 || st === 403) ? 4 : 1;

// ── OpenRouter ──
async function runOpenRouter() {
  const BASE = (process.env.OPENROUTER_API_BASE || 'https://openrouter.ai/api/v1').replace(/\/+$/, '');
  const KEY = opt('--key') || keyFile(path.join(CFG, 'openrouter.key')) || (process.env.OPENROUTER_API_KEY || '').trim();
  if (!KEY) {
    console.error('无 OpenRouter key。获取：https://openrouter.ai/settings/keys\n配置：export OPENROUTER_API_KEY=... 或写入 ~/.config/term_agent/openrouter.key（chmod 600）');
    return 2;
  }
  const r1 = await get(BASE + '/key', KEY);
  const r2 = await get(BASE + '/credits', KEY);
  const kd = jparse(r1.text), cd = jparse(r2.text);
  const errs = {};
  if (r1.status >= 400) errs.key = `HTTP ${r1.status} ` + (((kd || {}).error || {}).message || r1.text.slice(0, 120));
  if (r2.status >= 400) errs.credits = `HTTP ${r2.status} ` + (((cd || {}).error || {}).message || r2.text.slice(0, 120));

  if (WANT_JSON) {
    console.log(JSON.stringify({ ok: r1.status < 400, provider: 'openrouter', key: kd, credits: cd, errors: errs }, null, 2));
    return r1.status < 400 ? 0 : authExit(r1.status);
  }

  const d = (kd || {}).data || {};
  const cr = (cd || {}).data || {};
  const out = ['OpenRouter 额度'];
  if (d && Object.keys(d).length) {
    const kind = d.is_management_key ? '管理 key' : (d.is_provisioning_key ? '临时 key' : '普通 key');
    out.push(`Key    ${d.label || '—'}  ·  ${kind}  ·  免费层 ${d.is_free_tier ? '是' : '否'}`);
    if ('total_credits' in cr) {
      const bal = Number(cr.total_credits) - Number(cr.total_usage);
      out.push(`余额   ${usd(bal)}（购 ${usd(cr.total_credits)} － 已用 ${usd(cr.total_usage)}）`);
    }
    if (d.usage !== undefined && d.usage !== null) {
      out.push(`用量   累计 ${usd(d.usage)} · 日 ${usd(d.usage_daily)} · 周 ${usd(d.usage_weekly)} · 月 ${usd(d.usage_monthly)}`);
    }
    if (d.limit !== undefined && d.limit !== null) {
      out.push(`限额   ${bar(Number(d.usage) || 0, Number(d.limit) || 0)} ${usd(d.usage)} / ${usd(d.limit)}（剩 ${usd(d.limit_remaining)}，重置 ${d.limit_reset || '—'}）`);
    } else {
      out.push('限额   未设花费上限（uncapped）');
    }
    const fm = d.free_model_daily_requests;
    if (fm && (fm.limit || fm.used)) out.push(`免费模型 今日 ${fm.used}/${fm.limit} 次（剩 ${fm.remaining}）`);
    for (const bd of (d.budgets || []).slice(0, 3)) {
      out.push(`预算   ${bd.scope || '—'} ${usd(bd.spend_usd)} / ${usd(bd.limit_usd)} · 剩 ${usd(bd.remaining_usd)} · ${bd.reset_interval || ''}`);
    }
  }
  if (errs.credits && r2.status === 403) {
    out.push(`余额   需 Management key（普通 key 无权读 /credits）：${errs.credits}`);
  }
  if (errs.key) out.push(`错误   ${errs.key}`);
  console.log(out.join('\n'));
  return r1.status < 400 ? 0 : authExit(r1.status);
}

// ── OpenCode ──
async function runOpenCode() {
  const BASE = (process.env.OPENCODE_API_BASE || 'https://opencode.ai/inference').replace(/\/+$/, '');
  const KEY = opt('--key') || keyFile(path.join(CFG, 'opencode.key')) || (process.env.OPENCODE_API_KEY || '').trim();
  if (!KEY) {
    console.error('无 OpenCode key。获取：Console → Account › Personal API keys（前缀 oc_sk_）\n配置：export OPENCODE_API_KEY=... 或写入 ~/.config/term_agent/opencode.key');
    return 2;
  }
  const r = await get(BASE + '/v1/models', KEY);
  const ok = r.status === 200;
  if (WANT_JSON) {
    console.log(JSON.stringify({ ok, provider: 'opencode', status: r.status, models_bytes: r.text.length,
      balance_api: false, note: '官方无公开余额接口' }, null, 2));
    return ok ? 0 : authExit(r.status);
  }
  const out = ['OpenCode（Console / Zen）'];
  out.push(`Key    ${ok ? green('有效 ✓') : (r.status ? red(`无效 ✗ HTTP ${r.status}`) : '网络失败')}`);
  if (ok) {
    const j = jparse(r.text);
    out.push(`模型   可列 ${(j && Array.isArray(j.data)) ? j.data.length : 0} 个（该端点 200 = key 可鉴权）`);
  }
  out.push('余额   官方未提供公开接口（issue #10448 仍在请求中）');
  out.push('查看   Console → Activity / 顶部 Billing 抽屉（快捷键 B）；Settings › Billing');
  out.push('用量   `opencode stats`（本地统计，非账户余额）');
  console.log(out.join('\n'));
  return ok ? 0 : authExit(r.status);
}

// ── CommandCode ──
async function runCommandCode() {
  const base = (process.env.CC_API_BASE || 'https://api.commandcode.ai').replace(/\/+$/, '');
  const KEY = opt('--key') || (process.env.CC_KEY || '').trim() || (process.env.CC_KEY_FILE ? keyFile(process.env.CC_KEY_FILE) : '') || decodeKeyBin();
  if (!KEY) {
    console.error('无 key（--key / CC_KEY / ~/.config/term_agent/key.bin）');
    return 2;
  }
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
  const got = {}, fails = [];
  await Promise.all(ENDPOINTS.map(async ([k, p]) => {
    try {
      const r = await fetch(base + p, { headers, signal: AbortSignal.timeout(15000) });
      const txt = await r.text();
      if (!r.ok && r.status !== 402 && r.status !== 429) throw new Error(`HTTP ${r.status} ${txt.slice(0, 120)}`);
      got[k] = JSON.parse(txt);
      got[k].__status = r.status;
    } catch (e) {
      fails.push(`${p}: ${e.message}`);
    }
  }));

  if (WANT_JSON) { console.log(JSON.stringify({ provider: 'commandcode', ...got, fails }, null, 2)); return fails.length ? 1 : 0; }

  const rel = (ms) => {
    const d = Math.max(0, ms - Date.now());
    const h = Math.floor(d / 3.6e6), m = Math.floor((d % 3.6e6) / 6e4), dd = Math.floor(h / 24);
    return dd > 0 ? `${dd}d${h % 24}h` : h > 0 ? `${h}h${m}m` : `${m}m`;
  };
  const at = (ms) => { const d = new Date(ms); return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };

  const u = got.account?.user, cr = got.credits || {}, wl = cr.windowLimits || {};
  const s = got.usage || {}, sub = got.subscription?.data || {};
  const lines = [bold('CommandCode 用量 / 额度')];
  if (u) lines.push(`${dim('账号')}   ${u.name} <${u.email}>`);
  if (sub.planId) {
    const pe = sub.currentPeriodEnd ? ` · 周期至 ${at(Date.parse(sub.currentPeriodEnd))}（剩 ${rel(Date.parse(sub.currentPeriodEnd))}）` : '';
    lines.push(`${dim('计划')}   ${sub.planId} ${sub.status}${sub.cancelAtPeriodEnd ? ' (已取消续订)' : ''}${pe}`);
  }
  const monthLeft = cr.credits?.monthlyCredits;
  const monthUsed = s.totalCredits;
  if (monthLeft !== undefined) {
    const capM = monthUsed !== undefined ? monthLeft + monthUsed : undefined;
    const extra = [cr.credits?.purchasedCredits ? `含购入 ${usd(cr.credits.purchasedCredits)}` : '',
      cr.credits?.freeCredits ? `含赠送 ${usd(cr.credits.freeCredits)}` : ''].filter(Boolean).join(' ');
    lines.push(`${dim('月额度')} ${capM ? bar(monthUsed, capM) + '  ' : ''}剩余 ${bold(usd(monthLeft))}${capM ? ' / ' + usd(capM) : ''}${extra ? '  ' + dim(extra) : ''}`);
  }
  for (const [key, label] of [['fiveHour', '5小时'], ['weekly', '每周 ']]) {
    const w = wl[key];
    if (!w) continue;
    const flag = w.exceeded ? red('已用尽') : '';
    lines.push(`${dim(label)} ${bar(w.used, w.cap)}  ${usd(w.used)} / ${usd(w.cap)}${flag}${w.resetAt ? `  ·  重置 ${at(w.resetAt)}（${rel(w.resetAt)} 后）` : ''}`);
  }
  if (s.totalCount !== undefined) {
    lines.push(`${dim('本周期')} ${nfmt(s.totalCount)} 次请求 · 成功 ${s.successRate}%${s.failedCount ? `（失败 ${s.failedCount}）` : ''} · tokens ${(Number(s.totalTokens) / 1e6).toFixed(2)}M（入 ${(Number(s.totalTokensIn) / 1e6).toFixed(2)}M / 出 ${(Number(s.totalTokensOut) / 1e6).toFixed(2)}M）`);
    if (s.periodStart) lines.push(`${dim('起始')}   ${at(Date.parse(s.periodStart))}${s.periodBasis ? dim(' · ' + s.periodBasis) : ''}`);
  }
  if (fails.length) lines.push(red('失败端点: ' + fails.join(' | ')));
  console.log(lines.join('\n'));
  return fails.length ? 1 : 0;
}

// ── 入口 ──
const prov = resolveProvider();
if (!prov) {
  if (positional.length) console.error(`未知 provider：${positional[0]}`);
  console.log(HELP);
  process.exit(5);
}
const RUN = { deepseek: runDeepSeek, openrouter: runOpenRouter, opencode: runOpenCode, commandcode: runCommandCode };
process.exit(await RUN[prov]());
