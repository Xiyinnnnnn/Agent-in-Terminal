#!/usr/bin/env python3
import argparse, json, os, signal, subprocess, sys, time
from pathlib import Path

BASE = Path(os.path.expanduser("~/.cache/ctxinject"))
PAY = BASE / "payloads"
WAKE = signal.SIGWINCH
MARK = "term_agent.py"
ADB = "127.0.0.1:7957"
EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")

def emit(d):
    print(json.dumps(d, ensure_ascii=False, separators=(",", ":")), flush=True)

def die(m, code=1):
    print(json.dumps({"ev": "err", "msg": m}, ensure_ascii=False), file=sys.stderr, flush=True)
    sys.exit(code)

PAYLOAD = r'''
import os, sys, json, time, threading, traceback
from pathlib import Path
RES, TK, IMG, TXT = Path(RESULT_PATH), Path(TOKEN), IMAGE_PATH, MESSAGE_TEXT
S = {}
def host():
    for m in [sys.modules.get("__main__")] + list(sys.modules.values()):
        d = getattr(m, "__dict__", None) or {}
        if isinstance(d.get("mem_hist"), list) and callable(d.get("_img")): return m
    raise RuntimeError("no mem_hist+_img module")
def tail_ok(h):
    if not h: return True
    r = h[-1].get("role")
    if r == "tool":
        i = len(h) - 1; k = 0
        while i >= 0 and h[i].get("role") == "tool": i -= 1; k += 1
        a = h[i] if i >= 0 else {}
        return not a.get("tool_calls") or k >= len(a["tool_calls"])
    return not h[-1].get("tool_calls") if r == "assistant" else True
def work():
    m = host(); h = m.mem_hist
    if TK.exists(): return {"skip": "dup"}
    if S.get("msg") is not None and h and h[-1] is S["msg"]: return S["res"]
    if not tail_ok(h): return {"deferred": "tool_calls 未收尾"}
    c = m._img((TXT + " " + IMG).strip())
    S["msg"] = {"role": "user", "content": c}
    h.append(S["msg"]); TK.write_text("1")
    r = {"hist_len": len(h)}
    r["content"] = [[p.get("type"), len((p.get("image_url") or {}).get("url", "")) if p.get("type") == "image_url" else p.get("text")] for p in c] if isinstance(c, list) else [["str", str(c)[:120]]]
    if IMG:
        ps = [Path(x) for x in IMG.split() if Path(x).is_file()]
        r["imgs"] = [len(ps), sum(p.stat().st_size for p in ps)]
        if len(ps) == 1: r["img"] = [True, ps[0].stat().st_size]
    S["res"] = r
    return r
out = {}
for _ in range(4):
    try: out = dict(ok=True, pid=os.getpid(), thread=threading.current_thread().name, **work()); break
    except BaseException: out = dict(ok=False, err=traceback.format_exc()); time.sleep(0.05)
try: RES.write_text(json.dumps(out, ensure_ascii=False))
except BaseException: pass
'''


def pcmd(pid):
    try: return Path("/proc/%d/cmdline" % pid).read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError: return ""

def hosts(mark):
    r = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) == os.getpid(): continue
        c = pcmd(int(d.name)); t = c.split()
        if not t or "python" not in t[0].rsplit("/", 1)[-1]: continue
        n = [x.rsplit("/", 1)[-1] for x in t]
        if mark in n and "ctxinject.py" not in n: r.append((int(d.name), c))
    return r

def caught(pid, sig):
    try:
        for l in open("/proc/%d/status" % pid):
            if l.startswith("SigCgt:"): return bool(int(l.split()[1], 16) >> (sig - 1) & 1)
    except OSError: pass
    return False

def once(pid, text, img, tok, wake, wait):
    PAY.mkdir(parents=True, exist_ok=True)
    tag = "%d_%d" % (pid, time.time() * 1000)
    pl, rc = PAY / ("pl_%s.py" % tag), PAY / ("rc_%s.json" % tag)
    pl.write_text("RESULT_PATH=%r\nTOKEN=%r\nIMAGE_PATH=%r\nMESSAGE_TEXT=%r\n" % (str(rc), tok, img or "", text) + PAYLOAD)
    t0 = time.monotonic()
    try: sys.remote_exec(pid, str(pl))
    except Exception as e: return None, 0.0, "remote_exec 失败：%s" % e
    if wake and caught(pid, WAKE):
        while not rc.exists() and time.monotonic() - t0 < wait:
            time.sleep(0.12)
            try: os.kill(pid, WAKE)
            except OSError: return None, 0.0, "目标已消失"
    while not rc.exists() and time.monotonic() - t0 < wait:
        time.sleep(0.05)
    if not rc.exists(): return None, time.monotonic() - t0, None
    d = json.loads(rc.read_text())
    if d.get("skip") or "hist_len" in d:
        try: os.remove(pl)
        except OSError: pass
    return d, time.monotonic() - t0, None

def spawn_watch(pid, text, img, tok):
    log = BASE / ("watch_%d.log" % pid)
    with open(log, "ab") as f: f.write(b"")
    subprocess.Popen([sys.executable, __file__, "watch", str(pid), text, img, tok],
                     stdout=open(log, "ab"), stderr=subprocess.STDOUT, start_new_session=True)
    emit({"ev": "watch_spawn", "log": str(log)})

def inject(pid, text, img, wake, timeout):
    if pid == os.getpid(): die("target_is_self")
    if not Path("/proc/%d" % pid).exists(): die("no_such_pid:%d" % pid)
    if img:
        miss = [x for x in img.split() if not Path(x).is_file()]
        if miss: die("no_such_image:%s" % " ".join(miss))
    ok = wake and caught(pid, WAKE)
    if wake and not ok: emit({"ev": "note", "msg": "no_sigwinch", "mode": "queue"})
    tok = str(PAY / ("done_%d_%d" % (pid, time.time() * 1000)))
    d, el, err = once(pid, text, img, tok, ok, timeout if ok else min(timeout, 2.0))
    if err: die(err)
    if d and not d.get("deferred"):
        emit({"ev": "ok", "el": round(el, 2), "d": d}); return 0
    emit({"ev": "defer", "el": round(el, 2), "reason": "busy" if d else "no_checkpoint", "d": d})
    spawn_watch(pid, text, img, tok)
    return 3

def watch(pid, text, img, tok):
    t0 = time.monotonic(); n = 0
    while time.monotonic() - t0 < 600:
        time.sleep(2 if n < 10 else 10); n += 1
        d, el, err = once(pid, text, img, tok, False, 2.0)
        if err: emit({"ev": "watch_err", "t": int(time.monotonic() - t0), "msg": err}); return
        if d and not d.get("deferred"):
            emit({"ev": "watch_ok", "t": int(time.monotonic() - t0), "d": d}); return
    emit({"ev": "watch_timeout", "t": int(time.monotonic() - t0)})

def shot(out=None, dev=None, long=None):
    raw = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=20).stdout
    ds = [l.split()[0] for l in raw.splitlines()[1:] if len(l.split()) >= 2 and l.split()[1] == "device"]
    if not ds: die("no_adb_device")
    dev = dev or (ADB if ADB in ds else ds[0])
    p = Path(out).expanduser() if out else BASE / ("shot_%s.png" % time.strftime("%Y%m%d-%H%M%S"))
    p.parent.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path.home() / ".local/bin/term_agent"))
    z = None
    try:
        from term_agent import _shrink_raw
        b = subprocess.run(["adb", "-s", dev, "exec-out", "screencap"], capture_output=True, timeout=90).stdout
        z = _shrink_raw(b, long) if len(b) >= 16 else None
    except Exception as e:
        print(json.dumps({"ev": "note", "msg": "raw_unavailable", "err": str(e)}, ensure_ascii=False), file=sys.stderr, flush=True)
    if not z:
        z = subprocess.run(["adb", "-s", dev, "exec-out", "screencap", "-p"], capture_output=True, timeout=90).stdout
        if not z or z[:8] != b"\x89PNG\r\n\x1a\n": die("screencap_not_png")
    p.write_bytes(z)
    emit({"ev": "shot", "path": str(p), "bytes": len(z)})
    return str(p)

def gc():
    n, now = 0, time.time()
    for f in (list(PAY.glob("*")) if PAY.exists() else []):
        if now - f.stat().st_mtime > 3 * 86400: os.remove(f); n += 1
    emit({"ev": "gc", "n": n})

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "watch":
    watch(int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]); sys.exit()

ap = argparse.ArgumentParser(prog="ctxinject")
sub = ap.add_subparsers(dest="v", required=True)
p = sub.add_parser("hosts"); p.add_argument("--mark", default=MARK)
p = sub.add_parser("shot"); p.add_argument("-o"); p.add_argument("--device"); p.add_argument("--long", type=int)
p = sub.add_parser("inject"); p.add_argument("items", nargs="+"); p.add_argument("--pid", type=int, required=True)
p.add_argument("-w", "--wake", action="store_true"); p.add_argument("--timeout", type=float, default=8.0)
p = sub.add_parser("auto"); p.add_argument("--text", default="看图"); p.add_argument("--pid", type=int, required=True)
p.add_argument("--timeout", type=float, default=8.0)
sub.add_parser("gc")

if __name__ == "__main__":
    a = ap.parse_args()
    if a.v == "hosts": emit({"ev": "hosts", "list": [[i, c] for i, c in hosts(a.mark)]})
    elif a.v == "shot": shot(a.o, a.device, a.long)
    elif a.v == "gc": gc()
    elif a.v == "inject":
        im = [x for x in a.items if Path(x).suffix.lower() in EXT]
        sys.exit(inject(a.pid, " ".join(x for x in a.items if x not in im), " ".join(im), a.wake, a.timeout))
    else: sys.exit(inject(a.pid, a.text, shot(), True, a.timeout))
