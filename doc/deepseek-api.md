# DeepSeek 官方 API 接入

## 当前配置

| 项 | 值 |
|---|---|
| 协议 | OpenAI-compatible Chat Completions |
| URL | `https://api.deepseek.com/chat/completions` |
| 默认模型 | `deepseek-flash` |
| 可选模型 | `deepseek-v4-pro` |
| 鉴权 | `Authorization: Bearer <API_KEY>` |
| 推理模式 | `thinking.type=enabled` |
| 推理强度 | `reasoning_effort=high` |
| 流式输出 | SSE，`stream=true` |
| 用量 | `stream_options.include_usage=true` |
| 工具调用 | Function Calling，`tool_choice=auto` |

模型名称、能力与价格可能变化，部署时以 DeepSeek 官方模型列表为准。

## API Key

读取顺序：

1. 环境变量 `DEEPSEEK_API_KEY`。
2. `~/.config/term_agent/key.bin`。
3. 首次启动隐藏输入。

推荐在 Termux 的 shell 配置文件中设置环境变量：

```bash
export DEEPSEEK_API_KEY="sk-..."
```

不要把 Key 写进项目源码或提交到 Git。

## 模型切换

默认使用 `deepseek-flash`。需要切换时：

```bash
export TERM_AGENT_MODEL=deepseek-flash
```

或：

```bash
export TERM_AGENT_MODEL=deepseek-v4-pro
```

`deepseek-flash` 支持文本与图片输入。`deepseek-v4-pro` 当前为文本模型。图片输入时不要使用 Pro。

## 请求结构

正常推理的请求体等价于：

```json
{
  "model": "deepseek-flash",
  "messages": [
    {"role": "system", "content": "system prompt"},
    {"role": "user", "content": "hello"}
  ],
  "max_tokens": 32768,
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "RUN",
        "description": "在终端执行 shell 命令",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {"type": "string"},
            "explain": {"type": "string"},
            "dangerous": {"type": "boolean"}
          },
          "required": ["command", "explain", "dangerous"]
        }
      }
    }
  ],
  "tool_choice": "auto",
  "stream": true,
  "stream_options": {"include_usage": true}
}
```

压缩请求关闭思考、关闭流式输出、移除工具定义，使用 `max_tokens=MAX_OUT//4`。

## 流式解析

Agent 消费 SSE `data:` 行，遇到 `[DONE]` 结束：

| 字段 | 用途 |
|---|---|
| `choices[0].delta.content` | 正文增量 |
| `choices[0].delta.reasoning_content` | 思考内容增量 |
| `choices[0].delta.tool_calls` | 分段工具调用 |
| `choices[0].finish_reason` | 停止原因 |
| `usage.total_tokens` | 本次请求 token 总量 |

工具调用的 `arguments` 可能跨多个 SSE chunk，Agent 按 `index` 聚合后再解析 JSON。

## 上下文与输出上限

当前项目本地参数：

| 参数 | 值 | 说明 |
|---|---:|---|
| `MAX_TOK` | 900000 | 收到响应 usage 后的压缩触发阈值 |
| `MAX_OUT` | 32768 | 单次请求的最大生成 token 数 |

DeepSeek 当前模型上下文窗口与最大输出上限以官方模型与价格页为准。`MAX_TOK` 是 Agent 的压缩策略阈值，不是服务端硬限制。

## 错误诊断

| HTTP / 错误 | 检查 |
|---|---|
| 401 | API Key 是否正确、是否已撤销 |
| 403 | 账户权限、模型访问权限 |
| 429 | 速率限制、余额与可用额度 |
| 400 | 模型 ID、请求体字段、工具定义、上下文长度 |
| 网络错误 | Termux 网络、DNS、TLS、代理环境 |

主程序会输出 HTTP 错误码与截断后的 API 响应正文。不要公开粘贴包含密钥或敏感提示词的日志。

## 官方资料

- 首次调用：https://api-docs.deepseek.com/zh-cn/
- Chat Completions：https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/
- 图像理解：https://api-docs.deepseek.com/zh-cn/guides/vision/
- 图像理解：https://api-docs.deepseek.com/zh-cn/guides/vision/
- 模型与价格：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
- 模型列表：https://api.deepseek.com/models
