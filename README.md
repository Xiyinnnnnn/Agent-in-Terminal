# Agent-in-Terminal

轻量级终端 AI Agent：DeepSeek 官方 API + Shell 工具执行 + 上下文压缩 + Skills。

- Python 3.10+
- 主程序仅使用 Python 标准库，无需 `pip install`
- 默认模型：`deepseek-flash`
- API：DeepSeek 官方 OpenAI 兼容 Chat Completions
- 支持 Linux 与 Termux（Android）

## Termux 一键安装

在 Termux 中执行：

```bash
curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
```

安装完成后：

```bash
agent
```

更新：

```bash
agent-update
```

安装器会安装 Python、curl、tar、tmux、ffmpeg、android-tools，并尝试安装 yt-dlp。主程序与 Skills 安装在 Termux 前缀目录和 `~/.config/term_agent/skill/`。

首次运行会提示输入 DeepSeek API Key。也可以通过环境变量提供：

```bash
export DEEPSEEK_API_KEY="sk-..."
agent
```

环境变量优先于本地保存的 Key。不要把真实 Key 提交到 Git 仓库、截图或公开日志中。

## Linux 手动运行

```bash
python3 term_agent.py
```

或在项目目录运行：

```bash
./launch.sh
```

## DeepSeek API 配置

项目默认直接访问 DeepSeek 官方 API，不再依赖 `127.0.0.1:3050`、commandcode-proxy 或其他本地网关。

| 配置 | 默认值 |
|---|---|
| API URL | `https://api.deepseek.com/chat/completions` |
| 模型 | `deepseek-flash` |
| 推理强度 | `high` |
| 最大输出 | `32768` tokens |
| 压缩触发阈值 | `900000` tokens |

模型可通过环境变量切换：

```bash
export TERM_AGENT_MODEL=deepseek-flash
# 或
export TERM_AGENT_MODEL=deepseek-v4-pro
```

`deepseek-flash` 支持文本与图像输入；`deepseek-v4-pro` 当前为文本模型。模型是否可用、上下文长度、输出上限和价格以 DeepSeek 官方模型列表为准。

官方文档：

- [首次调用 API](https://api-docs.deepseek.com/zh-cn/)
- [Chat Completions API](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion/)
- [模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)
- [模型列表 API](https://api.deepseek.com/models)
- [项目 API 接入说明](doc/deepseek-api.md)

### API Key 保存

- 首选 `DEEPSEEK_API_KEY` 环境变量。
- 未设置环境变量时，首次运行会使用隐藏输入提示录入 Key。
- 本地保存位置：`~/.config/term_agent/key.bin`，权限设为 `0600`。
- 兼容旧版本已有的 `key.bin`，无需重新录入。

安全说明：当前 `key.bin` 使用机器信息派生的 XOR 混淆并设置文件权限，并非现代密码学意义上的强加密。对高安全要求的环境，建议使用环境变量或 Termux 私有目录权限保护，并避免共享设备账户。

## 使用与快捷键

| 按键 | 行为 |
|---|---|
| `Ctrl+Space` | 暂停当前执行并返回提示符 |
| `Ctrl+X` | 请求压缩上下文；当前步骤结束后处理 |

新终端启动即新对话。Agent 通过 `RUN` 工具执行 Shell 命令；危险操作由模型在工具参数中标记 `dangerous=true` 后触发终端确认。

**安全边界：** 宿主根据模型返回的 `dangerous` 标志决定是否弹出确认。若模型错误地把危险命令标记为 `false`，命令会直接执行。不要在不可信环境中运行；执行前应审阅命令。

## 数据目录

```text
~/.config/term_agent/
├── key.bin
├── memory/
├── skill/
└── taskbook/
```

安装更新时：
- 更新主程序；
- 同步仓库自带 Skills；
- 只删除上次安装器记录、且已从仓库移除的原厂 Skills；
- 保留 `key.bin`、`memory/`、`taskbook/` 和用户自建技能。

## Skills 与可选依赖

| 工具 | 用途 | Termux 包 |
|---|---|---|
| `tmux` | `subagent.py` 持久子代理 | `tmux` |
| `ffmpeg` / `ffprobe` | `videowatch.py` 视频抽帧 | `ffmpeg` |
| `yt-dlp` | 下载网络视频 | `yt-dlp` |
| `adb` | `ctxinject.py` Android 截屏 | `android-tools` |
| Pillow | 手动图片裁切/转码示例 | `python-pillow` |

安装器会安装上述系统包。`ctxinject.py` 的运行时注入还要求目标进程与脚本在相同 UID、兼容的 Python 解释器和可访问的文件系统环境下运行；Android/proot 边界可能限制该功能。

## 项目结构

```text
term_agent.py       Agent 主程序
install.sh          Termux 一键安装器
launch.sh           项目目录内启动器
requirements.txt    依赖说明（主程序零 pip 依赖）
skills/             原厂 Skills
doc/                开发、基准测试文档
```

## License

MIT

## Extras

[Agent-Channel](https://github.com/Xiyinnnnnn/Agent-Channel)：独立的微信/QQ 遥控通道项目。
