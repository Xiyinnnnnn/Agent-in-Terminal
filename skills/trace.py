#!/usr/bin/env python3
"""trace.py — 把另一个 agent 的 mem_hist+summaries 清洗成结构化执行轨迹（省 80%~96% token）。"""
import argparse, json, os, re, sys, time

BASE = os.path.expanduser("~/.cache/trace")
FAIL_RE = re.compile(r'退出码\s*([1-9]\d*)|Traceback|执行失败|\[已拒绝\]|\[超出上限\]|命令超时')
CODE_RE = re.compile(r'^退出码\s*(-?\d+)')
CJK_RE = re.compile(r'[\u4e00-\u9fff]')

def toks(s):
    cjk = len(CJK_RE.findall(s))
    return int(cjk + (len(s) - cjk) / 3.5)

def brief(res, w=90):
    res = str(res or '')
    head, body = res.split('\n', 1) if '\n' in res else (res, '')
    m = CODE_RE.match(head)
    code = m.group(1) if m else '?'
    bl = [l.strip() for l in body.split('\n') if l.strip()]
    first = bl[0] if bl else head.strip()
    if first == '[stderr]' and len(bl) > 1: first = 'stderr: ' + bl[1]
    return {'code': code, 'lines': len(bl), 'bytes': len(res), 'first': first[:w],
            'fail': bool(FAIL_RE.search(res)) or code not in ('0', '?')}

def parse(hist, summaries):
    out, pend, cur = [], {}, None
    for k, s in enumerate(summaries or [], 1):
        out.append({'kind': 'sum', 'sn': k, 'text': re.sub(r'\s+', ' ', str(s))})
    for m in hist:
        role, c = m.get('role'), m.get('content')
        if role == 'user':
            if isinstance(c, str) and c.startswith('历史背景：'):
                out.append({'kind': 'sum', 'sn': 0, 'text': c}); cur = None; continue
            txt = c if isinstance(c, str) else '[图%d]' % sum(
                1 for p in c if isinstance(p, dict) and p.get('type') == 'image_url')
            cur = {'kind': 'turn', 'u': re.sub(r'\s+', ' ', txt), 'tools': []}
            out.append(cur)
        elif role == 'assistant':
            for tc in (m.get('tool_calls') or []):
                f = tc.get('function') or {}
                try: a = json.loads(f.get('arguments') or '{}')
                except Exception: a = {}
                pend[tc.get('id')] = (f.get('name') or 'RUN', a)
        elif role == 'tool':
            name, a = pend.pop(m.get('tool_call_id'), ('RUN', {}))
            if cur is not None:
                cur['tools'].append({'name': name, 'args': a, 'res': str(c or '')})
    n = 0
    for it in out:
        if it['kind'] == 'turn':
            n += 1; it['idx'] = '#%d' % n
    return out

def render(items, level=1, uw=60, rw=90, sw=400):
    L, nsum, stok = [], 0, 0
    for it in items:
        if it['kind'] == 'sum': nsum += 1; stok += toks(it['text'])
    if level == 0 and nsum:
        L.append('※ 压缩摘要 ×%d（共 %d tok，因果链用 --sums 取全文）' % (nsum, stok))
    for it in items:
        if it['kind'] == 'sum':
            if level >= 1:
                tx, tag = it['text'], ('#%d' % it['sn']) if it['sn'] else '?'
                if len(tx) > sw: tx = tx[:sw] + '…（共%d字/%dtok，--sum %s 取全文）' % (len(it['text']), toks(it['text']), tag)
                L.append('※ 摘要%s [%dtok] %s' % (tag, toks(it['text']), tx))
            continue
        nf = sum(1 for t in it['tools'] if brief(t['res'])['fail'])
        tag = '  [%d工具%s]' % (len(it['tools']), ' · %d失败' % nf if nf else '') if it['tools'] else ''
        L.append(it['idx'] + ' u:' + it['u'][:uw] + tag)
        if level >= 1:
            for j, t in enumerate(it['tools'], 1):
                b = brief(t['res'], rw)
                cmd = (t['args'].get('command') or '').replace('\n', ' ')[:rw]
                why = (t['args'].get('explain') or '')[:24]
                L.append('   %s.%d %s %s| %s → exit %s · %d行/%dB · %s' % (
                    it['idx'], j, t['name'], ('「%s」' % why) if why else ' ', cmd,
                    b['code'], b['lines'], b['bytes'], ('FAIL ' if b['fail'] else '') + b['first']))
    return '\n'.join(L)

def raw(items, sel):
    L = []
    for it in items:
        if it['kind'] != 'turn': continue
        for j, t in enumerate(it['tools'], 1):
            tid = '%s.%d' % (it['idx'], j)
            if sel(tid, t):
                L.append('=== %s %s ===\n%s' % (tid, t['name'], t['res']))
    return '\n'.join(L)

def fails(items):
    L, n = [], 0
    for it in items:
        if it['kind'] != 'turn': continue
        for j, t in enumerate(it['tools'], 1):
            b = brief(t['res'])
            if b['fail']:
                n += 1
                L.append('%s.%d %s | %s → exit %s · %s' % (
                    it['idx'], j, t['name'], (t['args'].get('command') or '')[:80], b['code'], b['first']))
    return ('FAIL ×%d\n' % n + '\n'.join(L)) if n else 'FAIL ×0（无失败）'

def md_table(items):
    L = ['| # | 动作 | 命令 | 结果 | 状态 |', '|---|---|---|---|---|']
    for it in items:
        if it['kind'] != 'turn': continue
        for j, t in enumerate(it['tools'], 1):
            b = brief(t['res'])
            cmd = (t['args'].get('command') or '').replace('\n', ' ').replace('|', '\\|')[:80]
            res = 'exit %s · %d行/%dB · %s' % (b['code'], b['lines'], b['bytes'], b['first'].replace('|', '\\|')[:60])
            L.append('| %s.%d | %s | `%s` | %s | %s |' % (
                it['idx'], j, (t['args'].get('explain') or '')[:20], cmd, res, 'FAIL' if b['fail'] else 'OK'))
    return '\n'.join(L)

def dump_from_pid(pid, wait=5.0):
    os.makedirs(BASE, exist_ok=True)
    out = os.path.join(BASE, 'hist_%d.json' % pid)
    if os.path.exists(out): os.remove(out)
    src = os.path.join(BASE, '_dump_%d.py' % pid)
    open(src, 'w', encoding='utf-8').write(
        'import sys, json\n'
        'd = sys.modules["__main__"].__dict__\n'
        'json.dump({"mem_hist": d.get("mem_hist") or [], "summaries": d.get("summaries") or []},\n'
        '          open(%r, "w", encoding="utf-8"), ensure_ascii=False)\n' % out)
    if not os.path.isdir('/proc/%d' % pid):
        print('错误：目标进程 %d 不存在' % pid, file=sys.stderr); sys.exit(2)
    try:
        sys.remote_exec(pid, src)
    except Exception as e:
        print('错误：注入失败 %s（需同 UID + 同 CPython 小版本）' % e, file=sys.stderr); sys.exit(2)
    t0 = time.monotonic()
    while not os.path.exists(out):
        if time.monotonic() - t0 > wait:
            print('错误：%.1fs 内未落盘' % wait, file=sys.stderr); sys.exit(2)
        time.sleep(0.1)
    try: os.remove(src)
    except OSError: pass
    return out

def selftest():
    H = [{"role": "user", "content": "起服务并验证"},
         {"role": "assistant", "content": None, "tool_calls": [{"id": "a", "type": "function",
          "function": {"name": "RUN", "arguments": json.dumps({"command": "node s.mjs", "explain": "起服务"})}}]},
         {"role": "tool", "tool_call_id": "a", "content": "退出码 0\nlistening on 3050"},
         {"role": "assistant", "content": None, "tool_calls": [{"id": "b", "type": "function",
          "function": {"name": "RUN", "arguments": json.dumps({"command": "curl :3050", "explain": "验端口"})}}]},
         {"role": "tool", "tool_call_id": "b", "content": "退出码 7\n\n[stderr] curl: (7) Failed to connect"},
         {"role": "assistant", "content": "端口没起"}]
    it = parse(H, ["历史背景：前 40 轮接反代，DNS 未解决。"])
    o1, o0 = render(it, 1), render(it, 0)
    ck = [('L1含FAIL', 'FAIL' in o1), ('L0无工具行', '.1 ' not in o0), ('摘要渲染', '摘要#1' in o1),
          ('序号连续', '#1.1' in o1 and '#1.2' in o1), ('md表头', md_table(it).startswith('| # |')),
          ('失败清单', '#1.2' in fails(it)), ('精确命中', 'Failed to connect' in raw(it, lambda i, t: i == '#1.2')),
          ('预算函数', toks('中文abc') > 0)]
    for n, ok in ck: print(('PASS ' if ok else 'FAIL ') + n)
    return 0 if all(k for _, k in ck) else 1

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('hist', nargs='?')
    ap.add_argument('--pid', type=int)
    ap.add_argument('--level', type=int, default=1)
    ap.add_argument('--sums', action='store_true')
    ap.add_argument('--sum', type=int)
    ap.add_argument('--id')
    ap.add_argument('--grep')
    ap.add_argument('--md', action='store_true')
    ap.add_argument('--fails', action='store_true')
    ap.add_argument('--budget', type=int, default=0)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    path = dump_from_pid(a.pid) if a.pid else a.hist
    if not path:
        print('错误：给 --pid 或 hist.json', file=sys.stderr); sys.exit(1)
    try: d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        print('错误：读 %s 失败 %s' % (path, e), file=sys.stderr); sys.exit(1)
    items = parse(d.get('mem_hist') or [], d.get('summaries'))
    if not items:
        print('(空历史)', file=sys.stderr); sys.exit(3)
    if a.sums or a.sum:
        for it in items:
            if it['kind'] == 'sum' and (a.sums or it['sn'] == a.sum):
                print('=== 摘要#%d [%dtok / %dB] ===\n%s\n' % (it['sn'], toks(it['text']), len(it['text']), it['text']))
        sys.exit(0)
    if a.grep or a.id:
        print(raw(items, lambda tid, t: (a.id and tid == a.id) or
                  (a.grep and re.search(a.grep, t['res'] + json.dumps(t['args'], ensure_ascii=False)))) or '(无命中)')
        sys.exit(0)
    if a.fails: print(fails(items)); sys.exit(0)
    if a.md: print(md_table(items)); sys.exit(0)
    s = render(items, a.level)
    if a.budget and toks(s) > a.budget:
        s = render(items, 0)
        if toks(s) > a.budget: s = s[:a.budget * 2] + '\n…(预算截断)'
    print(s)
