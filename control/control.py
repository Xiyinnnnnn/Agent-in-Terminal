#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-in-Terminal Channel 傻瓜控制中心（零第三方依赖，标准库 TUI）

职责（只做控制层，不碰 Agent Core / Channel 核心逻辑）：
  - start / stop / status  Channel Manager（PID 文件方式，防重复启动）
  - 微信 / QQ 登录状态查看与接入指引（登录协议仍归各自 Adapter）
  - 多模态 ON/OFF（持久化到现有 channel/config.json，只影响新任务）
  - 查看最近日志
  - 桌面统一入口：Agent Channel

启动：python3 control/control.py
"""
import json, os, re, signal, socket, subprocess, sys, time

# ---- 路径：全部基于本文件自身位置定位，不硬编码用户名 ----
HERE   = os.path.dirname(os.path.abspath(__file__))          # repo/control
REPO   = os.path.dirname(HERE)                               # repo
CH_DIR = os.path.join(REPO, "channel")                       # repo/channel
CONFIG = os.path.join(CH_DIR, "config.json")                 # 复用现有配置（唯一一份）
MANAGER = os.path.join(CH_DIR, "manager.py")
LOG_DIR = "/tmp/agent-channel"
PID_FILE = os.path.join(LOG_DIR, "channel.pid")
STATE_FILE = os.path.join(LOG_DIR, "channel.state.json")     # 运行态元数据（PID/启动时间/适配器）
LOG_FILE = os.path.join(LOG_DIR, "channel.log")
OUTBOX_LOG = os.path.join(LOG_DIR, "outbox-local.log")

GREEN, YELLOW, RED, CYAN, BOLD, NC = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[1m", "\033[0m"

def c(s, color): return f"{color}{s}{NC}"

def _dw(s):
    """等宽终端下按显示宽度取字符串（中文/全角算2）。"""
    w = 0
    for ch in s:
        if ord(ch) > 0x2E7F:  # 非 ASCII 可见区按全角 2 计
            w += 2
        else:
            w += 1
    return w

def _pad(s, width):
    return s + " " * max(0, width - _dw(s))

def _strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)

# ---------------- 配置 ----------------
def load_config():
    if os.path.exists(CONFIG):
        try:
            with open(CONFIG, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(c(f"[配置读取失败] {e}", RED))
    return {}

def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.chmod(CONFIG, 0o600)

# ---------------- Channel 进程状态 ----------------
def _read_pid():
    try:
        with open(PID_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except Exception:
        return None

def _pid_alive(pid):
    if not pid: return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def _is_manager(pid):
    """确认 pid 确实是 channel/manager.py（防误杀别的进程）。"""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmd = f.read().decode("utf-8", "ignore").replace("\x00", " ")
        return "channel/manager.py" in cmd or "manager.py" in cmd
    except Exception:
        return False

def channel_status():
    """返回 (state, info)；state ∈ running/stopped/stale"""
    pid = _read_pid()
    if pid and _pid_alive(pid):
        if _is_manager(pid):
            return "running", {"pid": pid}
        # PID 活着但不是 manager（被别的进程占用）→ 视为残留
        return "stale", {"pid": pid, "reason": "PID 文件指向非 manager 进程"}
    if pid:
        return "stale", {"pid": pid, "reason": "残留 PID（进程已退出）"}
    # 没有 pid 文件，再兜底找一次（例如手动起的 manager）
    try:
        out = subprocess.run(["pgrep", "-f", "channel/manager.py --serve"],
                             capture_output=True, text=True).stdout.strip()
        if out:
            p = int(out.splitlines()[0])
            return "running", {"pid": p, "note": "无PID文件但检测到运行中的 manager"}
    except Exception:
        pass
    return "stopped", {}

def _clear_stale():
    for f in (PID_FILE, STATE_FILE):
        try:
            if os.path.exists(f): os.remove(f)
        except Exception:
            pass

# ---------------- 日志（复用 /tmp/agent-channel） ----------------
def tail_file(path, n=40):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return "(暂无日志)"

# ---------------- 微信 / QQ 登录状态 ----------------
def _port_open(host, port, timeout=0.5):
    try:
        s = socket.create_connection((host, int(port)), timeout=timeout)
        s.close()
        return True
    except OSError:
        return False

def adapter_login_state():
    """登录状态判定：适配器配置存在 + 对应后端可达。
    QQ:    需要外部 OneBot 实现(NapCat/Lagrange)，webhook 端口默认 18086，正向 API 默认 3000
    微信:  需要外部 iLink/微信事件推送，webhook 端口默认 18087
    控制中心只做判定与接入指引；不重新实现登录协议。"""
    cfg = load_config()
    state = {}
    # ---- QQ ----
    qq = cfg.get("qq") or {}
    qq_api = (qq.get("onebot_http") or "").strip()
    qq_port = (qq.get("webhook_local") or "127.0.0.1:18086").rsplit(":", 1)[-1]
    if qq.get("bot_qq") and qq_api and _port_open("127.0.0.1", qq_port):
        state["qq"] = {"level": "ok", "bot": qq.get("bot_qq"), "api": qq_api}
    elif qq.get("bot_qq") and qq_api:
        state["qq"] = {"level": "half", "bot": qq.get("bot_qq"), "api": qq_api,
                       "hint": "已配置，但 OneBot 后端(NapCat/Lagrange)未在本机 webhook 端口监听"}
    else:
        state["qq"] = {"level": "none", "hint": "未配置 bot_qq / onebot_http"}
    # ---- 微信 ----
    wx = cfg.get("wechat") or {}
    wx_ilk = (wx.get("ilk") or "").strip()
    wx_port = (wx.get("webhook_local") or "127.0.0.1:18087").rsplit(":", 1)[-1]
    if wx_ilk and wx.get("access_token") and _port_open("127.0.0.1", wx_port):
        state["wechat"] = {"level": "ok", "ilk": wx_ilk}
    elif wx_ilk and wx.get("access_token"):
        state["wechat"] = {"level": "half", "ilk": wx_ilk,
                           "hint": "已配置，但微信 iLink/事件推送未到达本机 webhook 端口"}
    else:
        state["wechat"] = {"level": "none", "hint": "未配置 wechat.ilk / access_token"}
    return state

def _wx_login_guide():
    print()
    print(c("微信接入说明（登录协议属于 WeChat Adapter，控制中心只负责指引）", BOLD))
    print("  微信通道采用 iLink / 微信客服消息方向，需你在微信侧完成：")
    print("   1. 微信开放平台/企业微信创建应用，获得 access_token")
    print("   2. 配置事件推送 → 指向本机 webhook（默认 127.0.0.1:18087/ilink）")
    print("   3. 把应用信息填入 repo/channel/config.json 的 wechat 段：")
    print('      { "ilk": "https://iLink端点/api/cgi-bin/message",')
    print('        "access_token": "xxx",')
    print('        "webhook_local": "127.0.0.1:18087", "webhook_path": "/ilink" }')
    print(c("  填写后回到本界面选 [2] 刷新即可看到「● 已配置」；真实可用还需微信侧能推送到本机。", YELLOW))

def _qq_login_guide():
    print()
    print(c("QQ 接入说明（登录协议属于 QQ Adapter，控制中心只负责指引）", BOLD))
    print("  QQ 通道走 OneBot11 反向HTTP，需要先跑起一个 OneBot 实现（NapCat 或 Lagrange）：")
    print("   1. 安装并登录 NapCat/Lagrange（扫码登录 QQ，登录态由它持久保存）")
    print("   2. 开启 反向HTTP 上报 → 指向 本机 webhook（默认 127.0.0.1:18086/onebot）")
    print("   3. 记下正向 HTTP API 地址（默认 http://127.0.0.1:3000）")
    print("   4. 把信息填入 repo/channel/config.json 的 qq 段：")
    print('      { "bot_qq": "你的QQ号", "onebot_http": "http://127.0.0.1:3000",')
    print('        "webhook_local": "127.0.0.1:18086", "webhook_path": "/onebot" }')
    print(c("  填写并跑起后端后回本界面选 [2] 刷新即可看到「● 已登录」。", YELLOW))

# ---------------- start / stop ----------------
def start_channel():
    state, info = channel_status()
    if state == "running":
        print(c(f"Channel 已在运行中 (PID {info.get('pid')})，无需重复启动。", GREEN))
        return False
    if state == "stale":
        print(c(f"检测到残留状态：{info.get('reason')} → 自动清理。", YELLOW))
        _clear_stale()
    os.makedirs(LOG_DIR, exist_ok=True)
    py = sys.executable
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    # nohup 风格：脱离终端，日志落 /tmp/agent-channel/channel.log
    with open(LOG_FILE, "a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [py, MANAGER, "--serve"],
            cwd=CH_DIR, env=env,
            stdout=logf, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    # 写 PID 文件
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    # 等 1.2s 确认没立刻崩
    time.sleep(1.2)
    if proc.poll() is not None:
        _clear_stale()
        tail = tail_file(LOG_FILE, 10)
        print(c("Channel 启动失败（进程已退出）。最近日志：", RED))
        print(tail)
        return False
    print(c(f"Channel 已启动 (PID {proc.pid})。", GREEN))
    print("  日志: " + LOG_FILE)
    return True

def stop_channel():
    state, info = channel_status()
    if state == "stopped":
        print(c("Channel 未运行。", YELLOW))
        return False
    if state == "stale":
        print(c(f"残留状态：{info.get('reason')} → 清理，无需停止。", YELLOW))
        _clear_stale()
        return True
    pid = info["pid"]
    print(c(f"正在停止 Channel (PID {pid})…", CYAN))
    # 1) SIGTERM 正常关闭（manager 的 KeyboardInterrupt 处理会触发退出打印）
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(c(f"发送 SIGTERM 失败: {e}", RED))
    # 2) 等待正常退出（最多 5s）
    for _ in range(25):
        if not _pid_alive(pid):
            break
        time.sleep(0.2)
    # 3) 必要时 terminate → 最后才是 kill
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        time.sleep(1)
    if _pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        print(c("进程未在宽限期内退出，已强制结束。", YELLOW))
    else:
        print(c("Channel 已正常退出。", GREEN))
    # 4) 清理 PID / 状态
    _clear_stale()
    return True

def multimodal_state():
    cfg = load_config()
    return bool(cfg.get("multimodal", True))

def toggle_multimodal():
    cfg = load_config()
    cur = bool(cfg.get("multimodal", True))
    cfg["multimodal"] = not cur
    save_config(cfg)
    now = "ON" if cfg["multimodal"] else "OFF"
    print(c(f"多模态已切换为 {now}。", GREEN))
    print(c("  仅对新启动的 Agent 任务生效，当前正在执行的任务不受影响。", YELLOW))
    return cfg["multimodal"]

# ---------------- 首页 ----------------
def _dot(ok):
    return c("●", GREEN) if ok else c("○", RED)

def status_line():
    st, info = channel_status()
    ls = adapter_login_state()
    qq, wx = ls.get("qq"), ls.get("wechat")
    mm = multimodal_state()
    return st, info, qq, wx, mm

def render():
    st, info, qq, wx, mm = status_line()
    # Channel 行
    if st == "running":
        ch_line = c("● 运行中", GREEN) + c(f"   (PID {info.get('pid')})", NC)
    elif st == "stale":
        ch_line = c("! 异常(残留)", RED) + c(f"   {info.get('reason','')}", NC)
    else:
        ch_line = c("○ 未运行", RED)
    # 登录状态行
    qq_lv = qq.get("level", "none")
    wx_lv = wx.get("level", "none")
    if qq_lv == "ok": qq_line = c("● 已登录", GREEN) + c(f"  bot={qq.get('bot')}", NC)
    elif qq_lv == "half": qq_line = c("! 已配置/后端未连", YELLOW)
    else: qq_line = c("○ 未接入", RED)
    if wx_lv == "ok": wx_line = c("● 已配置", GREEN)
    elif wx_lv == "half": wx_line = c("! 已配置/未到达", YELLOW)
    else: wx_line = c("○ 未接入", RED)
    mm_line = c("● ON", GREEN) if mm else c("○ OFF", RED)

    w = 56
    print(c("╔" + "═"*(w-2) + "╗", CYAN))
    title = " Agent-in-Terminal Channel "
    pad = w - 2 - len(title)
    print(c("║" + " "*max(0,(pad//2)) + title + " "*max(0,pad-pad//2) + "║", CYAN))
    print(c("╠" + "═"*(w-2) + "╣", CYAN))
    def row(k, v):
        plain = _strip_ansi(f" {k}") + _strip_ansi(v)
        kk = " " + k
        body = kk + " " + v
        fill = w - 2 - _dw(plain) - 1   # 右边框前至少1空格
        print(c("║" + body + " " * max(0, fill) + "║", CYAN))
    row("Channel", ch_line)
    row("QQ", qq_line)
    row("微信", wx_line)
    row("多模态", mm_line)
    print(c("╠" + "═"*(w-2) + "╣", CYAN))
    menu = [
        ("1", "启动 / 停止 Channel"),
        ("2", "微信 / QQ 登录 (查看/指引)"),
        ("3", "多模态 ON / OFF"),
        ("4", "查看最近日志"),
        ("5", "刷新状态"),
        ("0", "退出"),
    ]
    for k, t in menu:
        row(k, c(t, NC))
    print(c("╚" + "═"*(w-2) + "╝", CYAN))
    if st != "running":
        print(c("提示：Channel 未运行 → 按 [1] 启动。启动后微信/QQ 消息才会触发 Agent。", YELLOW))
    print()

def _pause():
    try:
        input(c("按回车返回…", CYAN))
    except EOFError:
        pass

def act_start_stop():
    st, info, *_ = status_line()
    if st == "running":
        stop_channel()
    else:
        start_channel()
    _pause()

def act_login():
    st, info, qq, wx, mm = status_line()
    print()
    print(c("微信 / QQ 登录状态", BOLD))
    wx_lv = wx.get("level", "none")
    qq_lv = qq.get("level", "none")
    print(f"  微信：{'● 已配置(接收可达)' if wx_lv=='ok' else ('! 已配置/推送未到达' if wx_lv=='half' else '○ 未接入')}")
    if wx_lv == "half" and wx.get("hint"): print(c("        " + wx["hint"], YELLOW))
    print(f"  QQ ：{'● 已登录(后端可达)' if qq_lv=='ok' else ('! 已配置/后端未连' if qq_lv=='half' else '○ 未接入')}")
    if qq_lv == "half" and qq.get("hint"): print(c("        " + qq["hint"], YELLOW))
    print(c("  ─────────────────────────────────", NC))
    print("  登录态由各自 Adapter / 外部后端负责，控制中心不保存密码或 token：")
    print("  · 微信登录态 → iLink 应用（首次扫码授权由微信侧完成）")
    print("  · QQ 登录态  → NapCat/Lagrange 扫码登录，登录态由它们持久保存")
    while True:
        print()
        print("  [w] 微信接入指引    [q] QQ 接入指引    [r] 刷新    [0] 返回")
        k = input("  选择: ").strip().lower()
        if k in ("w", "微信"): _wx_login_guide()
        elif k in ("q", "qq"): _qq_login_guide()
        elif k == "r": return act_login()
        elif k in ("0", ""): return
        else: print(c("  无效输入。", YELLOW))

def act_log():
    print()
    print(c("最近日志（/tmp/agent-channel/channel.log 末尾 40 行）", BOLD))
    print("-"*56)
    print(tail_file(LOG_FILE, 40))
    if os.path.exists(OUTBOX_LOG):
        print(c("本地回复记录 outbox-local.log 末尾 10 行", BOLD))
        print("-"*56)
        print(tail_file(OUTBOX_LOG, 10))
    _pause()

def main():
    # 兼容单参数子命令：control.py --status / --start / --stop（给脚本/快捷用）
    if len(sys.argv) > 1:
        a = sys.argv[1]
        if a in ("--status", "status"):
            st, info = channel_status()
            print(json.dumps({"state": st, **info}, ensure_ascii=False))
            return
        if a in ("--start", "start"):
            sys.exit(0 if start_channel() else 1)
        if a in ("--stop", "stop"):
            sys.exit(0 if stop_channel() else 1)
    while True:
        os.system("clear" if os.name == "posix" else "cls")
        render()
        try:
            k = input("  选择 [1-5 / 0]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  再见。"); return
        if k == "1": act_start_stop()
        elif k == "2": act_login()
        elif k == "3":
            toggle_multimodal(); _pause()
        elif k == "4": act_log()
        elif k == "5": continue
        elif k == "0": print("  再见。"); return
        else: print(c("  无效输入，请按菜单数字。", YELLOW)); time.sleep(0.8)

if __name__ == "__main__":
    main()
