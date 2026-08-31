# Agent-in-Terminal（宿主）

## 是什么
零依赖 Python 单文件终端 Agent（564 行）。OpenAI 兼容 API（火山方舟 v4 / deepseek-v4-flash），bash 工具执行，Bazzite 桌面常驻。

## 运行与数据
- 入口：本目录 `term_agent.py`（python3 直跑，零依赖）
- 桌面：`~/Desktop/term-agent.desktop` → `python3 ~/.local/bin/term_agent/term_agent.py`
- 数据：`~/.config/term_agent/` = `key.bin`（加密 API Key）+ `memory/` `skill/` `taskbook/`（agent 自产 md）

## 全局常量
| 常量 | 值 | 用途 |
|---|---|---|
| API_URL | `https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions` | LLM 端点 |
| MODEL | `deepseek-v4-flash` | 模型名 |
| MAX_TOK | 524288 | 会话 usage 超此值→触发压缩 |
| MAX_OUT | 32768 | 输出 max_tokens；压缩用 `MAX_OUT//4` |
| REASONING_EFFORT | medium | 推理强度 |
| SYSTEM | 内置提示词常量 | 每个请求的 system 消息 |
| TOOLS | RUN 工具 schema | 工具定义 |

## 核心循环（main）
```
mem_hist = []            # 消息列表 [user/assistant/tool]
summaries = []           # append-only 快照链
loop:
  q = input()
  mem_hist.append(user q)
  inner loop:
    if need_compress:                        # usage>MAX_TOK 或 API 重试超限
      last_u = 最后一个 user 消息下标
      ns = compress(mem_hist[:last_u], summaries)
      if ns is None: break
      summaries.append(ns)                   # 只追加不覆盖
      mem_hist = mem_hist[last_u:]           # 尾部保留
      need_compress = False
    resp = llm(build_context(mem_hist, summaries))
    if resp None/API_ERROR: retry>10 → need_compress=True
    if resp.usage > MAX_TOK: need_compress=True
    否则处理 content / tool_calls（循环执行 RUN 并回填）
```

## 上下文 = 快照链 + 历史
```
build_context: [system SYSTEM] + [user s for s in summaries] + mem_hist
compress:      [system SYSTEM] + [user s for s in summaries] + hist + [user "[总结所有]"]
               → llm(stream=False, think=False, max_tokens=MAX_OUT//4)
               → 返回 "历史背景：" + 新快照文本
```
- 快照链 append-only：旧快照永不变更/不移除（Prefix immutable, suffix replaceable）
- 压缩请求复用完整前缀 → 最大化 KV 命中
- 连续多条 user 消息（快照链）是设计，不是 bug

## 函数地图
| 函数 | 职责 |
|---|---|
| main | 交互循环 + 压缩调度 + 工具循环 |
| llm | OpenAI 兼容请求，流式解析 content/reasoning/tool_calls/usage |
| build_context | 构造 SYSTEM+快照链+历史 |
| compress | 压缩历史→新快照（append） |
| RUN | 工具执行，危险命令黑名单拦截 |
| match_danger / confirm_block | 危险命令检测 + 二次确认 |
| extract_tool_call | 备用工具调用解析 |
| _img | 图片参数 base64 化 |
| load/save_api_key | 密钥读写（机器种子 XOR + base64，key.bin 0600） |

## 密钥
`_machine_seed()` 取机器特征 → XOR + base64 加密；`KEY_FILE = ~/.config/term_agent/key.bin`（0600）。

## 改哪 / 怎么验
- 改提示词 → `SYSTEM` 常量
- 改压缩 → `compress` / `build_context` / `main` 压缩段（三处联动）
- 改工具 → `RUN` + `TOOLS` schema
- 验：`python3 -m py_compile term_agent.py`；mock `llm` 单测（构造假 hist/summaries 断言快照 append 与请求顺序）

## 约束
- 新终端 = 新对话（mem_hist 纯内存，无持久化）
- 压缩请求非流式、关闭思考
- 依赖 readline（交互输入）
