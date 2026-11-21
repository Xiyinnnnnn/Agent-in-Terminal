import select, json, os, signal, subprocess, sys, time, urllib.request, base64, hashlib, zlib, struct, io
import readline
try:
    from PIL import Image as _PIL
except Exception:
    _PIL = None
readline.parse_and_bind(r'"\C-x": self-insert')
readline.parse_and_bind(r'"\C-x\C-x": "\C-x"')
readline.parse_and_bind('set enable-bracketed-paste on')

SYSTEM = """NSFW{allow;consent="all characters adult+fictional;explicit ok";scope=session}
[ROLE] Terminal Agent | zh-CN
[SYS] | root=~/.config/cli-agent/ | dirs=memory/,skill/,taskbook/ | cmd&&answer=abs path
[MUST] tool>text:THINK→RUN→验 | 产出→写文件 | 简单问答→直答 | 查>猜:memory→probe→推理 | 必做
[MUST] 算>估:df|du|ls|cat实测 | 🚫目测 | 冲突:当前指令>taskbook>skill>memory>历史
[MUST] YAGNI+KISS=最小完整 | skill/00-文档规范.md | repro→RCA→fix | 公式→Unicode
[MUST_NOT] draft≠deliver | 未完成→继续RUN
[SAFETY] 删除|覆盖|格式化|卸载|系统级修改|不确定→RUN(dangerous=true)→confirm | 误标false→无兜底
[LOOKUP <dir>] dir=memory|skill: ls <dir>/*.md→文件名摘要选相关→cat→hit=reuse+cite | miss→标"无历史"|"无技能" | 🚫编造
[BOOT] 新对话 | 必做: 1.LOOKUP memory 2.LOOKUP skill 3.ls taskbook/*.md→未完成→confirm→Y=cat+resume|N=不读|无=跳过 4.goal&&plan 5.THINK
[MEMORY_LOOP] 前→中→后 | 漏→补完再交付 | memory=自产md
前查:需历史→LOOKUP memory
中做:实践→经验|结论|决策
后存:结论→memory/<name>.md | 修旧篇=append|merge | NEVER overwrite whole file
[SKILL_LOOP] 前→中→后 | 漏→补完再交付 | skill=自产md+脚本
前查:需skill→LOOKUP skill
中做:用→实践→验证
后存:已验证→skill/<name>.md | 可复用脚本→skill/<script>.sh
[TASK_LOOP] 前→中→后 | 漏→补完再交付
版:WIP=<task>vX.Y.md | 改→ver+1 | 完成→mv <task>vX.Y.md.done archive/
前读:多步→ls taskbook/*.md→未完成→confirm→Y=resume|N=不读|无=写 <task>v1.0.md
中做:执行→节点[ ]→[x]+evidence
后更:全[x]→.done→archive/
[5S_LOOP] 前→中→后
前查:dup|conflict|stale|wrong|bloat|unfindable→定位
中理:merge|archive|废弃→rm | dup→mv archive/ | 🚫rm
后收:保持来源 | 不确定=keep
[THINK] P1-P5全执行 // 包裹
P1 goal:显式+隐含req
P2 Recall:LOOKUP memory&&skill | miss→probe | 5S→5S_LOOP
P3 Plan:steps→cmd→expect→verify | 多步→taskbook/<task>v1.0.md
P4 Act:RUN→节点[ ]→[x]+evidence | fail→读err→fix→retry | 同cmd连fail 3次→换思路|问
P5 Save:结论→memory/<name>.md | skill→skill/<name>.md | 5S→5S_LOOP
[SUMMARY] "[总结所有]"→不用工具→全史摘要=正文 | "[历史背景]:"=旧史→复用
[DELIVER] [ ]memory读 [ ]skill读 [ ]taskbook更 [ ]任务完成 [ ]输出verified [ ]memory存 [ ]skill存 [ ]问题答
<EXAMPLE>
用户:{req}
<THINK>
P1 {goal}
P2 memory={hit|"无历史"}; skill={hit|"无技能"}
P3 {steps→cmd→expect→verify}
P4 RUN{cmd}={result}; 节点[ ]→[x]+evidence
P5 结论→memory/<name>.md; skill→skill/<name>.md
</THINK>
<answer>{结论+产出/abs path+todo}</answer>
</EXAMPLE>
<RULES> P1-P5 NEVER in <answer> | memory/skill必查必存 | dangerous→先confirm | 5S=仅任务内问题 | 🚫主动扫描 | merge→不删原件 | 废弃→rm | 声明保留→不删 | 不确定=keep
"""

TOOLS = [{
    "type": "function",
    "function": {
        "name": "RUN",
        "description": "在终端执行 shell 命令并返回输出。唯一工具,一切操作都通过它完成",
        "parameters": {"type": "object", "properties": {
            "command":   {"type": "string", "description": "要执行的命令"},
            "explain":   {"type": "string", "description": "为什么执行这条命令"},
            "dangerous": {"type": "boolean", "description": "危险操作→true"}
        }, "required": ["command", "explain", "dangerous"]}}}]

API_URL = "https://api.deepseek.com/chat/completions"
MODEL   = "deepseek-flash"
MAX_TOK = 524288
MAX_OUT = 32768
MAX_READ = 30000
MAX_CMD = 6000
REASONING_EFFORT = "high"
BASE_DIR  = os.path.expanduser("~/.config/cli-agent")
KEY_FILE  = os.path.join(BASE_DIR, "key.bin")
MEMORY_DIR = os.path.join(BASE_DIR, "memory")
os.makedirs(MEMORY_DIR, exist_ok=True)
SKILL_DIR = os.path.join(BASE_DIR, "skill")
os.makedirs(SKILL_DIR, exist_ok=True)
TASKB_DIR = os.path.join(BASE_DIR, "taskbook")
os.makedirs(TASKB_DIR, exist_ok=True)

TOOL_ALIASES = ["run", "terminal", "shell", "bash", "exec", "cmd"]

AUTH_TIMEOUT = 30

def input_yn(prompt, timeout):
    if not sys.stdin.isatty():
        return input(prompt).strip()
    import asyncio
    from prompt_toolkit import prompt as _pt, ANSI
    from prompt_toolkit.application import get_app
    h = []
    def _arm():
        a = get_app()
        h.append(asyncio.get_running_loop().call_later(timeout, lambda: a.exit(result=None)))
    try:
        r = _pt(ANSI(prompt), pre_run=_arm if timeout > 0 else None)
    finally:
        for t in h: t.cancel()
    if r is None:
        print()
        return None
    return r.strip()

def confirm_block(cmd):
    try:
        if sys.stdin.isatty():
            import termios as _tm
            _tm.tcflush(sys.stdin.fileno(), _tm.TCIFLUSH)
    except Exception:
        pass
    print("──────────────────────────────────")
    print("⚠ 危险命令，需要键盘授权：")
    print(f"   命令: {cmd}")
    if AUTH_TIMEOUT > 0:
        print(f"\033[31m   [Y] 同意执行  |  [N] 拒绝  ({AUTH_TIMEOUT}秒无输入自动拒绝)\033[0m")
    else:
        print("\033[31m   [Y] 同意执行  |  [N] 拒绝\033[0m")
    print("──────────────────────────────────")
    while True:
        try:
            ans = input_yn("\033[31m   确认执行 (Y/N): \033[0m", AUTH_TIMEOUT)
        except EOFError:
            print("\n[已拒绝] 输入中断")
            return False
        if ans is None:
            print(f"[超时拒绝] {AUTH_TIMEOUT}秒内未收到输入")
            return False
        import unicodedata as _ud
        a = _ud.normalize("NFKC", ans).strip().lower()
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            print("[已拒绝] 用户输入了 N")
            return False
        print(f"   无效输入 [{ans}]，请输入 Y 或 N")

def _machine_seed():
    try:
        seed = open("/etc/machine-id", encoding="utf-8").read().strip()
    except Exception:
        seed = os.uname()[1] + os.path.expanduser("~")
    return hashlib.sha256(seed.encode()).digest()

def encrypt_key(k):
    mk = _machine_seed()
    return base64.b64encode(bytes(b ^ mk[i % len(mk)] for i, b in enumerate(k.encode()))).decode()

def decrypt_key(s):
    mk = _machine_seed()
    return bytes(b ^ mk[i % len(mk)] for i, b in enumerate(base64.b64decode(s))).decode()

def load_api_key():
    if os.path.exists(KEY_FILE):
        try:
            return decrypt_key(open(KEY_FILE, encoding="utf-8").read().strip())
        except Exception:
            return None
    return None

def save_api_key(k):
    os.makedirs(BASE_DIR, exist_ok=True)
    open(KEY_FILE, "w", encoding="utf-8").write(encrypt_key(k))
    os.chmod(KEY_FILE, 0o600)

API_KEY = load_api_key()

try:
    from rich.console import Console
    from rich.markdown import Markdown
    _con = Console()
except Exception:
    pass

_mdb = _mdl = ""
_mdf = False

def _md_emit():
    global _mdb
    b, _mdb = _mdb, ""
    if b.strip():
        try:
            _con.print(Markdown(b))
            _con.print()
        except Exception:
            print(b, end="", flush=True)

def _md_feed(t):
    global _mdb, _mdl, _mdf
    _mdl += t
    while "\n" in _mdl:
        ln, _mdl = _mdl.split("\n", 1)
        _mdb += ln + "\n"
        if ln.lstrip().startswith(("```", "~~~")):
            _mdf = not _mdf
            if not _mdf:
                _md_emit()
        elif not _mdf and not ln.strip():
            _md_emit()

def _md_flush():
    global _mdb, _mdl, _mdf
    _mdb, _mdl, _mdf = _mdb + _mdl, "", False
    _md_emit()

def llm(messages, with_tools=True, stream=True, max_tokens=MAX_OUT, think=True):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    if think:
        body["reasoning_effort"] = REASONING_EFFORT
        body["thinking"] = {"type": "enabled"}
    else:
        body["thinking"] = {"type": "disabled"}
    if with_tools:
        body["tools"], body["tool_choice"] = TOOLS, "auto"
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + str(API_KEY or ""), "User-Agent": "curl/8.5.0"})
    content, usage, resp = "", None, None
    try:
        resp = urllib.request.urlopen(req, timeout=600)
        if not stream:
            return json.loads(resp.read().decode("utf-8"))
        tool_calls, finish, thinking, reasoning = {}, None, False, ""
        import select, termios, tty
        fd = sys.stdin.fileno()
        if sys.stdin.isatty():
            old = termios.tcgetattr(fd)
        else:
            old = None
        try:
            if old is not None:
                tty.setcbreak(fd)
            for raw in resp:
                if old is not None:
                    r, _, _ = select.select([sys.stdin], [], [], 0)
                    if r:
                        ch = os.read(fd, 1)
                        if ch == b"\x00":
                            raise _StopLoop
                        if ch == b"\x18":
                            global _compress_requested
                            _compress_requested = True
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = (chunk.get("choices") or [{}])[0]
                finish = choice.get("finish_reason")
                if chunk.get("usage"):
                    usage = chunk["usage"]
                delta = choice.get("delta") or {}
                if delta.get("reasoning_content"):
                    if not thinking: print("\n\x1b[38;5;244m[思维链]", end="", flush=True)
                    thinking = True
                    reasoning += delta["reasoning_content"]
                    print(delta["reasoning_content"], end="", flush=True)
                if delta.get("content"):
                    if not content:
                        if thinking:
                            print("\x1b[0m\n[正文]", end="", flush=True)
                    content += delta["content"]
                    _md_feed(delta["content"])
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    obj = tool_calls.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        obj["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        obj["function"]["name"] = fn["name"]
                    if fn.get("arguments"):
                        obj["function"]["arguments"] += fn["arguments"]
            if thinking:
                print("\x1b[0m", end="", flush=True)
            if not content and not tool_calls and not reasoning:
                return "API_ERROR"
            message = {"role": "assistant", "content": content or None}
            if reasoning:
                message["reasoning_content"] = reasoning
            if tool_calls:
                message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
            return {"choices": [{"message": message, "finish_reason": finish}], "usage": usage}
        finally:
            _md_flush()
            if old is not None:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except urllib.error.HTTPError as e:
        print(f"\n[API错误 {e.code}] {e.read().decode('utf-8','ignore')[:300]}")
        if content:
            return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": None}], "usage": usage, "truncated": True}
        return "API_ERROR"
    except _StopLoop:
        raise
    except Exception:
        if content:
            return {"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": None}], "usage": usage, "truncated": True}
        return None
    finally:
        if resp is not None:
            try: resp.close()
            except Exception: pass



MAXLONG = 512
QCOL = 216

def _pil():
    global _PIL
    if _PIL is None:
        try:
            from PIL import Image as _I
            _PIL = _I
        except Exception:
            return None
    return _PIL
def _nopil(r):
    print("[提示] 未安装 Pillow，图片未解码：pip install pillow 后提示用户重新输入图片", flush=True)
    return r
def _resize(im,lg):
    w,h=im.size
    if max(w,h)<=lg: return im
    k=lg/max(w,h)
    return im.resize((max(1,int(w*k)),max(1,int(h*k))),_pil().LANCZOS)

def _save(im,I):
    if QCOL>1:
        try:
            im=im.quantize(colors=min(256,QCOL),method=I.Quantize.FASTOCTREE,dither=I.Dither.NONE)
        except Exception: pass
    b=io.BytesIO(); im.save(b,"PNG",optimize=True,compress_level=9); return b.getvalue()

def _shrink(p):
    I=_pil()
    if I is None: return None
    try:
        return _save(_resize(I.open(p).convert("RGB"),MAXLONG),I)
    except Exception: return None

def _shrink_raw(b,lg=None):
    I=_pil()
    if I is None or len(b)<16: return None
    w,h=struct.unpack("<II",b[:8])
    if w<2 or h<2 or len(b)<16+w*h*4: return None
    try:
        im=I.frombytes("RGBA",(w,h),bytes(b[16:16+w*h*4])).convert("RGB")
        return _save(_resize(im,lg or MAXLONG),I)
    except Exception: return None

_IMG_EXT=('.jpg','.jpeg','.png','.gif','.webp','.bmp','.tif','.tiff')
def _badimg(bad):
    return "以下图片损坏，请提示用户："+" ".join(os.path.basename(x) for x in bad)

def _img(q):
    import shlex
    t=q.strip()
    if t.startswith(('http://','https://')):
        return [{'type':'text','text':'看图'},{'type':'image_url','image_url':{'url':t,'detail':'low'}}] if t.split('?')[0].lower().endswith(_IMG_EXT) else q
    imgs=[]; text=[]
    for x in shlex.split(t):
        p=x.strip("'\"")
        if os.path.isfile(p) and os.path.splitext(p)[1].lower() in _IMG_EXT: imgs.append(p)
        else: text.append(x)
    if not imgs: return q
    head=' '.join(text) or f'{len(imgs)}张图'
    if _pil() is None: return _nopil(head)
    b=[]; bad=[]
    for p in imgs:
        s=_shrink(p)
        if s is None: bad.append(p); continue
        b.append(base64.b64encode(s).decode())
    if not b: return _badimg(bad)
    c=[{'type':'text','text':head if not bad else head+"\n"+_badimg(bad)}]
    c+=[{"type":"image_url","image_url":{"url":"data:image/png;base64,"+x,"detail":"low"}} for x in b]
    return c

def compress(hist, summaries=None):
    hist = sanitize_hist(hist)
    msgs = []
    for s in summaries or []:
        msgs.append({"role": "user", "content": s})
    msgs += hist
    msgs.append({"role": "user", "content": "[总结所有]"})
    for _ in range(10):
        print("正在压缩", flush=True)
        resp = llm([{"role": "system", "content": SYSTEM}] + msgs, with_tools=False, stream=False, max_tokens=MAX_OUT // 4, think=False)
        if isinstance(resp, dict) and resp.get("choices"):
            c = resp["choices"][0]["message"]["content"]
            if c:
                return "[历史背景]:" + c
        time.sleep(5)
    return None

def sanitize_hist(h):
    out, i, n = [], 0, len(h)
    while i < n:
        m = h[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            j, k = i + 1, 0
            while j < n and h[j].get("role") == "tool":
                k += 1; j += 1
            if k < len(m["tool_calls"]):
                i = j; continue
            out.extend(h[i:j]); i = j; continue
        out.append(m); i += 1
    return out

def build_context(mem_hist, summaries=None):
    ctx = [{"role": "system", "content": SYSTEM}]
    for s in summaries or []:
        ctx.append({"role": "user", "content": s})
    return ctx + sanitize_hist(mem_hist)

def _trunc(s, lim=MAX_READ):
    if len(s) <= lim:
        return s
    n = len(s)
    keep = lim
    for _ in range(3):
        note = "\n[已省略 %d 字符]\n" % (n - keep)
        k = max(0, lim - len(note))
        if k == keep:
            break
        keep = k
    note = "\n[已省略 %d 字符]\n" % (n - keep)
    head = keep * 6 // 10
    tail = keep - head
    return s[:head] + note + (s[-tail:] if tail else "")

def RUN(args):
    cmd = args.get("command", "").strip()
    if not cmd:
        return "错误：没有命令"
    if len(cmd) > MAX_CMD:
        return "[超出上限] %d>%d 字符，请分块" % (len(cmd), MAX_CMD)
    if args.get("dangerous") and not confirm_block(cmd):
        return "[已拒绝] 危险命令未执行"
    import select, termios, tty
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd) if sys.stdin.isatty() else None
    try:
        if old:
            tty.setcbreak(fd)
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        global _proc; _proc = p
        out, err = bytearray(), bytearray()
        dl, oo, oe = time.time() + 3600, True, True
        while oo or oe:
            if time.time() > dl:
                os.killpg(p.pid, signal.SIGKILL); p.wait()
                return "命令超时（3600秒）"
            watch = []
            if oo: watch.append(p.stdout)
            if oe: watch.append(p.stderr)
            if old: watch.append(sys.stdin)
            r, _, _ = select.select(watch, [], [], 0.1)
            if p.poll() is not None and not r:
                break
            if old and sys.stdin in r:
                ch = os.read(fd, 1)
                if ch == b"\x00":
                    _kp(p); raise _StopLoop
                if ch == b"\x18":
                    global _compress_requested
                    _compress_requested = True
            if oo and p.stdout in r:
                d = os.read(p.stdout.fileno(), 65536)
                if d: out += d
                else: oo = False
            if oe and p.stderr in r:
                d = os.read(p.stderr.fileno(), 65536)
                if d: err += d
                else: oe = False
        p.wait()
        text = bytes(out).decode("utf-8", "ignore") + (("\n[stderr] " + bytes(err).decode("utf-8", "ignore")) if err else "")
        return f"退出码 {p.returncode}\n{_trunc(text)}"
    except _StopLoop:
        raise
    except Exception as e:
        return f"执行失败: {e}"
    finally:
        if old:
            try: termios.tcflush(fd, termios.TCIFLUSH)
            except Exception: pass
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        if _proc is not None:
            _kp(_proc); _proc = None
TOOL_IMPL = {name.lower(): RUN for name in TOOL_ALIASES}

def welcome():
    print("\n[首次运行] 配置 DeepSeek API Key")
    try:
        import getpass
        k = getpass.getpass("请输入 API Key: ").strip()
    except Exception:
        k = input("请输入 API Key: ").strip()
    if not k:
        print("未输入 Key，退出。下次运行可重新配置。")
        sys.exit(1)
    save_api_key(k)
    print(f"已加密保存 → {KEY_FILE}\n")
    return k

class _StopLoop(Exception):
    pass

def _kp(p):
    try:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGKILL)
        p.wait()
    except Exception:
        pass

_proc = None
_compress_requested = False

def _stop(s, f):
    if _proc is not None:
        _kp(_proc)
    raise _StopLoop

_pt_session = None

def _read_input():
    global _pt_session
    if not sys.stdin.isatty():
        lines = []
        while True:
            line = input("\n你> " if not lines else "... ")
            if not line.replace("\x18", "").strip():
                if "\x18" in line:
                    lines.append(line)
                break
            lines.append(line)
        return "\n".join(lines)
    if _pt_session is None:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.key_binding import KeyBindings
        kb = KeyBindings()

        @kb.add("enter")
        def _enter(event):
            b = event.current_buffer
            if not b.document.current_line.replace("\x18", "").strip() and not (
                    event.key_processor.input_queue
                    or select.select([sys.stdin.fileno()], [], [], 0.02)[0]):
                b.validate_and_handle()
            else:
                b.insert_text("\n")

        @kb.add("c-x")
        def _cx(event):
            event.current_buffer.insert_text("\x18")

        @kb.add("tab")
        def _tab(event):
            event.current_buffer.insert_text("\t")

        _pt_session = PromptSession(multiline=True, key_bindings=kb,
                                    prompt_continuation="... ")
    return _pt_session.prompt("\n你> ")


def main():
    global API_KEY, mem_hist, _compress_requested
    if not API_KEY:
        API_KEY = welcome()

    mem_hist = []
    signal.signal(signal.SIGUSR1, _stop)
    summaries = []
    need_compress = False
    print("新终端=新对话 | Ctrl+Space=暂停 | Ctrl+X=压缩")

    while True:
        try:
            raw = _read_input().replace("\x00", "")
            if "\x18" in raw:
                _compress_requested = True
                raw = raw.replace("\x18", "")
            q = raw.strip()
        except _StopLoop:
            continue
        except KeyboardInterrupt:
            print("")
            continue
        except EOFError:
            print("\n再见")
            break
        if not q:
            continue
        try:
            q=_img(q)
        except Exception:
            pass
        mem_hist.append({"role": "user", "content": q})

        try:
            retry = 0
            empty = 0
            while True:
                if _compress_requested:
                    need_compress = True
                    _compress_requested = False
                if need_compress:
                    last_u = max(i for i, m in enumerate(mem_hist) if m["role"] == "user")
                    if last_u == 0:
                        need_compress = False
                    else:
                        ns = compress(mem_hist[:last_u], summaries)
                        if ns is None:
                            need_compress = False
                            break
                        summaries.append(ns)
                        mem_hist = mem_hist[last_u:]
                        need_compress = False
                        retry = 0
                        print("\n[已压缩，继续]", flush=True)
                resp = llm(build_context(mem_hist, summaries))
                if resp is None:
                    retry += 1
                    if retry > 10:
                        last_u = max(i for i, m in enumerate(mem_hist) if m["role"] == "user")
                        if last_u > 0:
                            need_compress = True
                            continue
                        break
                    time.sleep(5)
                    continue
                if resp == "API_ERROR":
                    last_u = max(i for i, m in enumerate(mem_hist) if m["role"] == "user")
                    if last_u > 0:
                        need_compress = True
                        continue
                    break
                usage = (resp.get("usage") or {}).get("total_tokens", 0)
                if usage > MAX_TOK:
                    need_compress = True
                msg = resp.get("choices", [{}])[0].get("message", {})
                content, tcs = msg.get("content") or "", msg.get("tool_calls") or []
                rc = msg.get("reasoning_content")
                if resp.get("truncated"):
                    retry += 1
                    if retry > 10:
                        break
                    time.sleep(5)
                    continue
                if tcs:
                    am = {"role": "assistant", "content": content or None, "tool_calls": tcs}
                    if rc: am["reasoning_content"] = rc
                    mem_hist.append(am)
                    for tc in tcs:
                        name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"].get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        print(f"\n[工具] {name} {args.get('explain','')} | {args.get('command','')[:100]}")
                        impl = TOOL_IMPL.get(name.lower())
                        result = impl(args) if impl else f"未知工具 {name}"
                        mem_hist.append({"role": "tool", "tool_call_id": tc.get("id"), "content": str(result)})
                    continue
                if not content:
                    empty += 1
                    if empty > 3:
                        break
                    time.sleep(1)
                    continue
                if content: print()
                am = {"role": "assistant", "content": content}
                if rc: am["reasoning_content"] = rc
                mem_hist.append(am)
                break
        except _StopLoop:
            print("\x1b[0m", end="")
        except Exception as e:
            print(f"\n[内部错误] {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
