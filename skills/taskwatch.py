#!/usr/bin/env python3
"""taskwatch — 长任务监听：一次阻塞调用，stdout 只回一行 DONE / BLOCKED。

DONE 退出码 0；BLOCKED 退出码 1（表示"没结论/需人介入"，不是命令失败）。
"""
import argparse, hashlib, json, os, re, shlex, signal, subprocess, sys, time
from pathlib import Path

BASE = Path.home() / ".cache/taskwatch"
TAGRE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
CAP = 3300          # 宿主 RUN 硬超时 3600s，留 300s 余量
TAILB = 8192        # 只读日志尾部做正则


# ---------- 基础件 ----------
def die(msg, code=2):
    print("ERROR %s" % msg, file=sys.stderr, flush=True)
    sys.exit(code)


def boot():
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    except Exception:
        return time.monotonic()


def truthy(v):
    return v is not None and v > 0 and v != float("inf")


def atomic_write(p, s):
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(s)
    os.replace(tmp, p)


def statinfo(pid):
    """→ (state, starttime) 或 None（进程不存在）"""
    try:
        raw = Path("/proc/%d/stat" % pid).read_text()
    except Exception:
        return None
    rest = raw[raw.rfind(")") + 2:].split()
    if not rest:
        return None
    return rest[0], rest[19] if len(rest) > 19 else ""


def alive(pid, start=""):
    st = statinfo(pid)
    if st is None:
        return False
    state, starttime = st
    if state == "Z":
        return False
    if start and starttime and start != starttime:
        return False          # pid 被复用
    return True


def starttime_of(pid):
    st = statinfo(pid)
    return st[1] if st else ""


def tailtext(p, n=TAILB):
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def lines(p):
    try:
        with open(p, "rb") as f:
            return f.read().count(b"\n")
    except Exception:
        return 0


def wake(mode):
    try:
        subprocess.run(["termux-wake-" + mode], capture_output=True, timeout=10)
    except Exception:
        pass


def other_active(me):
    for p in BASE.glob("*/pid"):
        if p.parent.name == me:
            continue
        try:
            pid = int(p.read_text().strip() or 0)
            st = p.parent.joinpath("start").read_text().strip()
        except Exception:
            continue
        if pid and alive(pid, st):
            return True
    return False


def dpaths(tag):
    if not TAGRE.match(tag or ""):
        die("bad_tag:%r（限 A-Za-z0-9._- 长度1-40）" % tag)
    d = BASE / tag
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- 单行结论 ----------
def result(status, elapsed, code=0, **kv):
    parts = ["%ds" % int(round(elapsed))]
    order = ["rc", "why", "resume", "size", "ln", "frozen"]
    kv.setdefault("frozen", 0)
    for k in order:
        if k in kv and kv[k] not in (None, ""):
            parts.append("%s=%s" % (k, kv[k]))
    print("%-7s %s" % (status, " ".join(parts)), flush=True)
    sys.exit(code)


# ---------- 产物判据 ----------
def fsize(p):
    try:
        return os.path.getsize(p)
    except Exception:
        return None


# ---------- 等待核心 ----------
def watch(tag, timeout, interval, file, min_size, stable, gdone, gblock):
    d = dpaths(tag)
    rcf, rctmp, pidf, logf = d / "rc", d / "rc.tmp", d / "pid", d / "log"
    try:
        pid = int(pidf.read_text().split()[0])
    except Exception:
        pid = 0
    start = ""
    try:
        start = (d / "start").read_text().strip()
    except Exception:
        pass

    t0 = time.monotonic()
    pb, pm = boot(), t0
    frozen, last_sz, last_chg, gone = 0.0, None, t0, 0
    state = {"status": "WATCH", "tag": tag, "pid": pid, "ts": int(time.time())}
    atomic_write(d / "state", json.dumps(state, ensure_ascii=False))

    def touch(status, **kv):
        state.update({"status": status, "ts": int(time.time())})
        state.update(kv)
        atomic_write(d / "state", json.dumps(state, ensure_ascii=False))

    while True:
        m = time.monotonic()
        b = boot()
        dm, db = m - pm, b - pb
        if db - dm > 2:                       # 被系统冻结过
            frozen += db - dm
        pm, pb = m, b
        el = m - t0

        # 1 rc
        if rctmp.exists() and not rcf.exists():
            try:
                os.replace(rctmp, rcf)
            except Exception:
                pass
        if rcf.exists():
            try:
                rc = int(rcf.read_text().strip() or 0)
            except Exception:
                rc = 0
            sz = fsize(file) if file else None
            if rc != 0:
                touch("BLOCKED", why="rc", rc=rc)
                result("BLOCKED", el, 1, rc=rc, size=sz, frozen=int(frozen))
            if file and (sz is None or sz < min_size):
                touch("BLOCKED", why="short", rc=rc, size=sz)
                result("BLOCKED", el, 1, why="short", rc=rc, size=sz, frozen=int(frozen))
            touch("DONE", rc=0)
            result("DONE", el, 0, rc=0, size=sz, frozen=int(frozen))

        # 2 日志判据
        tail = tailtext(logf) if (gblock or gdone) else ""
        if gblock and tail and re.search(gblock, tail):
            touch("BLOCKED", why="prompt")
            result("BLOCKED", el, 1, why="prompt", ln=lines(logf), frozen=int(frozen))
        if gdone and tail and re.search(gdone, tail):
            touch("DONE", why="grep")
            result("DONE", el, 0, size=fsize(file) if file else None, frozen=int(frozen))

        # 3 进程
        if pid and not alive(pid, start):
            gone += 1
            if gone >= 2:                     # 宽限一轮等 rc 落盘
                sz = fsize(file) if file else None
                ok = (sz is not None and sz >= min_size) if file else False
                if not file:
                    touch("BLOCKED", why="orphan")
                    result("BLOCKED", el, 1, why="orphan", frozen=int(frozen))
                if ok:
                    touch("DONE", why="file")
                    result("DONE", el, 0, size=sz, frozen=int(frozen))
                touch("BLOCKED", why="orphan", size=sz)
                result("BLOCKED", el, 1, why="orphan", size=sz, frozen=int(frozen))
        else:
            gone = 0

        # 4 无 pid 场景：文件稳定
        if not pid and file:
            sz = fsize(file)
            if sz != last_sz:
                last_sz, last_chg = sz, m
            elif sz is not None and sz >= min_size and (m - last_chg) >= stable:
                touch("DONE", why="stable")
                result("DONE", el, 0, size=sz, frozen=int(frozen))

        # 5 超时
        if truthy(timeout) and el > timeout:
            touch("BLOCKED", why="timeout", resume=1 if alive(pid, start) else 0)
            result("BLOCKED", el, 1, why="timeout",
                   resume=1 if alive(pid, start) else 0,
                   size=fsize(file) if file else None, frozen=int(frozen))

        time.sleep(interval)


# ---------- 子命令 ----------
def do_run(a):
    cmd = " ".join(a.cmd).strip()
    if not cmd:
        die("no_cmd")
    tag = a.tag or ("t" + hashlib.sha1(cmd.encode()).hexdigest()[:8])
    d = dpaths(tag)
    pidf, rcf, rctmp, logf = d / "pid", d / "rc", d / "rc.tmp", d / "log"

    if pidf.exists():
        try:
            pid = int(pidf.read_text().split()[0])
            st = (d / "start").read_text().strip()
            old = (d / "cmd").read_text().strip()
        except Exception:
            pid, st, old = 0, "", ""
        if pid and alive(pid, st) and old == cmd:          # 幂等：直接续听
            return watch(tag, a.timeout, a.interval, a.file, a.min_size,
                         a.size_stable, a.grep_done, a.grep_block)

    for f in (rcf, rctmp):
        if f.exists():
            f.unlink()
    atomic_write(d / "cmd", cmd)
    wake("lock") if not a.no_wake else None

    inner = "( %s\n); echo $? > %s" % (cmd, shlex.quote(str(rctmp)))
    with open(logf, "wb") as lf:
        p = subprocess.Popen(["bash", "-c", inner], stdin=subprocess.DEVNULL,
                             stdout=lf, stderr=subprocess.STDOUT,
                             start_new_session=True)
    atomic_write(pidf, "%d %s\n" % (p.pid, int(time.time())))
    atomic_write(d / "start", starttime_of(p.pid))
    try:
        watch(tag, a.timeout, a.interval, a.file, a.min_size,
              a.size_stable, a.grep_done, a.grep_block)
    finally:
        if not a.no_wake and not other_active(tag):
            wake("unlock")


def do_wait(a):
    tag = a.tag
    d = dpaths(tag)
    if a.pid:
        atomic_write(d / "pid", "%d\n" % a.pid)
        atomic_write(d / "start", starttime_of(a.pid))
    watch(tag, a.timeout, a.interval, a.file, a.min_size,
          a.size_stable, a.grep_done, a.grep_block)


def do_peek(a):
    d = BASE / a.tag
    try:
        s = json.loads((d / "state").read_text())
    except Exception:
        die("no_state:%s" % a.tag)
    print("%-7s age=%ds pid=%s" % (s.get("status", "?"),
                                   int(time.time()) - s.get("ts", 0), s.get("pid", 0)))


def do_tail(a):
    d = BASE / a.tag
    t = tailtext(d / "log", a.bytes)
    if not t:
        die("no_log:%s" % a.tag)
    sys.stdout.write("\n".join(t.splitlines()[-a.lines:]) + "\n")


def do_ls(a):
    for p in sorted(BASE.glob("*/pid")):
        tag = p.parent.name
        try:
            pid = int(p.read_text().split()[0])
        except Exception:
            pid = 0
        st = (p.parent / "start").read_text().strip()
        try:
            state = json.loads((p.parent / "state").read_text()).get("status", "-")
        except Exception:
            state = "-"
        print("%-24s %-7s pid=%-8d %s" % (tag, state, pid,
                                          "ALIVE" if alive(pid, st) else "gone"))


def do_kill(a):
    d = BASE / a.tag
    try:
        pid = int((d / "pid").read_text().split()[0])
        st = (d / "start").read_text().strip()
    except Exception:
        die("no_pid:%s" % a.tag)
    if not alive(pid, st):
        print("ALREADY gone pid=%d" % pid)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        os.kill(pid, signal.SIGTERM)
    def mark(sig):
        try:
            sp = d / "state"
            js = json.loads(sp.read_text())
            js.update({"status": "KILLED", "ts": int(time.time()), "why": sig})
            atomic_write(sp, json.dumps(js, ensure_ascii=False))
        except Exception:
            pass

    for _ in range(20):
        if not alive(pid, st):
            mark("term"); print("KILLED pid=%d sig=TERM" % pid)
            return
        time.sleep(0.25)
    try:
        os.killpg(pid, signal.SIGKILL)
    except Exception:
        pass
    mark("kill"); print("KILLED pid=%d sig=KILL" % pid)


# ---------- CLI ----------
def build():
    ap = argparse.ArgumentParser(prog="taskwatch", description="长任务监听：一次调用阻塞到结论，只回 DONE / BLOCKED")
    sub = ap.add_subparsers(dest="sub", required=True)

    def common(s):
        s.add_argument("-t", "--tag", default=None)
        s.add_argument("--timeout", type=float, default=1800, help="监听上限秒，封顶 3300，超时不杀任务")
        s.add_argument("--interval", type=float, default=5.0)
        s.add_argument("--file", default=None, help="期望产物路径")
        s.add_argument("--min-size", type=int, default=0, help="产物下限字节")
        s.add_argument("--size-stable", type=float, default=15.0, help="无 pid 时大小稳定窗口秒")
        s.add_argument("--grep-done", default=None, help="日志命中即完成（正则）")
        s.add_argument("--grep-block", default=None, help="日志命中即阻塞，如交互提示（正则）")

    s = sub.add_parser("run", help="后台起命令并阻塞监听")
    common(s)
    s.add_argument("--no-wake", action="store_true", help="不取 wakelock")
    s.add_argument("cmd", nargs=argparse.REMAINDER)
    s.set_defaults(fn=do_run)

    s = sub.add_parser("wait", help="监听已在跑的任务")
    common(s)
    s.add_argument("--pid", type=int, default=0)
    s.set_defaults(fn=do_wait)

    s = sub.add_parser("peek", help="单次读状态，不阻塞")
    s.add_argument("-t", "--tag", required=True)
    s.set_defaults(fn=do_peek)

    s = sub.add_parser("tail", help="抓日志尾部")
    s.add_argument("-t", "--tag", required=True)
    s.add_argument("-n", "--lines", type=int, default=40)
    s.add_argument("--bytes", type=int, default=TAILB)
    s.set_defaults(fn=do_tail)

    s = sub.add_parser("ls", help="列出所有监听")
    s.set_defaults(fn=do_ls)

    s = sub.add_parser("kill", help="杀任务进程组（危险，显式调用）")
    s.add_argument("-t", "--tag", required=True)
    s.set_defaults(fn=do_kill)
    return ap


def main():
    a = build().parse_args()
    if a.sub == "run":
        a.cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if getattr(a, "timeout", 0) > CAP:
        a.timeout = CAP
    if getattr(a, "interval", 1) <= 0:
        a.interval = 5.0
    BASE.mkdir(parents=True, exist_ok=True)

    def on_sig(sig, frm):
        print("BLOCKED 0s why=interrupted", flush=True)
        os._exit(1)

    signal.signal(signal.SIGINT, on_sig)
    signal.signal(signal.SIGTERM, on_sig)
    a.fn(a)


if __name__ == "__main__":
    main()
