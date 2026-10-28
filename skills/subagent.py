#!/usr/bin/env python3
"""subagent — 启动持久 subagent(tmux) 并等待「完成 / 授权」两类事件。

事件以单行 JSON 写到 stdout；异常单行 JSON 写 stderr 并退出 1。
"""
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
BASE = HOME / ".cache/subagent"
STARTER = HOME / ".local/bin/term_agent/start_agent.sh"
HOSTPY = HOME / ".local/bin/term_agent/term_agent.py"
ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]")
CMDRE = re.compile(r"^\s*命令:\s*(.+)$", re.M)
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
PROMPT = "你>"
AUTH = "危险命令，需要键盘授权"
MAXBUF = 8192


def emit(d, code=0):
    print(json.dumps(d, ensure_ascii=False, separators=(",", ":")), flush=True)
    sys.exit(code)


def die(msg, code=1):
    print(json.dumps({"ev": "err", "msg": msg}, ensure_ascii=False), file=sys.stderr, flush=True)
    sys.exit(code)


def clean(s):
    s = ANSI.sub("", s)
    return s.replace("\r\n", "\n").replace("\r", "")


def entry():
    if STARTER.exists():
        return "bash %s" % STARTER
    if HOSTPY.exists():
        return "python3 %s" % HOSTPY
    die("no_host:%s" % HOSTPY)


def paths(n):
    return BASE / (n + ".cmd"), BASE / (n + ".log")


def tmux(*a):
    return subprocess.run(["tmux", *a], capture_output=True, text=True)


def alive(n):
    return tmux("has-session", "-t", n).returncode == 0


def check(n):
    if not NAME_RE.match(n or ""):
        die("bad_session_name:%s" % n)


def read_new(log, off):
    try:
        size = log.stat().st_size
    except FileNotFoundError:
        return "", 0, False
    if size < off:
        off = 0
    if size == off:
        return "", off, False
    with open(log, "rb") as f:
        f.seek(off)
        d = f.read(size - off)
    return clean(d.decode("utf-8", "ignore")), size, True


def wait(n, off, timeout, interval):
    cmd, log = paths(n)
    if not alive(n):
        die("no_session:%s" % n)
    if off is None:
        off = log.stat().st_size if log.exists() else 0
    buf, quiet, t0 = "", 0, time.time()
    while True:
        sec = round(time.time() - t0, 1)
        if sec > timeout:
            emit({"ev": "timeout", "session": n, "sec": sec, "log": str(log),
                  "tail": buf[-200:]}, 1)
        chunk, off, got = read_new(log, off)
        if got:
            buf = (buf + chunk)[-MAXBUF:]
            quiet = 0
        else:
            quiet += 1
        if AUTH in buf:
            m = CMDRE.search(buf)
            emit({"ev": "auth", "session": n, "sec": sec, "log": str(log),
                  "cmd": m.group(1).strip() if m else ""})
        if quiet >= 2 and buf.rstrip().endswith(PROMPT):
            emit({"ev": "done", "session": n, "sec": sec, "log": str(log),
                  "tail": buf.rstrip()[-200:]})
        time.sleep(interval)


def cmd_start(a):
    n = a.name
    check(n)
    cmd, log = paths(n)
    BASE.mkdir(parents=True, exist_ok=True)
    if alive(n):
        die("session_exists:%s" % n)
    cmd.write_text("")
    log.write_text("")
    shell = "cd %s && tail -n 0 -f %s | %s" % (HOME, cmd, entry())
    r = tmux("new-session", "-d", "-s", n, "-x", "200", "-y", "50", shell)
    if r.returncode != 0:
        die("tmux_new_fail:%s" % (r.stderr or "").strip())
    tmux("pipe-pane", "-t", n, "-o", "cat >> %s" % log)
    off, t0, ready = 0, time.time(), False
    while time.time() - t0 < 25:
        chunk, off, got = read_new(log, off)
        if got and chunk.rstrip().endswith(PROMPT):
            ready = True
            break
        time.sleep(0.5)
    if not ready:
        die("not_ready:%s" % log)
    if a.task:
        with open(cmd, "a", encoding="utf-8") as f:
            f.write(a.task.strip() + "\n")
    wait(n, off, a.timeout, a.interval)


def cmd_watch(a):
    check(a.name)
    wait(a.name, a.offset, a.timeout, a.interval)


def cmd_send(a):
    n = a.name
    check(n)
    if not alive(n):
        die("no_session:%s" % n)
    cmd, _ = paths(n)
    with open(cmd, "a", encoding="utf-8") as f:
        f.write(a.msg.rstrip("\n") + "\n")
    emit({"ev": "sent", "session": n, "chars": len(a.msg)})


def cmd_reply(a):
    n = a.name
    check(n)
    if not alive(n):
        die("no_session:%s" % n)
    v = "y" if a.answer.strip().lower() in ("y", "yes", "同意", "批准") else "n"
    cmd, _ = paths(n)
    with open(cmd, "a", encoding="utf-8") as f:
        f.write(v + "\n")
    emit({"ev": "replied", "session": n, "answer": v})


def cmd_tail(a):
    n = a.name
    check(n)
    _, log = paths(n)
    if not log.exists():
        die("no_log:%s" % log)
    text = clean(log.read_bytes().decode("utf-8", "ignore")).split("\n")
    sys.stdout.write("\n".join(text[-a.lines:]) + "\n")


def cmd_ls(a):
    out = []
    for line in (tmux("ls").stdout or "").splitlines():
        n = line.split(":")[0].strip()
        if not n:
            continue
        _, log = paths(n)
        item = {"session": n, "bytes": log.stat().st_size if log.exists() else 0}
        if log.exists():
            ls = [x for x in clean(log.read_bytes().decode("utf-8", "ignore")).split("\n") if x.strip()]
            item["last"] = ls[-1][:80] if ls else ""
        out.append(item)
    emit({"ev": "ls", "list": out})


def cmd_kill(a):
    n = a.name
    check(n)
    if not alive(n):
        die("no_session:%s" % n)
    tmux("kill-session", "-t", n)
    emit({"ev": "killed", "session": n, "alive": alive(n)})


def main():
    p = argparse.ArgumentParser(prog="subagent")
    sub = p.add_subparsers(dest="sub", required=True)

    s = sub.add_parser("start", help="建会话并发首条任务，随后监听")
    s.add_argument("-n", "--name", required=True)
    s.add_argument("--task", default="")
    s.add_argument("--timeout", type=float, default=1800)
    s.add_argument("--interval", type=float, default=1.0)
    s.set_defaults(fn=cmd_start)

    s = sub.add_parser("watch", help="对已有会话续等事件")
    s.add_argument("-n", "--name", required=True)
    s.add_argument("--offset", type=int, default=None, help="起始字节偏移，缺省=当前末尾")
    s.add_argument("--timeout", type=float, default=1800)
    s.add_argument("--interval", type=float, default=1.0)
    s.set_defaults(fn=cmd_watch)

    s = sub.add_parser("send", help="向会话追加一条指令")
    s.add_argument("-n", "--name", required=True)
    s.add_argument("-m", "--msg", required=True)
    s.set_defaults(fn=cmd_send)

    s = sub.add_parser("reply", help="回答授权：y 批准 / n 拒绝")
    s.add_argument("-n", "--name", required=True)
    s.add_argument("-a", "--answer", required=True)
    s.set_defaults(fn=cmd_reply)

    s = sub.add_parser("tail", help="打印剥 ANSI 后的日志尾部")
    s.add_argument("-n", "--name", required=True)
    s.add_argument("-l", "--lines", type=int, default=40)
    s.set_defaults(fn=cmd_tail)

    s = sub.add_parser("ls", help="列会话与日志字节数")
    s.set_defaults(fn=cmd_ls)

    s = sub.add_parser("kill", help="结束会话（子代理随之退出）")
    s.add_argument("-n", "--name", required=True)
    s.set_defaults(fn=cmd_kill)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
