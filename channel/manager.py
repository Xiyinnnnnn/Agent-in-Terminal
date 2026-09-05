#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent-in-Terminal Channel Manager
微信/QQ → Channel Manager → 每条消息独立新 Agent 进程 → channel-reply / channel-send-file 回原会话

设计原则（任务书）：
- 不改 term_agent.py 本体；不加数据库/Redis/daemon/systemd/全局队列。
- 并发不串会话：每个 task 独立 socket + 独立进程。
- stdout=工作报告；channel-reply=主动聊天；channel-send-file=发文件。
- 未主动 reply 时，把最终 stdout 作为一次普通回复（去重）。
"""
import json, os, re, sys, uuid, socket, subprocess, threading, shutil, time, atexit, signal

REPO   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE   = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("CHANNEL_CONFIG", os.path.join(HERE, "config.json"))

DEFAULT_CONFIG = {
    "agent": "./term_agent.py",
    "multimodal": True,
    "runtime_dir": "/tmp/agent-channel",
    "allowed_file_dirs": ["/tmp/agent-channel", REPO],
    "task_timeout": 1200,        # Agent 超时（秒）
    "max_file_mb": 200,          # channel-send-file 大小上限
    "exit_grace": 3,             # 任务结束后清理前等待秒
    "adapters": ["local"],       # 启用的适配器：local / wechat / qq
    "wechat": {},
    "qq": {},
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            cfg.update(json.load(open(CONFIG_PATH, encoding="utf-8")))
        except Exception as e:
            print(f"[Channel] 配置读取失败: {e}", file=sys.stderr)
    return cfg

def sanitize_text(t):
    """把消息压成单物理行（input() 每次只读一行），换行折叠为空格。"""
    if not t: return ""
    return re.sub(r"[ \t]*[\r\n]+[ \t]*", " ", str(t)).strip()

def strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)

def get_agent_note():
    return ("\n[运行环境] 你可以用 Shell 调用 `channel-reply \"回复内容\"` 向当前聊天主动发文字，"
            "用 `channel-send-file \"/绝对路径/文件\"` 向当前聊天发文件（可多次调用）。"
            "不要直接调用微信/QQ API。")

# ---------- 统一消息模型 ----------
def make_message(platform, conversation_id, sender_id, message_id, text, attachments=None):
    return {
        "platform": platform,
        "conversation_id": conversation_id,
        "sender_id": sender_id,
        "message_id": message_id,
        "text": text,
        "attachments": attachments or [],
    }

# ---------- Socket 协议服务 ----------
# Agent → Manager（JSON Lines, 一次一帧）:
#   {"type":"reply","text":"..."}
#   {"type":"file","path":"/abs/path"}
# Manager 应答: {"ok":true} 或 {"ok":false,"error":"..."}
class TaskSocket:
    def __init__(self, task, cfg):
        self.task, self.cfg = task, cfg
        self.path = task["socket_path"]
        self.server = None
        self.thread = None
        self.lock = threading.Lock()
        self._stop = threading.Event()

    def start(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        os.chmod(self.path, 0o600)
        self.server.listen(8)
        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()

    def _accept_loop(self):
        self.server.settimeout(0.5)
        while not self._stop.is_set():
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn):
        try:
            conn.settimeout(10)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk: break
                data += chunk
            line = data.split(b"\n", 1)[0].decode("utf-8", "ignore").strip()
            resp = self._dispatch(line)
            try:
                conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass
        except Exception as e:
            try: conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode("utf-8"))
            except Exception: pass
        finally:
            conn.close()

    def _dispatch(self, line):
        if not line:
            return {"ok": False, "error": "空请求"}
        try:
            req = json.loads(line)
        except Exception:
            return {"ok": False, "error": "JSON 解析失败"}
        t = req.get("type")
        if t == "reply":
            text = sanitize_text(req.get("text"))
            if not text: return {"ok": False, "error": "空回复文本"}
            try:
                self.task["manager"].reply(self.task, text)
                with self.lock: self.task["replied"] = True
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        if t == "file":
            path = (req.get("path") or "").strip()
            try:
                self.task["manager"].send_file(self.task, path)
                return {"ok": True}
            except Exception as e:
                return {"ok": False, "error": str(e)}
        return {"ok": False, "error": f"未知类型 {t}"}

    def close(self):
        self._stop.set()
        if self.server:
            try: self.server.close()
            except Exception: pass
        if os.path.exists(self.path):
            try: os.unlink(self.path)
            except Exception: pass

# ---------- Channel Manager ----------
class ChannelManager:
    def __init__(self, cfg):
        self.cfg = cfg
        self.tasks = {}            # task_id -> task dict
        self.tlock = threading.Lock()
        self.adapters = {}
        self._load_runtime_dirs()

    # -- 目录 --
    def _base(self, *p): return os.path.join(self.cfg["runtime_dir"], *p)
    def inbox(self, tid): return self._base("inbox", tid)
    def runtime(self, tid): return self._base("runtime", tid)

    def _load_runtime_dirs(self):
        for d in ("inbox", "runtime"):
            os.makedirs(self._base(d), exist_ok=True)

    # -- 接收消息（由 Adapter 回调）--
    def on_message(self, msg):
        if not (msg.get("text") or msg.get("attachments")):
            return  # 空消息忽略
        threading.Thread(target=self._handle_message, args=(msg,), daemon=True).start()

    def _handle_message(self, msg):
        task_id = uuid.uuid4().hex[:12]
        task = {
            "task_id": task_id,
            "msg": msg,
            "cfg": self.cfg,
            "manager": self,
            "socket_path": self.runtime(task_id) + "/api.sock",
            "replied": False,
            "stdout": "",
            "adapter": msg.get("platform"),
            "process": None,
        }
        with self.tlock: self.tasks[task_id] = task
        try:
            self._run_agent(task)
        except Exception as e:
            self._send_error(task, f"Agent 启动失败：{e}")
        finally:
            with self.tlock: self.tasks.pop(task_id, None)
            self._cleanup(task)

    # -- Agent 生命周期 --
    def _run_agent(self, task):
        # 1. 任务目录 + 下载附件
        inbox, rt = self.inbox(task["task_id"]), task["socket_path"]
        os.makedirs(os.path.dirname(rt), exist_ok=True)
        inbox_paths = self._collect_attachments(task, inbox)

        # 2. Socket
        tsock = TaskSocket(task, self.cfg)
        task["tsock"] = tsock
        tsock.start()

        # 3. 构造一次性任务文本（单物理行）
        lines = []
        text = sanitize_text(task["msg"].get("text"))
        if self.cfg.get("multimodal"):
            imgs = [p for p in inbox_paths if p.lower().endswith((".jpg",".jpeg",".png",".gif",".webp"))]
            files = [p for p in inbox_paths if p.lower() not in (".jpg",".jpeg",".png",".gif",".webp")]
            if imgs:  lines.append("[图片] " + " ".join(imgs))
            if files: lines.append("[附件] " + " ".join(files))
        else:
            if inbox_paths:
                lines.append("[附件] " + " ".join(inbox_paths))
        if text:  lines.append(text)
        lines.append(get_agent_note())
        task_input = sanitize_text(" ".join(lines))

        # 4. spawn Agent 进程
        agent = self.cfg["agent"]
        agent_path = agent if os.path.isabs(agent) else os.path.join(REPO, agent)
        env = dict(os.environ)
        env["CHANNEL_TASK_ID"] = task["task_id"]
        env["CHANNEL_SOCKET"]  = task["socket_path"]
        proc = subprocess.Popen(
            [sys.executable, agent_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            cwd=os.path.dirname(agent_path), env=env, start_new_session=True,
        )
        task["process"] = proc

        # 5. 写任务 + 关 stdin
        try:
            proc.stdin.write(task_input + "\n")
            proc.stdin.flush()
        finally:
            proc.stdin.close()

        # 6. 收 stdout 直到退出 / 超时
        report = ""
        try:
            report = proc.communicate(timeout=self.cfg.get("task_timeout", 1200))[0] or ""
        except subprocess.TimeoutExpired:
            self._kill(proc)
            report = (proc.stdout.read() if proc.stdout else "") or ""
            task["stdout"] = report
            self._send_error(task, "Agent 超时，已终止")
            return
        task["stdout"] = report

        # 7. 未主动 reply → 把 stdout 作为一次回复（去重）
        if not task["replied"]:
            final = strip_ansi(report).strip()
            # 去掉过程噪音行，尽量取正文
            final = self._extract_final(final)
            if final:
                self.reply(task, final)
        self._cleanup_runtime(task)

    def _extract_final(self, s):
        """从 stdout 提取最终回复：去掉 你> / [工具] / [思维链] 等过程行。"""
        keep = []
        for ln in s.splitlines():
            st = ln.strip()
            if not st: continue
            if st in ("新终端=新对话 | Ctrl+Space=暂停", "再见"): continue
            if st.startswith("你> "): continue
            if st.startswith("[") and "]" in st[:6] and ("工具" in ln or "压缩" in ln or "正文" in ln or "思维链" in ln or "ANSI" in ln):
                continue
            keep.append(st)
        txt = "\n".join(keep)
        # 若整段是思考链格式，截掉 <thinking>...</thinking>
        m = re.search(r"</?thinking>.*?", txt, re.S)
        if m:
            txt = txt.replace(m.group(0), "").strip()
        return txt

    def _collect_attachments(self, task, inbox):
        """把消息里的附件(网络URL/本地路径)放到任务 inbox，返回本地绝对路径列表。"""
        os.makedirs(inbox, exist_ok=True)
        out = []
        att = task["msg"].get("attachments") or []
        for i, a in enumerate(att):
            if not a: continue
            try:
                if a.startswith(("http://", "https://")):
                    import urllib.request
                    name = os.path.basename(a.split("?")[0]) or f"att_{i}"
                    dest = os.path.join(inbox, f"{i}_{name}")
                    urllib.request.urlretrieve(a, dest)
                    out.append(dest)
                elif os.path.isfile(a):
                    dest = os.path.join(inbox, f"{i}_{os.path.basename(a)}")
                    shutil.copy2(a, dest)
                    out.append(dest)
            except Exception as e:
                print(f"[Channel] 附件下载失败 {a}: {e}", file=sys.stderr)
        return out

    def _cleanup(self, task):
        tsock = task.get("tsock")
        if tsock: 
            try: tsock.close()
            except Exception: pass
        self._cleanup_runtime(task)

    def _cleanup_runtime(self, task):
        tid = task["task_id"]
        for d in (self.inbox(tid), self.runtime(tid)):
            try: shutil.rmtree(d, ignore_errors=True)
            except Exception: pass

    def _kill(self, proc):
        try:
            import signal as _s
            if proc.poll() is None:
                os.killpg(proc.pid, _s.SIGKILL)
            proc.wait()
        except Exception:
            pass

    # -- 发送到聊天 --
    def _clean_reply(self, text):
        """清洗 Agent 回复：去掉通道侧混入的 '你> ' 提示符残影/前后空行。"""
        if not text: return text
        lines = text.split("\n")
        out = []
        for ln in lines:
            st = ln.strip()
            if st == "你>":     # 丢弃纯提示符残影行
                continue
            out.append(ln)
        t = "\n".join(out).strip()
        t = re.sub(r"(?:^|\n)\s*你>\s*", "", t)   # 行首兜底
        t = t.replace("\\n", "\n")                # 字面 \n 转真实换行
        return t.strip()

    def reply(self, task, text):
        text = self._clean_reply(text)
        ad = self.adapters.get(task["msg"]["platform"])
        if ad is None: raise RuntimeError(f"无适配器: {task['msg']['platform']}")
        ad.send_text(task["msg"], text)

    def send_file(self, task, raw_path):
        path = self._verify_path(task, raw_path)
        ad = self.adapters.get(task["msg"]["platform"])
        if ad is None: raise RuntimeError(f"无适配器: {task['msg']['platform']}")
        ad.send_file(task["msg"], path)

    def _verify_path(self, task, raw_path):
        path = os.path.realpath(os.path.expanduser(raw_path or ""))
        if not os.path.exists(path):
            raise RuntimeError(f"文件不存在: {raw_path}")
        if not os.access(path, os.R_OK):
            raise RuntimeError(f"文件不可读: {raw_path}")
        if not os.path.isfile(path):
            raise RuntimeError(f"不是普通文件: {raw_path}")
        allow = [os.path.realpath(d) for d in self.cfg.get("allowed_file_dirs", [])]
        allow.append(os.path.realpath(self.runtime(task["task_id"])))  # 至少允许本任务 runtime
        if not any(path == a or path.startswith(a + os.sep) for a in allow):
            raise RuntimeError(f"路径不在允许目录内: {raw_path}")
        if os.path.getsize(path) > self.cfg.get("max_file_mb", 200) * 1024 * 1024:
            raise RuntimeError(f"文件过大: {raw_path}")
        return path

    def _send_error(self, task, msg):
        try:
            ad = self.adapters.get(task["msg"]["platform"])
            if ad: ad.send_text(task["msg"], f"[Channel 错误] {msg}")
        except Exception as e:
            print(f"[Channel] 错误回传失败: {e}", file=sys.stderr)

    # -- Adapter 注册/启动 --
    def load_adapters(self):
        from adapters import create_adapters
        for name, ad in create_adapters(self.cfg).items():
            if name not in self.cfg.get("adapters", []):
                continue
            try:
                ad.attach(self)
                self.adapters[name] = ad
            except Exception as e:
                # 单个适配器启动失败(如端口被占)绝不拖垮 manager 与其他通道
                print(f"[Channel] 适配器 {name} 启动失败，已跳过（其余通道不受影响）: {e}",
                      file=sys.stderr, flush=True)

    def run(self):
        self.load_adapters()
        print(f"[Channel] Manager 启动 | 适配器: {list(self.adapters)} | runtime: {self.cfg['runtime_dir']}", flush=True)
        self._install_signal()
        self._keep_alive()
        self._shutdown_adapters()

    def _install_signal(self):
        import signal as _sig
        try:
            _sig.signal(_sig.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
            _sig.signal(_sig.SIGINT,  lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
        except Exception:
            pass

    def _keep_alive(self):
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[Channel] 正在退出，终止运行中的任务…", flush=True)
            self._kill_all_tasks()

    def _kill_all_tasks(self):
        """退出时清杀所有 Agent 子进程，防止 manager 停止后任务成孤儿残留。"""
        with self.tlock:
            procs = [t.get("process") for t in list(self.tasks.values()) if t.get("process")]
        killed = 0
        for proc in procs:
            try:
                if proc and proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)   # Agent start_new_session=True → killpg 整组
                    killed += 1
            except Exception:
                pass
        if killed:
            print(f"[Channel] 已终止 {killed} 个运行中的 Agent 任务", flush=True)
        time.sleep(1)   # 给任务线程收尾时间

    def _shutdown_adapters(self):
        for name, ad in list(self.adapters.items()):
            try:
                ad.stop()
            except Exception as e:
                print(f"[Channel] 适配器 {name} 停止失败: {e}", file=sys.stderr, flush=True)

def main():
    cfg = load_config()
    m = ChannelManager(cfg)
    if "--test" in sys.argv:
        m.load_adapters()
        idx = sys.argv.index("--test")
        text = " ".join(sys.argv[idx+1:]).strip() or "测试任务"
        print(f"[Channel] 注入本地测试消息: {text}")
        m.on_message(make_message("local", "test-conv", "local-user", "m1", text, _attachments_from_args(cfg)))
        # 等待任务结束
        while m.tasks:
            time.sleep(0.5)
        print("[Channel] 测试完成", flush=True)
        return
    if "--serve" in sys.argv:
        m.run(); return
    # 默认 serve
    m.run()

def _attachments_from_args(cfg):
    out = []
    for a in sys.argv[1:]:
        if a.startswith("--test"): continue
        if a.startswith("--"): continue
        out.append(a)
    att = []
    for p in out:
        if os.path.exists(p): att.append(os.path.realpath(p))
    return att

if __name__ == "__main__":
    main()
