# 以下内容替换 README.md 中的 QUICK START 段落

## QUICK START

全球 CDN 一键安装（国内直连，无需代理）：

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/Xiyinnnnnn/Agent-in-Terminal@main/install.sh | bash
```

GitHub 直连（海外用户）：

```bash
curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
```

> 脚本内部自动双源回退：优先走 jsDelivr CDN，失败自动切 GitHub raw，无需手动选择。
> 注意：jsDelivr 是 CDN，代码更新后约 2~5 分钟生效，刚 push 完请稍等片刻再安装。

首次运行输入 DeepSeek API Key：

- 输入不可见（getpass）
- 机器绑定加密落盘（`~/.config/term_agent/key.bin`）
- 唯一落盘项，不出现明文
