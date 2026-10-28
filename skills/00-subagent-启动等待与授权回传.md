# 00-subagent-启动等待与授权回传

STATE ✓ 2026-10-29｜SCOPE 派活给持久子代理并在完成/授权时收回控制权｜SCRIPT `subagent.py`
REF `memory/subagent-tmux管道与非tty授权通道.md`（机制与实测口径）

## 何时用
| 条件 | 动作 |
|---|---|
| 长任务交独立子代理，主 Agent 不空转轮询 | `start` |
| 已 start 过、事件丢失要接着等 | `watch` |
| 收到 `ev=auth` | 读 `cmd` → 判断 → `reply` |
| 收到 `ev=done` | `tail` 验产物，再决定下一步 |
| 要补新指令 | `send` |

## 命令
```bash
S=~/.config/term_agent/skill/subagent.py
python3 $S start -n job1 --task "只回复 ok，不调工具"   # 启动并入监听，返回即事件
python3 $S watch -n job1                               # 续等下一事件
python3 $S send  -n job1 -m "继续第 2 步"
python3 $S reply -n job1 -a y                          # y 批准 / n 拒绝
python3 $S tail  -n job1 -l 40
python3 $S ls
python3 $S kill  -n job1
```

## 返回（stdout 单行 JSON）
| ev | 字段 | 码 | 含义 |
|---|---|---|---|
| `done` | `session,sec,log,tail` | 0 | 子代理交还输入权（`你> ` 在尾且静默 2s） |
| `auth` | `session,sec,log,cmd` | 0 | 授权待决；`cmd` = 被请求的命令原文 |
| `timeout` | `session,sec,log,tail` | 1 | 超 `--timeout`（默认 1800s），非完成 |
| `sent` `replied` `killed` `ls` | — | 0 | 管理回执 |
| `err`（stderr） | `msg` | 1 | 见 FAIL |

## FAIL
| msg / 现象 | 原因 | 动作 |
|---|---|---|
| `session_exists:N` | 同名会话在跑 | 换名或先 `kill` |
| `not_ready:…` | 25s 内无提示符 | `tail` 查 key 解密与反代 `:3050` |
| `no_session:N` | 会话已退 | `ls` 后 `start` 重来 |

## 陷阱
| 现象 | 原因 | 处置 |
|---|---|---|
| `auth` 挂很久不超时 | 子代理 stdin 为管道→`isatty()` 假→`input()` 无限等 | 正常；正是它保住 30s 授权窗口 |
| 子代理 RUN 内 Ctrl+C / Ctrl+Space 失效 | 同因，`old=None` 不设 cbreak | 长命令靠 `--timeout`（宿主 RUN 上限 3600s） |
| 决策被吞成下一条提问 | RUN 执行中不读 stdin | 只在见到 `auth`/`done` 后 `send` `reply` |
| 完成误报 | 回答正文含 `你> ` | 已限定尾部+静默 2s；存疑用 `tail` 复核 |
| 日志乱码 | `pipe-pane` 记原始字节含 ANSI | 一律用 `tail` 子命令，别 `cat` |
