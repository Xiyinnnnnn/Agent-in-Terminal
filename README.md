# 以下内容追加到 README.md 末尾（UPDATE 段落）

## UPDATE 如何更新

安装脚本是**幂等**的：重复执行安装命令即可覆盖更新程序文件，不会动你的配置和记忆：

```bash
# 方式一：重新执行安装命令（推荐，覆盖 install.sh / term_agent.py / .desktop 三件套）
curl -fsSL https://cdn.jsdelivr.net/gh/Xiyinnnnnn/Agent-in-Terminal@main/install.sh | bash
```

```bash
# 方式二：只更新主程序（脚本装好后的日常更新用这个最快）
curl -fsSL https://cdn.jsdelivr.net/gh/Xiyinnnnnn/Agent-in-Terminal@main/term_agent.py -o ~/.local/bin/term_agent/term_agent.py
```

```bash
# 方式三：直接对 agent 说「更新你自己」（它自带 shell 工具，会自己拉取）
```

> 安全：重跑安装命令不会覆盖 `~/.config/term_agent/`（API Key、记忆），放心更新。
> 注意：jsDelivr 是 CDN，推送后约 2~5 分钟生效；刚 push 完想立即验证请用 GitHub raw 直连地址。
