# 00-token消耗查询 — 四供应商 token 消耗 / 额度
STATE ✓ 2026-11-08｜SCOPE DeepSeek 官方、OpenRouter、OpenCode、CommandCode 四家余额与用量；`provider` 字段切换｜SCRIPT `token.mjs`
REF memory/反代-用量与额度查询现状.md

## 何时用
问「DeepSeek 还剩多少钱 / 消耗多快」「OpenRouter 余额与 key 限额」「OC key 还有效吗」「CommandCode 月额度 / 5 小时额度」时。

## 命令
```bash
ln -sfn ~/.config/term_agent/skill/token.mjs ~/.local/bin/token   # 首次
token ds                      # DeepSeek 官方（全名 deepseek）
token or                      # OpenRouter（全名 openrouter）
token oc                      # OpenCode（全名 opencode / zen）
token cc                      # CommandCode（全名 commandcode）
dsbalance / wallet / ccusage  # 旧软链，按 argv[1] 名推断 provider
```

## 参数 / 退出码
| 参数 / 环境 | 作用 |
|---|---|
| `provider` | `ds`／`or`／`oc`(=`zen`)／`cc`，全名亦可；`--provider` 等价且优先 |
| `--json`／`--key`／`--timeout` | 原始 JSON ／ 临时 key ／ 秒，默认 20 |
| `--no-save`／`--no-color` | 仅 deepseek：不写余额快照 ／ 关 ANSI |

| provider | 余额 / 用量来源 | key 源（先到先得） | 硬坑 |
|---|---|---|---|
| deepseek | `/user/balance`；无 usage 接口，靠快照差推算 | `--key`→`DEEPSEEK_API_KEY`→`deepseek.key`→`key.bin`(须 `sk-`) | `balance_infos` 可能仅 1 条，金额是字符串 |
| openrouter | `/credits` 购−用；`/key` 日/周/月 | `--key`→`openrouter.key`→`OPENROUTER_API_KEY` | `/credits` 需 Management key，403 降级显示限额 |
| opencode | 无公开余额接口；`opencode stats` 本地统计 | `--key`→`opencode.key`→`OPENCODE_API_KEY` | `/v1/models` 不带 key 也 200，判有效性必须带 key |
| commandcode | `credits.monthlyCredits`=剩余；`/alpha/usage/summary` | `--key`→`CC_KEY`→`key.bin`(XOR) | 必须 node fetch，curl/python 403 `code:1010`，反代 3050 404 |

| 码 | 含义 |
|---|---|
| `0`／`3` | 成功 ／ deepseek 余额不足（`is_available=false`） |
| `1`／`2` | 网络或非鉴权 HTTP ／ 无 key（stderr 给配置法） |
| `4`／`5` | 鉴权 401/403 ／ provider 未知，打印用法 |

## 失败处置
| 现象 | 动作 |
|---|---|
| `HTTP 401` | key 失效：换 key 或 `--key` 临时指定 |
| `HTTP 403` + openrouter | `/credits` 需 Management key；面板已自动降级显示 `/key` 限额 |
| commandcode `error code: 1010` | 换 curl/python 为 node fetch；本脚本已是 node |
| deepseek 无消耗行 | 同币种快照不足 1 小时或期间只充值：多查几次再判 |

## 陷阱
| 项 | 说明 |
|---|---|
| `limit` ≠ 余额 | openrouter 的 `limit` 是花费上限，余额看 `total_credits - total_usage` |
| 快照文件 | `~/.local/share/dsbalance/history.jsonl` 保留 2000 行，删掉即失去推算 |
