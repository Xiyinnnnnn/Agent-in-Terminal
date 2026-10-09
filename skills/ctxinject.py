#!/usr/bin/env python3
import argparse, json, os, signal, subprocess, sys, time
from pathlib import Path

BASE = Path(os.path.expanduser("~/.cache/ctxinject"))
PAY = BASE / "payloads"
WAKE = signal.SIGWINCH
MARK = "term_agent.py"
ADB = "127.0.0.1:7957"
EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")

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
        p = Path(IMG); r["img"] = [p.is_file(), p.stat().st_size if p.is_file() else 0]
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
    print("后台看守 %s" % log)

def inject(pid, text, img, wake, timeout):
    if pid == os.getpid(): sys.exit("拒绝：目标是本进程")
    if not Path("/proc/%d" % pid).exists(): sys.exit("无此 pid %d" % pid)
    if img and not Path(img).is_file(): sys.exit("无此图片 %s" % img)
    ok = wake and caught(pid, WAKE)
    if wake and not ok: print("未捕获 SIGWINCH，退化为排队")
    tok = str(PAY / ("done_%d_%d" % (pid, time.time() * 1000)))
    d, el, err = once(pid, text, img, tok, ok, timeout if ok else min(timeout, 2.0))
    if err: sys.exit(err)
    if d and not d.get("deferred"):
        print("已落地 %.2fs %s" % (el, json.dumps(d, ensure_ascii=False))); return 0
    print("宿主忙：%s" % (d or "未到检查点"))
    spawn_watch(pid, text, img, tok)
    return 3

def watch(pid, text, img, tok):
    t0 = time.monotonic(); n = 0
    while time.monotonic() - t0 < 600:
        time.sleep(2 if n < 10 else 10); n += 1
        d, el, err = once(pid, text, img, tok, False, 2.0)
        if err: print("%.0fs %s" % (time.monotonic() - t0, err), flush=True); return
        if d and not d.get("deferred"):
            print("%.0fs 已落地 %s" % (time.monotonic() - t0, json.dumps(d, ensure_ascii=False)), flush=True); return
    print("看守超时放弃", flush=True)

def shot(out=None, dev=None, long=None):
    raw = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=20).stdout
    ds = [l.split()[0] for l in raw.splitlines()[1:] if len(l.split()) >= 2 and l.split()[1] == "device"]
    if not ds: sys.exit("无在线 adb 设备")
    dev = dev or (ADB if ADB in ds else ds[0])
    p = Path(out).expanduser() if out else BASE / ("shot_%s.png" % time.strftime("%Y%m%d-%H%M%S"))
    p.parent.mkdir(parents=True, exist_ok=True)
    b = subprocess.run(["adb", "-s", dev, "exec-out", "screencap", "-p"], capture_output=True, timeout=90).stdout
    if not b or b[:8] != b"\x89PNG\r\n\x1a\n": sys.exit("screencap 无输出或非 PNG")
    p.write_bytes(b)
    print("%s %dB 原始（压缩由宿主 _img 内嵌逻辑完成）" % (p, len(b)))
    return str(p)

def gc():
    n, now = 0, time.time()
    for f in (list(PAY.glob("*")) if PAY.exists() else []):
        if now - f.stat().st_mtime > 3 * 86400: os.remove(f); n += 1
    print("gc %d" % n)

def pid_of(a):
    if a.pid: return a.pid
    h = hosts(a.mark)
    if len(h) == 1: return h[0][0]
    print("\n".join("%d %s" % x for x in h) or "无候选，用 --pid")
    sys.exit(2)

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "watch":
    watch(int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]); sys.exit()

ap = argparse.ArgumentParser(prog="ctxinject")
sub = ap.add_subparsers(dest="v", required=True)
p = sub.add_parser("hosts"); p.add_argument("--mark", default=MARK)
p = sub.add_parser("shot"); p.add_argument("-o"); p.add_argument("--device"); p.add_argument("--long", type=int)
p = sub.add_parser("inject"); p.add_argument("items", nargs="+"); p.add_argument("--pid", type=int)
p.add_argument("--mark", default=MARK); p.add_argument("-w", "--wake", action="store_true"); p.add_argument("--timeout", type=float, default=8.0)
p = sub.add_parser("auto"); p.add_argument("--text", default="看图"); p.add_argument("--pid", type=int)
p.add_argument("--mark", default=MARK); p.add_argument("--timeout", type=float, default=8.0)
sub.add_parser("gc")

if __name__ == "__main__":
    a = ap.parse_args()
    if a.v == "hosts": print("\n".join("%d %s" % x for x in hosts(a.mark)))
    elif a.v == "shot": shot(a.o, a.device, a.long)
    elif a.v == "gc": gc()
    elif a.v == "inject":
        im = [x for x in a.items if Path(x).suffix.lower() in EXT]
        sys.exit(inject(pid_of(a), " ".join(x for x in a.items if x not in im), im[0] if im else "", a.wake, a.timeout))
    else: sys.exit(inject(pid_of(a), a.text, shot(), True, a.timeout))
