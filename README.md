# AGENT IN TERMINAL

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Termux-green.svg)]()

A lightweight AI agent that lives in your terminal.

基于 DeepSeek 官方 API，支持 Shell 工具执行、上下文压缩、Skills 扩展与多代理协作。

## QUICK START

**一键安装**

```bash
curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
```

安装脚本会自动：

- 判断当前环境（Linux / Termux）。
- 安装对应系统依赖。
- 检查并准备 Python 运行环境。
- 安装 Pillow（PIL）图像处理依赖。
- 安装 Agent 主程序及 Skills。
- 根据平台配置启动入口：
  - **Termux**：配置 `agent` 快捷命令。
  - **Linux**：创建桌面快捷方式。

首次运行时按提示配置 DeepSeek API Key。

安装完成后，直接运行：

```bash
agent
```

首次启动时按提示配置 DeepSeek API Key。

## USAGE

```bash
agent
```

启动新对话。

```bash
agent-update
```

更新 Agent。

也可以通过环境变量配置 API Key：

```bash
export DEEPSEEK_API_KEY="sk-..."
agent
```

## KEY BINDINGS

| Key | Action |
|---|---|
| `Ctrl + Space` | 暂停当前执行并返回提示符 |
| `Ctrl + X` | 请求压缩上下文 |

## ARCHITECTURE

```text
Agent-in-Terminal/
├── term_agent.py       # Agent 主程序
├── install.sh          # 自动安装脚本
├── launch.sh           # 启动入口
├── skills/             # Skills 扩展
└── doc/                # 项目文档
```

**Runtime**

- Python 3.10+
- Pillow（PIL）
- DeepSeek Official API

主程序使用 Python 标准库处理核心逻辑，Pillow 用于图像处理。

## SECURITY

- API Key 优先从环境变量读取。
- 本地 Key 保存在 `~/.config/term_agent/key.bin`。
- 不要将 API Key 提交到 Git 仓库或公开日志。
- 执行命令前注意检查危险操作。

## NOTES

- 支持 Linux 与 Termux（Android）。
- 安装脚本会根据运行环境选择依赖安装方式。
- `tmux`、`ffmpeg`、`yt-dlp`、`adb` 等工具用于部分扩展 Skill，具体功能取决于对应工具是否安装。
- Agent 需要可用的 DeepSeek API Key 和网络连接。

## UPDATE

```bash
agent-update
```

也可以重新执行一键安装命令。

## LICENSE

MIT License

## Extras

[Agent-Channel](https://github.com/Xiyinnnnnn/Agent-Channel)：独立的微信 / QQ 遥控通道项目。
