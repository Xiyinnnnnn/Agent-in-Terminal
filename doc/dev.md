# Agent-in-Terminal（宿主开发说明）

## 运行与数据

- 主入口：`term_agent.py`，Python 3.10+，仅依赖标准库。
- 默认 API：DeepSeek 官方 Chat Completions。
- Termux 安装器：`install.sh`。
- Termux 启动命令：`agent`；更新命令：`agent-update`。
- 配置目录：`~/.config/term_agent/`，包含 `key.bin`、`memory/`、`skill/`、`taskbook/`。
- 环境变量：`DEEPSEEK_API_KEY`（Key）、`TERM_AGENT_MODEL`（模型 ID）。

## DeepSeek 官方 API 配置

| 项 | 默认值 | 说明 |
|---|---|---|
| API_URL | `https://api.deepseek.com/chat/completions` | 官方 OpenAI 兼容端点 |
| MODEL | `deepseek-flash` | `TERM_AGENT_MODEL` 可覆盖 |
| MAX_TOK | 900000 | 响应 usage.total_tokens 超阈值后请求压缩 |
| MAX_OUT | 32768 | 单次请求 `max_tokens` |
| REASONING_EFFORT | `high` | 官方推理强度参数 |
| AUTH_TIMEOUT | 30 | `dangerous=true` 授权等待秒数；非 TTY/<=0 使用阻塞输入 |

官方参考：
- https://api-docs.deepseek.com/zh-cn/
- https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/
- https://api-docs.deepseek.com/zh-cn/quick_start/pricing/

### 请求映射

| Agent 行为 | API 请求 |
|---|---|
| 正常推理 | `thinking.type=enabled`、`reasoning_effort=high` |
| 上下文压缩 | `thinking.type=disabled`、`stream=false`、`max_tokens=MAX_OUT//4` |
| Shell 工具 | `tools=[RUN]`、`tool_choice=auto` |
| 流式输出 | `stream=true`、`stream_options.include_usage=true` |
| 鉴权 | `Authorization: Bearer <DEEPSEEK_API_KEY>` |

API 使用 `/chat/completions`。流式响应通过 SSE 读取 `content`、`reasoning_content`、`tool_calls` 与末尾 `usage`。非流式压缩请求解析标准 JSON 响应。

DeepSeek 文档规定 `tool_choice=required` 与指定工具名不支持思考模式；本项目使用 `auto`，不使用 required/named tool choice。`deepseek-flash` 支持图像输入；`deepseek-v4-pro` 当前仅支持文本输入。以官方模型列表为准。

### Key 读取优先级

1. `DEEPSEEK_API_KEY` 环境变量。
2. 旧版兼容文件 `~/.config/term_agent/key.bin`。
3. 两者都缺失时进入隐藏输入向导。

`key.bin` 沿用旧版本机器种子 XOR 编码格式，权限设为 `0600`。它属于混淆，不是现代强加密；高安全场景优先使用环境变量。修改 Key 不需要修改源码。

## 核心循环（main）

```text
mem_hist = []            # [user/assistant/tool] 消息列表
summaries = []           # append-only 快照链
loop:
  q = input()
  mem_hist.append(user q)
  inner loop:
    if need_compress:
      last_u = 最后一个 user 消息下标
      ns = compress(mem_hist[:last_u], summaries)
      if ns is None: break
      summaries.append(ns)
      mem_hist = mem_hist[last_u:]
      need_compress = False
    resp = llm(build_context(mem_hist, summaries))
    if resp None/API_ERROR: retry / compression recovery
    if resp.usage.total_tokens > MAX_TOK: need_compress=True
    否则处理 content / tool_calls（执行 RUN 并回填）
```

中断语义：流式收包与命令执行期间轮询 stdin。`0x00` 抛 `_StopLoop` 回主循环；`0x18` 设置 `_compress_requested`，在安全边界请求压缩。

## 上下文 = 快照链 + 历史

```text
build_context: [system SYSTEM] + [user s for s in summaries] + mem_hist
compress:      [system SYSTEM] + [user s for s in summaries] + hist + [user "[总结所有]"]
               → llm(stream=False, think=False, max_tokens=MAX_OUT//4)
               → "历史背景：" + 新快照
```

- 快照链 append-only，旧快照不修改。
- 压缩请求复用完整前缀。
- 连续 user 快照消息是设计，不是 bug。
- `MAX_TOK` 是响应 usage 触发阈值，不是 API 的硬上下文上限。

## 安全模式

宿主不扫描命令内容，只读取 `RUN` 工具参数中的 `dangerous` 布尔值。

| dangerous | 行为 |
|---|---|
| `false` | 直接执行 Shell 命令 |
| `true` | 显示命令确认块，用户输入 `Y` 后执行 |

模型误标 `false` 时，宿主无二次拦截。该行为是当前安全模型的明确边界。

### 授权闸门

| 项 | 行为 |
|---|---|
| 预输入 | `tcflush(TCIFLUSH)`，避免预输入误放行 |
| 归一化 | NFKC + strip + lower |
| 接受 | `y` / `yes` + 回车 |
| 拒绝 | `n` / 超时 / `Ctrl+C` / `Ctrl+D` |
| 超时 | `AUTH_TIMEOUT` 秒；<=0 使用阻塞输入 |

## 进程回收与异常处理

- `RUN` 使用 `start_new_session=True` 创建独立进程组。
- `_kp(p)` 回收整组进程，避免子进程继续占用 TTY。
- `RUN` 的 `finally` 统一回收进程组。
- 图片解析异常按纯文本处理，不退出主循环。
- HTTP 401/403、429、网络异常输出可诊断错误；调用层保留 `API_ERROR`/重试约定。

## 函数地图

| 函数 | 职责 |
|---|---|
| `main` | 交互循环、压缩调度、工具循环 |
| `llm` | DeepSeek 官方 API 请求、SSE 解析、中断轮询 |
| `build_context` | SYSTEM + 快照链 + 历史 |
| `compress` | 压缩历史并追加快照 |
| `sanitize_hist` | 丢弃 tool_calls 与 tool 回填不配对的消息段 |
| `confirm_block` | 危险命令授权闸门 |
| `RUN` | Shell 执行、stdin 中断轮询、进程回收 |
| `load_api_key` | 环境变量优先，其次读取旧 key.bin |
| `save_api_key` | 写入兼容格式 key.bin，权限 0600 |

## Termux 安装行为

`install.sh` 使用 GitHub codeload 源码包安装，不依赖桌面环境：

- 主程序：`$PREFIX/share/term_agent/term_agent.py`
- 命令：`$PREFIX/bin/agent`
- 更新：`$PREFIX/bin/agent-update`
- 用户数据：`~/.config/term_agent/`
- 原厂 Skills：复制到 `~/.config/term_agent/skill/`
- 更新时只清理上次安装器记录的原厂 Skills，不删除用户自建文件、Key、memory、taskbook。

系统包：`python curl tar tmux ffmpeg android-tools`；`yt-dlp` 安装失败不影响主程序。

## 验证

```bash
python3 -m py_compile term_agent.py skills/*.py
bash -n install.sh launch.sh
```

无 Key 时可做模块导入与语法检查；真实 API 联通测试需要用户自己的 DeepSeek API Key。不要把真实 Key 写入测试文件或提交仓库。
