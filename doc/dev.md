# 宿主开发

STATE ✓ 2026-11-21｜SCOPE 单文件宿主 `cli-agent.py`：对话循环、压缩、授权闸门、图片编码；技能集见 `README` 与 `skills/`

## 分层

完整能力 = 依赖 + 宿主 + 技能集，缺一层只覆盖部分场景。

| 层 | 负责 | 位置 |
|---|---|---|
| 依赖 | 语言运行时、系统工具（chromium/ffmpeg/yt-dlp）、pip/npm 包 | `install.sh` 一次装齐 |
| 宿主 | 对话、压缩、工具调用、授权闸门 | `cli-agent.py`（单文件） |
| 技能 | 某件事怎么做：命令、参数、失败处置 | `skills/*.md` + 同目录脚本 |

宿主只暴露 `RUN`（shell 执行）一个工具；具体能力由技能把工具用出来，依赖决定这些技能能不能跑起来。扩能力只加技能，不改宿主。

## 运行期数据

| 路径 | 内容 |
|---|---|
| `~/.config/cli-agent/skill/` | 技能工作副本（`install.sh` 从 `skills/` 复刻） |
| `~/.config/cli-agent/memory/` | 结论、实测数字、坑 |
| `~/.config/cli-agent/taskbook/` | 多步任务进度与证据 |
| `~/.config/cli-agent/key.bin` | 加密 API Key（机器绑定） |

## 位置

| 项 | 值 |
|---|---|
| 仓库内 | `cli-agent.py`（根目录） |
| 安装后 | `~/.local/bin/cli-agent/cli-agent.py` |
| 数据根 | `~/.config/cli-agent/`：`key.bin` + `memory/` `skill/` `taskbook/` |
| 依赖 | Python 3.10+、Pillow、prompt_toolkit、rich（可选，缺失退回原样打印）；系统包与 pip/npm 由 `install.sh` 装 |

## 常量

| 常量 | 值 | 作用 |
|---|---|---|
| API_URL | `http://127.0.0.1:3050/v1/chat/completions` | 本地反代；云端镜像版为 `api.deepseek.com` |
| MODEL | `deepseek/deepseek-v4-flash` | CC 上游模型 ID（`vendor/model`） |
| MAX_TOK | 524288 | 压缩阈值（usage 超此值触发），非输出上限 |
| MAX_OUT | 32768 | 输出 max_tokens；压缩请求用 `MAX_OUT//4` |
| MAX_READ | 30000 | 工具结果回读截断，超出追加 `[已省略 N 字符]` |
| MAX_CMD | 6000 | 单条命令字符上限，超出不执行 |
| REASONING_EFFORT | high | 请求体 `reasoning_effort` |
| AUTH_TIMEOUT | 30 | 授权等待秒数；≤0 不设超时（非 tty 仍用 `input()`） |

## 提示词符号语义

`SYSTEM` 用符号压缩；改提示词先查表，不新增未声明符号。

| 符号 | 语义 | 例 |
|---|---|---|
| → | 流程 / 转换 | `THINK→RUN→验`、`结论→memory/<name>.md` |
| \| | 或 | `删除\|覆盖\|格式化`、`df\|du\|ls\|cat` |
| > | 优先 | `tool>text`、`查>猜`、`当前指令>taskbook>skill>memory>历史` |
| && | 且 | `cmd&&answer=abs path`、`LOOKUP memory&&skill` |
| = | 定义 | `root=~/.config/cli-agent/`、`hit=reuse+cite` |
| ≠ | 不等 | `draft≠deliver` |
| <x> | 占位符 | `<name>`、`<task>`、`<script>` |
| [ ] / [x] | 清单 | `节点[ ]→[x]+evidence` |
| // | 注释 | `[THINK] P1-P5全执行 // 包裹` |
| ! | 禁止 | `!跳过`、`!目测`、`!编造`、`!cat`、`!rm`、`!主动扫描`、`!删原件` |

| 约束 | 值 |
|---|---|
| 声明 | 全部符号在 `[SYM]` 一行声明；`;` 分隔、符号加括号，避免 `\|` 自指 |
| 并列 | 并列用逗号（`dirs=memory/,skill/,taskbook/`）；`\|` 只表"或" |
| 动作 vs 状态 | 危险动作写 `RUN(dangerous=true)`；只写 `dangerous=true` 模型会"先问不发 RUN"（实测 0/3 vs 2/3） |
| 压缩 | 2498 → 2217 字符（-11.2%）、60 → 48 行；50 个语义 token 全覆盖 |
| 不压 | `[SYM]` 行、LOOP 的 `前/中/后`、`[DELIVER]` 8 项、`NEVER overwrite whole file`、7 行 `<EXAMPLE>` |

## 主循环

```python
mem_hist = []; summaries = []
while True:
    q = input()                       # 0x00 清缓冲 / 0x18 置压缩标志
    mem_hist.append(user q)
    while True:
        if need_compress: ...          # 见「压缩」
        resp = llm(build_context(mem_hist, summaries))
        if resp.usage > MAX_TOK: need_compress = True
        if tool_calls: RUN 执行并回填; continue
        break
```

## 空响应重试

| 项 | 值 |
|---|---|
| 触发 | `content` 与 `tool_calls` 皆空（只回了 `reasoning_content`） |
| 处置 | 丢弃本次产出（不写 `mem_hist`）→ 用当前历史重发 |
| 上限 | 重发 3 次；第 4 次仍空 `break`，回到等输入 |
| 间隔 | 1s |
| 日志 | 静默，无提示 |
| 计数 | `empty` 每轮用户输入重置；与 `retry`（网络失败 / 截断，阈值 10）独立 |

| 边界实测 | 结果 |
|---|---|
| 空 1 次 | 重发 1 次成功 |
| 空 3 次 | 第 4 次成功 |
| 空 10 次 | 实际只调 4 次（原始 1 + 重发 3）后 `break` |

坑：日志里有无 `[正文]` 取决于该次响应是否带 `reasoning_content`；没有 `[正文]` ≠ 没回答。

## 压缩

| 项 | 值 |
|---|---|
| 触发 | `usage > MAX_TOK`，或连续 10 次 API 失败，或 `Ctrl+X` |
| 切点 | 最后一个 user 消息之前；其后的历史保留 |
| 产物 | `"[历史背景]:" + 新快照`，append 到 `summaries`，旧快照不可变 |
| 请求 | 复用完整前缀（最大化 KV 命中）、非流式、`think=False`、`max_tokens=MAX_OUT//4` |

## 安全

| 项 | 值 |
|---|---|
| 判定权 | 模型：`RUN` 入参的 `dangerous` 布尔值 |
| 宿主角色 | 不扫描命令内容，不解析管道、替换、剥壳 |
| `false` | `subprocess` 直接执行 |
| `true` | `confirm_block()` 弹确认，`y` + 回车才执行 |
| 误标 `false` | 直接执行，无兜底（有意设计） |
| 口径所在 | `SYSTEM` 的 `[SAFETY]` 段 + `TOOLS` 的 `dangerous` 描述；代码不参与判定 |

## 授权闸门 confirm_block

| 项 | 行为 |
|---|---|
| 预输入 | 进闸门前 `tcflush(TCIFLUSH)`，防"没看提示就被放行" |
| 归一化 | NFKC + strip + lower，全角 `ｙ/ｎ` 等效半角 |
| 接受 | `y` / `yes` + 回车；单键不算 |
| 超时 | `AUTH_TIMEOUT` 秒无输入 → 拒绝 |
| 拒绝回执 | `[已拒绝] 危险命令未执行（模型标记 dangerous=true）` |

## 函数

| 函数 | 职责 |
|---|---|
| main | 交互循环、压缩调度、工具回填 |
| llm | OpenAI 兼容流式请求；`select` 轮询 stdin 支持中断 |
| _md_feed / _md_flush | 流式正文按空行切块，围栏内不切；整块交 `rich` 渲染，缺 rich 或渲染异常退回原样打印；公式不处理，靠 `SYSTEM` 的 `[MUST] 公式→Unicode` |
| build_context | `SYSTEM` + 快照链 + `mem_hist` |
| compress | 历史 → 新快照（append-only） |
| sanitize_hist | 丢弃 tool_calls 与 tool 回填不配对的消息段 |
| confirm_block | 授权闸门 |
| RUN | 执行命令，边读边响应中断，超时 3600s |
| _kp | 无条件 `killpg(SIGKILL)` 回收整组 |
| _img / _shrink / _shrink_raw / _dec / _enc | 图片编码，自研无外部依赖 |
| load/save_api_key | `key.bin` 读写（machine-id XOR + base64，0600） |

## 密钥

`load_api_key()` 只读 `~/.config/cli-agent/key.bin`，源码不含明文；缺失时 `welcome()` 向导写入并 `chmod 600`。换 key 重写该文件即可。

## 改哪验哪

| 要改 | 动哪里 |
|---|---|
| 提示词 | `SYSTEM` 常量；跨机器同步禁整文件覆盖（各机器有各自的 `[SYS]` 口径） |
| 闸门 | `confirm_block`，`tcflush` 与 NFKC 两处不回退 |
| 判定权 | 只动 `SYSTEM` 的 `[SAFETY]` 段与 `TOOLS` 的 `dangerous` 描述 |
| 压缩 | `compress` / `build_context` / `main` 压缩段，三处联动 |
| 图片 | `_img` 系列 |
| 输出渲染 | `_md_feed` / `_md_flush`；思维链不渲染，`mem_hist` 里仍存原始 markdown |

```bash
python3 -m py_compile cli-agent.py
python3 - <<'PY'
import importlib.util
spec = importlib.util.spec_from_file_location("ta", "cli-agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert not hasattr(m, "match_danger")
assert m.RUN({"command": "echo hi", "explain": "t", "dangerous": False}).startswith("退出码 0")
PY
```

## 约束

| 项 | 值 |
|---|---|
| 会话 | 新终端 = 新对话；`mem_hist` 纯内存，不落盘 |
| 中断 | 流式收包与命令执行期间均 `select` 0s 轮询 stdin |
| 命令超时 | 3600s，超时整组 kill |
| 命令长度 | 6000 字符（`MAX_CMD`），大文件写入分块追加 |
| 注释 | 源码零注释，解释只在本文件 |

## 坑

| 现象 | 原因 | 处置 |
|---|---|---|
| 授权按 `y` 毫无反应 | 主进程退出后孙进程仍持有 tty 读走输入 | `_kp` 无条件 `killpg`，不加 `poll()` 守卫 |
| 未闭合引号导致主循环退出 | `shlex.split` 抛 `ValueError` | `q=_img(q)` 的 try/except 按纯文本处理 |
| 压缩后图片丢失 | 快照只存文本 | 图片原文只保留在 `mem_hist` 未压缩段 |
| 上下文明显超长却不压缩 | 只看 `usage` 字段，不数字符 | 依赖 API 返回 usage |
| 粘贴含空行的文本自动执行；粘贴内容里的 Tab 丢失 | 终端不发括号粘贴标记（输入法剪贴板、部分终端、tmux/ssh）时，换行是普通按键，空行回车触发执行；没配补全器时 Tab 不插入 | `_enter` 内检查 `input_queue` 与 stdin 20ms 内是否还有数据，有则当换行；单独绑定 Tab 插入 `\t` |
