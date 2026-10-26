# Agent-in-Terminal（宿主）

## 是什么
零依赖 Python 单文件终端 Agent（634 行，零注释风格）。OpenAI 兼容 API，bash 工具执行，Bazzite 桌面常驻。
默认经本地 `commandcode-proxy` 反代（`127.0.0.1:3050`），由 `start_agent.sh` 探活拉起。

## 运行与数据
- 入口：本目录 `term_agent.py`（python3 直跑，零依赖）
- 桌面：`~/Desktop/term-agent.desktop` → `python3 ~/.local/bin/term_agent/term_agent.py`
- 数据：`~/.config/term_agent/` = `key.bin`（加密 API Key）+ `memory/` `skill/` `taskbook/`（agent 自产 md）

## 全局常量
| 常量 | 值 | 用途 |
|---|---|---|
| API_URL | `http://127.0.0.1:3050/v1/chat/completions` | 本地反代（OpenAI 兼容） |
| MODEL | `deepseek/deepseek-v4-flash` | CC 上游模型 ID（形如 `vendor/model`） |
| MAX_TOK | 524288 | **上下文压缩阈值**（usage 超此值触发压缩），非输出上限 |
| MAX_OUT | 32768 | 输出 max_tokens；压缩请求用 `MAX_OUT//4` |
| REASONING_EFFORT | high | 推理强度（body.`reasoning_effort`） |
| AUTH_TIMEOUT | 30 | `dangerous=true` 时的授权等待秒数；`<=0` 退回阻塞式 `input()` |
| SYSTEM | 内置提示词常量 | 每个请求的 system 消息（**不随代码同步覆盖**，见文末） |
| TOOLS | RUN 工具 schema | 工具定义 |

## 核心循环（main）
```
mem_hist = []            # 消息列表 [user/assistant/tool]
summaries = []           # append-only 快照链
loop:
  q = input()            # Ctrl+Space(0x00) 清空缓冲；Ctrl+X(0x18) 置压缩标志
  mem_hist.append(user q)
  inner loop:
    if need_compress:
      last_u = 最后一个 user 消息下标
      ns = compress(mem_hist[:last_u], summaries)
      if ns is None: break
      summaries.append(ns)
      mem_hist = mem_hist[last_u:]
      need_compress = False
    resp = llm(build_context(mem_hist, summaries))   # 流式；select 0s 轮询 stdin
    if resp None/API_ERROR: retry>10 → need_compress=True
    if resp.usage > MAX_TOK: need_compress=True
    否则处理 content / tool_calls（循环执行 RUN 并回填）
```
中断语义：流式收包与命令执行期间都 `select` 轮询 stdin ——`0x00` 抛 `_StopLoop` 立刻回主循环，`0x18` 置 `_compress_requested` 供下一轮压缩。

## 上下文 = 快照链 + 历史
```
build_context: [system SYSTEM] + [user s for s in summaries] + mem_hist
compress:      [system SYSTEM] + [user s for s in summaries] + hist + [user "[总结所有]"]
               → llm(stream=False, think=False, max_tokens=MAX_OUT//4)
               → 返回 "历史背景：" + 新快照文本
```
- 快照链 append-only：旧快照永不变更/不移除（prefix immutable）
- 压缩请求复用完整前缀 → 最大化 KV 命中
- 连续多条 user 消息（快照链）是设计，不是 bug

## 安全模式（模型标志分流）

判定权在模型。宿主不扫描命令内容，只读 `RUN` 入参的 `dangerous` 布尔值决定走哪条路。

| dangerous | 路径 | 代码 |
|---|---|---|
| `false` | 直接 `subprocess` 执行 | `RUN` 内跳过闸门 |
| `true` | 弹确认块，用户 `Y` 才执行 | `confirm_block(cmd)` |

| 事实 | 后果 |
|---|---|
| 代码侧已无 `match_danger` / `DANGER_BL` / `PIPE_PATTERNS` / `_first_hit` / `_split_segs` | 无黑名单、无正则、无剥壳、无命令替换解析 |
| 模型误标 `false` | 命令直接执行，宿主无兜底（有意设计） |
| 判定口径只在 `SYSTEM` 的 `[SAFETY]` 段 + `TOOLS` 的 `dangerous` 描述 | 改口径只动这两处，不动代码 |

### 授权闸门（confirm_block）

| 项 | 行为 |
|---|---|
| 预输入 | 进闸门前 `tcflush(TCIFLUSH)`，封死"没看提示就被放行" |
| 归一化 | `NFKC` + strip + lower，全角 `ｙ/Ｙ/ｎ/Ｎ` 等效半角 |
| 接受 | `y` / `yes` + **回车**；单键不算（防误触） |
| 超时 | `AUTH_TIMEOUT` 秒无输入 → 自动拒绝 |
| 非法输入 | 重问；`Ctrl+C` / `Ctrl+D` → 拒绝 |
| 拒绝回执 | `[已拒绝] 危险命令未执行（模型标记 dangerous=true）` |

## 进程回收
- `RUN` 用 `start_new_session=True` 建独立进程组
- `_kp(p)` **无条件** `killpg(SIGKILL)`：主进程已退出时，组内孙进程可能仍持有 tty 并读走键盘输入
  （曾表现为"授权按了 y 却毫无反应"）；旧版 `if p.poll() is None` 守卫会让这步被整体跳过
- `RUN` 的 `finally` 统一 `_kp(_proc)`，避免残留

## 崩溃兜底
`q=_img(q)` 包 `try/except`：未闭合引号（`shlex.split` 抛 `ValueError`）等异常按纯文本处理，不再退出主循环。

## 函数地图
| 函数 | 职责 |
|---|---|
| main | 交互循环 + 压缩调度 + 工具循环 |
| llm | OpenAI 兼容请求，流式解析 content/reasoning/tool_calls/usage；stdin 轮询支持中断 |
| build_context | SYSTEM + 快照链 + 历史 |
| compress | 压缩历史 → 新快照（append） |
| sanitize_hist | 丢弃 tool_calls 与 tool 回填不配对的消息段 |
| confirm_block | 授权闸门（tcflush + NFKC + 回车确认），由 `dangerous` 标志触发 |
| RUN | 执行命令，select 边读边响应中断，超时 3600s |
| _kp | 无条件 killpg 回收整组 |
| _img / _shrink / _shrink_raw / _dec / _enc | 图片转 base64（自研解码，无外部依赖） |
| load/save_api_key | key.bin 读写（machine-id XOR + base64，0600） |

## 密钥
`API_KEY = load_api_key()` 只从 `~/.config/term_agent/key.bin` 读，源码内不含明文 Key；
缺失时 `main` 调 `welcome()` 向导写入（保存即 `chmod 600`）。换 Key 只需重写 key.bin，不必改源码。

## 改哪 / 怎么验
- 改提示词 → `SYSTEM`（**同步到别的机器时严禁整文件覆盖**：本仓库这份是 Bazzite，Termux 侧有其自己的环境口径）
- 改闸门 → `confirm_block`（`tcflush` 与 `NFKC` 两处都不要回退）
- 改判定权 → 只动 `SYSTEM` 的 `[SAFETY]` 段与 `TOOLS` 的 `dangerous` 描述，代码侧不参与判定
- 改压缩 → `compress` / `build_context` / `main` 压缩段（三处联动）
- 语法：`python3 -m py_compile term_agent.py`
- 危险判定回归（不启动宿主，直接加载模块）：
```python
import importlib.util
spec = importlib.util.spec_from_file_location("ta", "term_agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert not hasattr(m, "match_danger")
assert m.RUN({"command": "echo hi", "explain": "t", "dangerous": False}).startswith("退出码 0")
```

## 约束
- 新终端 = 新对话（`mem_hist` 纯内存，无持久化）
- 压缩请求非流式、关闭思考（`think=False`）
- 依赖 `readline`（交互输入）
- 单命令执行上限 3600s，超时整组 kill
- 零注释风格：解释写进本文件，源码不写行内注释
