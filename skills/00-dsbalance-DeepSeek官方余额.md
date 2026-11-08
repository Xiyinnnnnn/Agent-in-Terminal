# 00-dsbalance — DeepSeek 官方余额查询
STATE ✓ 2026-11-08｜SCOPE 只查余额与消耗速率（官方**无** token 用量接口）｜SCRIPT `00-dsbalance.mjs`
REF memory/DeepSeek官方余额接口与快照推算.md

## 何时用
问「DeepSeek 还剩多少钱 / 余额 / 还能不能调用 / 烧得快不快 / 赠金还有多少」时。

## 命令
```bash
dsbalance                                   # 面板（~/.local/bin/dsbalance → 本目录 00-dsbalance.mjs）
dsbalance --json                            # 原始响应 + 历史条数
dsbalance --no-save                         # 只查不写快照
dsbalance --key sk-xxx                      # 临时指定 key
node ~/.config/term_agent/skill/00-dsbalance.mjs    # 不经 PATH 直调
```

## 参数 / 退出码
| 参数 / 环境 | 作用 |
|---|---|
| `--json` `--no-save` `--no-color` | 原始 JSON / 不写快照 / 关 ANSI |
| `--key sk-…` | 本次用该 key |
| `DEEPSEEK_API_KEY` | 首选 key 源 |
| `DEEPSEEK_KEY_FILE` | key 文件（整文件即 key） |
| `DS_BASE` | 换基址（mock 测试用，默认 `https://api.deepseek.com`） |
| `DS_HIST_FILE` | 换快照文件（默认 `~/.local/share/dsbalance/history.jsonl`） |

| 码 | 含义 |
|---|---|
| 0 | 查询成功且账户可用 |
| 1 | 网络失败 / 其它 HTTP |
| 2 | 无 key 可取 |
| 3 | 查询成功但 `is_available=false`（余额不足） |
| 4 | 鉴权失败（401/403，key 无效） |

## 失败处置
| 现象 | 动作 |
|---|---|
| `HTTP 401 · Authentication Fails` | key 无效或已吊销：换 `DEEPSEEK_API_KEY` |
| `exit 3` / 状态「不可调用」 | 余额耗尽：充值后重查；赠金过期也会掉 |
| 没有「近 X 天消耗」行 | 快照不足：需同币种 ≥2 条且首条距今 ≥1h |

## 陷阱
| 项 | 说明 |
|---|---|
| 官方只有余额 | 无 usage / 消耗接口；「用了多少」只能由本地快照差推算，非官方数字 |
| 双币种 | `balance_infos` 可能含 CNY 与 USD 两条，逐条看，别只取第一条 |
| 赠金会过期 | `granted_balance` 单独列；`total_balance`＝赠金＋充值 |
| key 来源隔离 | `key.bin` 解密值以 `sk-` 开头才采用，避免把 CommandCode 的 `user_` key 错发给 DeepSeek |
| 快照截断 | 历史保留最近 2000 行，超限自动重写 |
| PATH 入口 | `~/.local/bin/dsbalance` 是软链，改源文件即生效，勿另存副本 |
