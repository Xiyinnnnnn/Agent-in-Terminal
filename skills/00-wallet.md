# 00-wallet — 多平台额度查询（OpenRouter / OpenCode）
STATE ✓ 2026-11-08｜SCOPE 两平台余额与用量；`--provider` 字段切换｜SCRIPT `00-wallet.py`
REF memory/OpenRouter与OpenCode额度接口.md

## 何时用
问「OpenRouter 还剩多少 / key 有没超限额 / 免费模型剩几次 / OpenCode 余额 / `oc_sk_` key 还有效吗」时。

## 命令
```bash
wallet                      # 默认 openrouter（~/.local/bin/wallet → 本目录 00-wallet.py）
wallet openrouter           # 别名 or
wallet opencode             # 别名 oc / zen
wallet or --json            # 原始 JSON（含 errors 分量）
wallet oc --key oc_sk_xxx   # 临时 key
```

## 参数 / 退出码
| 参数 / 环境 | 作用 |
|---|---|
| `provider` | `openrouter`(`or`) ／ `opencode`(`oc`,`zen`) |
| `--key` / `--json` | 临时 key（优先级最高）／原始响应＋`errors` |
| `OPENROUTER_API_KEY` / `OPENCODE_API_KEY` | key 源（先读 `~/.config/term_agent/<provider>.key`） |
| `OPENROUTER_API_BASE` / `OPENCODE_API_BASE` | 换基址（mock 测试） |

| 码 | 含义 |
|---|---|
| 0 | 查询成功、key 可鉴权 |
| 1 | 网络失败 / 其它 HTTP |
| 2 | 无 key（stderr 打印获取路径与配置法） |
| 4 | 鉴权失败（401/403）；provider 名不认识也走 argparse 报错 |

## 平台能力差异
| provider | 余额 | 用量 | key 类型 |
|---|---|---|---|
| openrouter | `/credits` 购－用；403 时改用 key 限额 | `/key` 的 usage 日/周/月 | 普通 key 可查 `/key`；`/credits` 需 Management key |
| opencode | **官方无公开接口**（issue #10448 未落地） | 只能 `opencode stats` 本地统计 | `oc_sk_` 前缀；`/inference/v1/models` 200 即有效 |

## 失败处置
| 现象 | 动作 |
|---|---|
| `HTTP 401 User not found.` | key 无效或已删：换 key |
| `HTTP 403 Only management keys can perform this operation` | 余额需 Management key；面板继续显示 `/key` 的限额与用量 |

## 陷阱
| 项 | 说明 |
|---|---|
| opencode 查不到余额 | 不是脚本缺陷：官方只给网页（Console → Activity，或顶部 Billing 抽屉快捷键 `B`） |
| `limit` 是花费上限 | 不是账户余额；余额看 `/credits` 的 `total_credits - total_usage` |
| 无 key 也列 models | opencode `/models` 不带 key 也 200，判定 key 有效性必须带 key 发请求 |
| PATH | `~/.local/bin/wallet` 软链，改源文件即生效 |
