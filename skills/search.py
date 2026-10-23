#!/usr/bin/env python3
"""search.py — Tavily 多账号聚合搜索池

设计依据（官方 docs /documentation/rate-limits，2026-10-24 实测）：
  每 key 100 RPM（dev=prod），4 key → 400 RPM ≈ 6.67 rps
  429 响应带 Retry-After（示例 60s）→ 该 key 冷却，请求转其它 key，不整体串行等待
  /usage 端点独立限流 10 次/10min → 额度缓存 TTL 600s，禁止每次请求都查
选路：可用 key 中「剩余额度最高」优先；剩余过低降权；全冷却则按最早解冻时间等待。
"""
import argparse, hashlib, json, os, random, sys, threading, time
from collections import deque
from pathlib import Path
from urllib import error, request

BASE = os.environ.get("TAVILY_BASE", "https://api.tavily.com")
CFG_DIR = Path.home() / ".config" / "term_agent" / "skill"
STATE_F = CFG_DIR / ".search_state.json"
KEYS_F = CFG_DIR / ".search_keys"      # 可选：每行一个 key，600 权限
KEY_HINT_F = CFG_DIR / ".search_keys.py"

KEYS = os.environ.get("TAVILY_KEYS", "").split()   # 云端版不含任何 key

WINDOW = 60.0          # 限流窗口秒
USAGE_TTL = 600.0      # 额度缓存；等于 /usage 限流周期，避免撞 10/10min
USAGE_MIN_GAP = 62.0   # 单 key 两次 /usage 最小间隔
LOW_QUOTA = 50         # 剩余低于此值降权
MAX_BACKOFF = 300


def kid(k):
    return hashlib.sha1(k.encode()).hexdigest()[:10]


class KeyState:
    __slots__ = ("key", "id", "remaining", "limit", "used", "cooldown", "fails",
                 "win", "uw", "quota_ts", "local", "ok", "bad", "inflight", "last")

    def __init__(self, key):
        self.key, self.id = key, kid(key)
        self.remaining, self.limit, self.used = None, 1000, 0
        self.cooldown, self.fails, self.local = 0.0, 0, 0
        self.win = deque()      # 请求时间窗
        self.uw = deque()       # /usage 时间窗
        self.quota_ts = 0.0
        self.ok, self.bad = 0, 0
        self.inflight, self.last = 0, 0.0

    def avail_eff(self):
        r = self.remaining if self.remaining is not None else self.limit
        return r - self.local - self.used


class Pool:
    def __init__(self, keys, rpm, verbose=False):
        self.ks = [KeyState(k) for k in keys]
        self.rpm = max(1, int(rpm))
        self.verbose = verbose
        self.lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.calls = []          # 完成时间戳，用于 rps
        self.load()

    # ---------- 状态持久化 ----------
    def load(self):
        try:
            d = json.loads(STATE_F.read_text())
        except Exception:
            return
        for k in self.ks:
            s = d.get(k.id)
            if not s:
                continue
            k.remaining, k.limit = s.get("remaining"), s.get("limit", 1000)
            k.used, k.cooldown = s.get("used", 0), s.get("cooldown", 0.0)
            k.quota_ts = s.get("quota_ts", 0.0)
            k.ok, k.bad = s.get("ok", 0), s.get("bad", 0)

    def save(self):
        d = {k.id: {"remaining": k.remaining, "limit": k.limit, "used": k.used,
                    "cooldown": round(k.cooldown, 1), "quota_ts": k.quota_ts,
                    "ok": k.ok, "bad": k.bad} for k in self.ks}
        with self.save_lock:
            tmp = STATE_F.with_name(f".search_state.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(d, indent=1))
            os.chmod(tmp, 0o600)
            tmp.replace(STATE_F)

    def log(self, msg):
        if self.verbose:
            print(msg, file=sys.stderr)

    # ---------- 额度刷新 ----------
    def refresh_quota(self, force=False):
        now = time.time()
        for k in self.ks:
            if not force and now - k.quota_ts < USAGE_TTL:
                continue
            u = k.uw
            while u and now - u[0] > 600:
                u.popleft()
            if len(u) >= 10:
                self.log(f"[{k.id}] /usage 撞击 10/10min 限流，跳过")
                continue
            if now - k.quota_ts < USAGE_MIN_GAP:
                self.log(f"[{k.id}] /usage 间隔不足 62s，跳过")
                continue
            try:
                req = request.Request(BASE + "/usage", headers={"Authorization": f"Bearer {k.key}"})
                with request.urlopen(req, timeout=20) as r:
                    d = json.loads(r.read())
                u.append(now)
                q = d.get("key", {})
                k.used = q.get("usage", k.used)
                k.limit = q.get("limit", k.limit) or k.limit
                k.remaining = max(0, k.limit - k.used)
                k.quota_ts = now
                self.log(f"[{k.id}] usage={k.used}/{k.limit} 剩余={k.remaining}")
            except error.HTTPError as e:
                self.log(f"[{k.id}] /usage http={e.code}")
                if e.code == 429:
                    k.quota_ts = now
            except Exception as e:
                self.log(f"[{k.id}] /usage 失败 {type(e).__name__}")

    # ---------- 选路 ----------
    def pick(self, deadline):
        while True:
            now = time.time()
            best, best_score, waits = None, None, []
            for k in self.ks:
                w = k.win
                while w and now - w[0] >= WINDOW:
                    w.popleft()
                if k.cooldown > now:
                    waits.append(k.cooldown - now)
                    continue
                if len(w) >= self.rpm:
                    waits.append(WINDOW - (now - w[0]))
                    continue
                score = k.avail_eff() - 4 * k.inflight
                if k.avail_eff() < LOW_QUOTA:
                    score -= 100000          # 低额度降权但非禁用
                if (best is None or score > best_score
                        or (score == best_score and k.last < best.last)):
                    best, best_score = k, score
            if best:
                best.win.append(now)
                best.inflight += 1
                best.last = now
                return best
            if not waits:
                raise RuntimeError("无可用 key")
            wait = max(0.02, min(min(waits), 0.5))
            if time.time() + wait > deadline:
                raise TimeoutError(f"全部 key 限流/冷却，需再等 {min(waits):.1f}s")
            time.sleep(wait + random.uniform(0, 0.05))

    # ---------- 请求 ----------
    def search(self, payload, deadline):
        tried = set()
        last = ""
        while len(tried) < len(self.ks):
            k = self.pick(deadline)
            if k.id in tried and len(self.ks) - len(tried) <= 0:
                break
            tried.add(k.id)
            body = json.dumps(payload).encode()
            req = request.Request(BASE + "/search", data=body, method="POST",
                                  headers={"Authorization": f"Bearer {k.key}",
                                           "Content-Type": "application/json"})
            try:
                t0 = time.time()
                with request.urlopen(req, timeout=40) as r:
                    data = r.read()
                with self.lock:
                    k.local += 1
                    k.ok += 1
                    self.calls.append(time.time())
                with self.lock:
                    k.inflight = max(0, k.inflight - 1)
                self.log(f"[{k.id}] 200 {time.time()-t0:.2f}s")
                return json.loads(data)
            except error.HTTPError as e:
                code = e.code
                ra = e.headers.get("Retry-After")
                detail = e.read()[:300].decode("utf-8", "replace")
                last = f"{code} {detail}"
                with self.lock:
                    k.bad += 1
                    k.inflight = max(0, k.inflight - 1)
                if code == 429:
                    cd = float(ra) if ra and ra.replace(".", "").isdigit() else 60.0
                    cd = min(cd * (2 ** min(k.fails, 3)), MAX_BACKOFF)
                    k.fails += 1
                    k.cooldown = time.time() + cd
                    self.log(f"[{k.id}] 429 Retry-After={ra} → 冷却 {cd:.0f}s，换 key")
                elif code in (401, 403):
                    k.cooldown = time.time() + 3600
                    self.log(f"[{k.id}] {code} 认证失败 → 冷却 1h")
                else:
                    k.cooldown = time.time() + min(5 * (2 ** k.fails), 60)
                    k.fails += 1
                    self.log(f"[{k.id}] http={code} → 冷却 {k.cooldown-time.time():.0f}s")
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                with self.lock:
                    k.bad += 1
                    k.inflight = max(0, k.inflight - 1)
                k.cooldown = time.time() + min(5 * (2 ** k.fails), 60)
                k.fails += 1
                self.log(f"[{k.id}] {last} → 冷却")
            finally:
                self.save()
        raise RuntimeError("全部 key 均失败；最后响应: " + last[:200])

    def rps(self):
        if len(self.calls) < 2:
            return 0.0
        span = max(self.calls) - min(self.calls)
        return (len(self.calls) - 1) / span if span > 0 else 0.0


# ---------- 输出 ----------
def render(d, with_summary):
    out = []
    if d.get("answer"):
        out.append("=== 答案 ===")
        out.append(d["answer"])
    for i, r in enumerate(d.get("results", []), 1):
        out.append(f"{i}. {r.get('title','')}")
        out.append(f"   {r.get('url','')}")
        if with_summary and r.get("content"):
            out.append("   " + r["content"].replace("\n", " ")[:400])
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Tavily 多账号聚合搜索池")
    ap.add_argument("query", nargs="*", help="查询词；多个则为多查询")
    ap.add_argument("-q", "--queries-file", help="批量查询文件，每行一条")
    ap.add_argument("-d", "--depth", default="basic",
                    choices=["basic", "advanced", "fast", "ultra-fast"])
    ap.add_argument("-m", "--max-results", type=int, default=5)
    ap.add_argument("-t", "--topic", default="general", choices=["general", "news", "finance"])
    ap.add_argument("-r", "--time-range", choices=["day", "week", "month", "year"])
    ap.add_argument("-a", "--answer", action="store_true")
    ap.add_argument("-s", "--summary", action="store_true")
    ap.add_argument("-j", "--json", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--rpm", type=int, default=95, help="每 key 每分钟上限（官方 100，留余量）")
    ap.add_argument("-c", "--concurrency", type=int, default=0,
                    help="并发数；0=按 目标rps×2.0s 自动取（约 4 key 时 13）")
    ap.add_argument("--target-rps", type=float, default=6.0)
    ap.add_argument("--max-wait", type=float, default=90.0, help="单请求最多等待秒数")
    ap.add_argument("--refresh-quota", action="store_true", help="强制刷新 /usage（受 10/10min 限流）")
    ap.add_argument("--reset", action="store_true",
                    help="清冷却与失败计数（保留额度记账）")
    ap.add_argument("--stats", action="store_true", help="打印各 key 额度/冷却/窗口")
    a = ap.parse_args()

    keys = list(KEYS)
    if KEYS_F.exists():
        keys = [l.strip() for l in KEYS_F.read_text().splitlines() if l.strip()]
    if not keys:
        sys.exit(2)
    pool = Pool(keys, a.rpm, a.verbose)
    if a.reset:
        for k in pool.ks:
            k.cooldown, k.fails, k.bad = 0.0, 0, 0
        pool.save(); print("已清冷却/失败计数", file=sys.stderr)
    pool.refresh_quota(force=a.refresh_quota)

    if a.stats:
        print(json.dumps({"keys": [{
            "id": k.id, "remaining": k.remaining, "limit": k.limit, "used": k.used,
            "cooldown_s": max(0, round(k.cooldown - time.time(), 1)),
            "win": len(k.win), "rpm_cap": pool.rpm, "ok": k.ok, "bad": k.bad}
            for k in pool.ks], "agg_rpm": a.rpm * len(pool.ks),
            "agg_rps": round(a.rpm * len(pool.ks) / 60, 2)}, ensure_ascii=False, indent=1))
        if not a.query and not a.queries_file:
            return

    if a.concurrency <= 0:
        a.concurrency = max(4, min(32, int(round(a.target_rps * 2.2) + 1)))
    a.rpm = a.rpm if a.rpm > 0 else 95

    qs = list(a.query)
    if a.queries_file:
        qs += [l.strip() for l in Path(a.queries_file).read_text().splitlines() if l.strip()]
    if not qs:
        ap.print_help()
        sys.exit(2)

    payload_base = {"search_depth": a.depth, "max_results": max(1, min(20, a.max_results)),
                    "topic": a.topic, "include_answer": a.answer}
    if a.time_range:
        payload_base["time_range"] = a.time_range

    deadline = time.time() + a.max_wait
    results, errs = {}, []
    lock = threading.Lock()

    def work(i, q):
        try:
            d = pool.search({**payload_base, "query": q}, deadline + 60)
            with lock:
                results[i] = d
        except Exception as e:
            with lock:
                errs.append(f"[{i}] {q!r}: {e}")

    t0 = time.time()
    if len(qs) == 1:
        work(0, qs[0])
    else:
        qs_idx = list(enumerate(qs))
        qlock = threading.Lock()

        def worker():
            while True:
                with qlock:
                    if not qs_idx:
                        return
                    i, q = qs_idx.pop(0)
                work(i, q)
        ths = [threading.Thread(target=worker) for _ in range(max(1, min(a.concurrency, len(qs))))]
        [t.start() for t in ths]
        [t.join() for t in ths]

    if a.json:
        print(json.dumps({"n": len(results), "errors": errs,
                          "elapsed": round(time.time() - t0, 2), "rps": round(pool.rps(), 2),
                          "results": [results[i] for i in sorted(results)]},
                         ensure_ascii=False, indent=1))
    else:
        for i in sorted(results):
            if len(qs) > 1:
                print(f"\n### [{i+1}] {qs[i]}")
            print(render(results[i], a.summary))
        for e in errs:
            print("错误:", e, file=sys.stderr)
        if a.verbose:
            print(f"[耗时 {time.time()-t0:.2f}s  有效 rps {pool.rps():.2f}  "
                  f"成功 {len(results)}/{len(qs)}]", file=sys.stderr)
    sys.exit(0 if not errs else 1)


if __name__ == "__main__":
    main()
