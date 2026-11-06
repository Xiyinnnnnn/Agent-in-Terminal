# AGENT IN TERMINAL

![license](https://img.shields.io/badge/license-MIT-1e90ff?style=flat-square)
![python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)
![deps](https://img.shields.io/badge/dependencies-Pillow-2ea44f?style=flat-square)
![platform](https://img.shields.io/badge/platform-linux%20%7C%20termux-f59e0b?style=flat-square)

超轻量终端内 AI Agent：单文件，DeepSeek 对话 + Shell 工具执行。

## QUICK START

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/Xiyinnnnnn/Agent-in-Terminal@main/install.sh | bash
```

首次运行输入 DeepSeek API Key：
- 加密落盘（`~/.config/term_agent/key.bin`）

## USAGE

```bash
# Linux：python3 ~/.local/bin/term_agent/term_agent.py

# Termux：agent
```

API 端点与模型写在 `term_agent.py` 顶部常量中（`API_URL` / `MODEL` / `MAX_TOK` / `MAX_OUT`），可自行修改。

## KEY BINDINGS 快捷键

| 按键 | 行为 |
|---|---|
| `Ctrl+Space` | 立即暂停当前执行（不退出，回到提示符） |
| `Ctrl+X` | 请求压缩当前上下文（不打断执行；当前步骤自然结束后进入压缩流程） |

> 启动横幅：`新终端=新对话 | Ctrl+Space=暂停 | Ctrl+X=压缩`
> `Ctrl+X` 只设置请求标记，多次按下合并为一次压缩，不立即执行、不中断 LLM / Shell。

## ARCHITECTURE

```mermaid
flowchart TD
    A["welcome()<br/>first-run key setup + encrypt"] --> B["main()<br/>loop: llm <-> RUN<br/>+ 压缩桥接"]
    B --> C["llm()<br/>流式对话<br/>Ctrl+Space=暂停 / Ctrl+X=请求压缩"]
    B --> D["compress()<br/>512K 摘要链"]
    B --> E["RUN()<br/>唯一工具: shell 执行<br/>+ 按 dangerous 标志授权"]
    C --> F["build_context()<br/>mem_hist + summaries"]
    D --> F
    E --> F
    F --> G["key store<br/>encrypt/decrypt 机器种子"]
    F --> H["memory / skill / taskbook<br/>~/.config/term_agent/*.md"]
```

| 层 | 组件 | 职责 |
|---|---|---|
| ENTRY | `welcome()` | 首次运行引导，Key 加密入库 |
| CORE | `main()` | 主循环：LLM 对话、工具调用解析、结果回填、压缩请求桥接 |
| LLM | `llm()` | 流式 SSE；`Ctrl+Space` 暂停 / `Ctrl+X` 设压缩请求标记 |
| MEM | `compress()` / `build_context()` | 512K(`MAX_TOK`) 阈值压缩，摘要链跨会话延续 |
| TOOL | `RUN()` | 唯一工具：Shell 执行 + `dangerous` 标志授权闸门 |
| SEC | `encrypt/decrypt_key()` | 机器指纹种子加密，Key 不落明文 |

## SECURITY 安全模型

判定权在模型：宿主不扫描命令内容，只按 `RUN` 的 `dangerous` 标志分流。

```mermaid
flowchart LR
    A["RUN(cmd, dangerous)"] --> B{"dangerous == true?"}
    B -->|否| C["subprocess 直接执行"]
    B -->|是| D["confirm_block()<br/>push ⚠ 确认块"]
    D -->|"Y"| C
    D -->|"N / 超时"| E["拒绝返回<br/>命令未执行"]
```

| dangerous | 行为 |
|---|---|
| `false` | 直接执行，宿主不做二次校验 |
| `true` | 终端 push 确认块（⚠ + 命令全文），`Y` + 回车才执行 |

### 用户授权

| 项 | 值 |
|---|---|
| 超时 | `AUTH_TIMEOUT = 30`，设 `0` = 永不超时 |
| 接受输入 | `y` / `yes` + 回车（单键不算，全角等效） |
| 拒绝 | `N` / 超时 / `Ctrl+C` / `Ctrl+D` |

## NOTES

- 新终端 = 新对话（每个终端会话独立上下文）
- `Ctrl+Space` = 暂停；`Ctrl+X` = 请求压缩

## UPDATE 如何更新

安装脚本是**幂等**的：重复执行安装命令即可覆盖更新程序文件

## LICENSE

MIT

## Extras 扩展

- **Agent-Channel（微信/QQ 遥控通道）**：已独立为单独仓库 → [Xiyinnnnnn/Agent-Channel](https://github.com/Xiyinnnnnn/Agent-Channel)
