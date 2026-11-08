# CommandCode 用量 / 额度查询
STATE ✓ 2026-11-08｜SCOPE 只读查 token 消耗、信用额度、5h/周窗口、订阅周期；零 token 消耗｜SCRIPT ccusage.mjs
REF memory/反代-用量与额度查询现状.md

## 何时用
问「用了多少 / 还剩多少额度 / token 消耗 / 5 小时窗口 / 周窗口 / 订阅什么时候到期 / 会不会撞限流」时。

## 命令
```bash
ccusage                 # 面板（~/.local/bin/ccusage → 本目录 ccusage.mjs）
ccusage --no-color      # 纯文本，给管道/日志
ccusage --json          # 四端点原始 JSON
node ~/.config/term_agent/skill/ccusage.mjs    # 不经 PATH 直调
```

## 参数 / 退出码
| 参数 | 作用 |
|---|---|
| `--json` | 原始 JSON（含 `fails`） |
| `--no-color` | 关 ANSI |
| `CC_KEY` | 直接给 key，优先于 key.bin |
| `CC_KEY_FILE` | 换 key 文件路径 |
| `CC_API_BASE` | 换上游基址 |

| 码 | 含义 |
|---|---|
| 0 | 全端点成功 |
| 1 | 有端点失败（面板末行列出） |
| 2 | 无 key 可取 |

## 失败处置
| 现象 | 动作 |
|---|---|
| `HTTP 403` + `error code: 1010` | CF 拦 TLS 指纹：只认 node `fetch`，别用 curl/python 直连 |
| `HTTP 401 / 403` 且 body 无 1010 | key 失效：重写 `~/.config/term_agent/key.bin` 后重启宿主 |
| 端点 `HTTP 404` | 上游改版：`--json` 看哪个，重查官方 CLI 新版路由 |
| 面板两窗口相等 | 正常：本周期首请求后两窗口同时开启 |

## 陷阱
| 项 | 说明 |
|---|---|
| 别绕反代 | 3050 只代理 5 条路由，`/alpha/*` 一律 404；直连即可 |
| 不烧额度 | 四个端点全只读，不计 credits |
| `monthlyCredits` | 是**剩余**，不是已用；已用看 `usage/summary.totalCredits` |
| 时间戳 | `resetAt` / `periodStart` 为毫秒，脚本已转本地时 |
| 官方等价物 | CLI 内 `/usage` 命令同源，本脚本免装 CLI |
| PATH 入口 | `~/.local/bin/ccusage` 是软链，改源文件即生效，勿另存副本 |
