# Agent-in-Terminal（宿主）

## 是什么
零依赖 Python 单文件终端 Agent（787 行，零注释风格）。OpenAI 兼容 API，bash 工具执行，Bazzite 桌面常驻。
默认经本地 `commandcode-proxy` 反代（`127.0.0.1:3050`），由 `start_agent.sh` 探活拉起。

## 运行与数据
- 入口：本目录 `term_agent.py`（python3 直跑，零依赖）
- 桌面：`~/Desktop/term-agent.desktop` → `python3 ~/.local/bin/term_agent/term_agent.py`
- 数据：`~/.config/term_agent/` = `key.bin`（加密 API Key）+ `memory/` `skill/` `taskbook/`（agent 自产 md）

## 全局常量
| 常量 | 值 | 用途 |
|---|---|---|
| API_URL | `http://127.0.0.1:3050/v1/chat/completions` | 本地反代（OpenAI 兼容） |
| MODEL | `deepseek/deepseek-v4-flash` | CC 上游模型 ID（形如 `vendor/model`） |
| MAX_TOK | 524288 | **上下文压缩阈值**（usage 超此值触发压缩），非输出上限 |
| MAX_OUT | 32768 | 输出 max_tokens；压缩请求用 `MAX_OUT//4` |
| REASONING_EFFORT | high | 推理强度（body.`reasoning_effort`） |
| AUTH_TIMEOUT | 30 | 危险命令授权等待秒数；`<=0` 退回阻塞式 `input()` |
| MAX_NEST | 2 | 剥壳 / 命令替换各自递归上限（两者叠加最深 4 层） |
| SYSTEM | 内置提示词常量 | 每个请求的 system 消息（**不随代码同步覆盖**，见文末） |
| TOOLS | RUN 工具 schema | 工具定义 |

## 核心循环（main）
```
mem_hist = []            # 消息列表 [user/assistant/tool]
summaries = []           # append-only 快照链
loop:
  q = input()            # Ctrl+Space(0x00) 清空缓冲；Ctrl+X(0x18) 置压缩标志
  mem_hist.append(user q)
  inner loop:
    if need_compress:
      last_u = 最后一个 user 消息下标
      ns = compress(mem_hist[:last_u], summaries)
      if ns is None: break
      summaries.append(ns)
      mem_hist = mem_hist[last_u:]
      need_compress = False
    resp = llm(build_context(mem_hist, summaries))   # 流式；select 0s 轮询 stdin
    if resp None/API_ERROR: retry>10 → need_compress=True
    if resp.usage > MAX_TOK: need_compress=True
    否则处理 content / tool_calls（循环执行 RUN 并回填）
```
中断语义：流式收包与命令执行期间都 `select` 轮询 stdin ——`0x00` 抛 `_StopLoop` 立刻回主循环，`0x18` 置 `_compress_requested` 供下一轮压缩。

## 上下文 = 快照链 + 历史
```
build_context: [system SYSTEM] + [user s for s in summaries] + mem_hist
compress:      [system SYSTEM] + [user s for s in summaries] + hist + [user "[总结所有]"]
               → llm(stream=False, think=False, max_tokens=MAX_OUT//4)
               → 返回 "历史背景：" + 新快照文本
```
- 快照链 append-only：旧快照永不变更/不移除（prefix immutable）
- 压缩请求复用完整前缀 → 最大化 KV 命中
- 连续多条 user 消息（快照链）是设计，不是 bug

## 危险命令防护（2026-10-19 加固）
四层判定，任一命中即进授权闸门。

**① DANGER_BL 基线表（token 级）**
`rm` `dd` `mkfs*` `fdisk` `parted` `wipefs` `shred` `blkdiscard` `chmod -R 777` `:(){ :|:& };:` 等；
命中规则：basename 精确等于、或以 `b"."` / `b":"` 开头（覆盖 `mkfs.ext4` 这类）。

**② PIPE_PATTERNS 语义正则**
`find … -delete`、`git clean -fdx`、`chmod -R 000`、`kill -9 -1`、`truncate -s0`、`pkill/killall -9`、
find 的 `-exec` 调用删除类命令、cp 覆写块设备（`/dev/sd|nvme|vd|mmcblk`）。
注：`git clean -n` / `--dry-run` 属只读预演，正则已排除，不触发授权。

**③ 结构解析（`_first_hit` + `match_danger`）**
- 剥前缀：`sudo doas env nohup nice ionice timeout setsid xargs command exec stdbuf`、`-u/-g/-c/…` 带值选项、`VAR=x`、纯数字；**层数不设上限**（曾有 6 个 token 上限，`sudo -u root env A=1 nice -n 5 <危险命令>` 可绕过）
- `/bin/rm` → 取 basename → `rm`
- `sh|bash|zsh|ksh|dash|ash|busybox|fish -c '…'` → 剥壳递归
- `eval '…'` → 递归
- `$(…)` 与反引号 → 递归
- 变量间接执行：`x=rm; $x -rf /` 命中（**仅当本命令内赋过值**，故 `$EDITOR f` 不误伤）
- 管道进 shell：`… | sh`、`… | python/perl/ruby/node`

**④ 重定向覆盖**
`> 目标` 且目标**已存在**（`os.path.exists`）→ 命中。
放行：`> /dev/null`、`2>&1`、`>>` 追加、写新文件。

### 语法归一与包装器剥离（2026-10-19 第二批）
- 去混淆 `_deobf`：引号、反斜杠、空引号对、`${IFS}`、`$'\xNN'` 先归一，再取 base 判定
- 分组与关键字：`(` `)` `{` `}` `!` `if then do done fi case function` 等不再作为 base 逃逸点
- 包装器递归 `_RUN_WRAPPERS`：`su doas chroot nsenter proot run0 busybox script setpriv systemd-run` 余下部分递归判危险（`-c` 参数按命令处理）
- here-string：`sh/bash <<< "…"` 内层递归
- `find` 判定扩到 `-execdir` / `-ok` / `-okdir`
- 自毁类：`kill` 目标为进程组或自身（`0` / `-1` / `$$` / `$PPID`）直接拦
- 误报修正：脚本名（`.sh/.py/.pl/.rb/.js`）不再被前缀规则当命令；引号内 `>` 不再当重定向
- 运行期健壮性：主循环兜底 `except`（不再被单次异常终结会话）、Ctrl+C 只中断本轮（`KeyboardInterrupt` 转 `_StopLoop`）、`resp` 显式关闭、空 key 不抛 `TypeError`

### 授权闸门（confirm_block）
- 进闸门前 `tcflush(TCIFLUSH)`：清掉提示框出现前的预输入，封死"没看提示就被放行"
- 归一化 `NFKC` + strip + lower：全角 `ｙ/Ｙ/ｎ/Ｎ` 与半角等效
- 必须 `y/yes` + **回车**；单键不算（防误触放行危险命令）
- 30s 无输入 → 自动拒绝；非法输入 → 重问；`Ctrl+C`/`Ctrl+D` → 拒绝

### 判定矩阵（回归基准，47 例）
必拦 22：`rm -rf ~/x`、`sudo rm -rf /`、`/bin/rm`、`xargs rm`、`echo a | sh`、`dd if=/dev/zero of=/dev/mmcblk0`、
`bash -c 'rm -rf'`、`sh -c 'rm -rf /'`、`eval 'rm -rf'`、`echo $(rm -rf)`、`$(rm -rf)`、`x=rm; $x -rf`、`c=$(echo rm); $c -rf`、
`bash -c "eval \"rm -rf /\""`、`find . -delete`、`truncate -s0 ~/.bashrc`、`echo x > ~/.bashrc`、`git clean -fdx`、
`chmod -R 000`、`kill -9 -1`、`rm`
必放 17：`ls > 新文件`、`> /dev/null`、`make 2>&1 | tee`、`cat a >> ~/.bashrc`、`git status`、`find -name`、
`kill 1234`、`bash -c 'echo hi'`、`eval "$(date)"`、`echo "$(date)"`、`./build.sh`、`truncate --size=100`、
`python3 -c 'print(1)'`、`$EDITOR f`、`${EDITOR} f`、`vim $HOME/x`、`awk '{print $1}'`、`git clean -n`、`git clean --dry-run`

### 已知边界（有意不做）
`sed -i` 原地改、`mv` 覆盖、`tee 已存在文件`、`python3 -c "open(...,'w')"` 不拦（静态不可判）；
转义引号造成的分段错乱已修（`_split_segs` 支持 `\` 转义）；
`> 目录`（如 `echo x > /tmp`）会误拦；`>|file`（noclobber 写法）轻微漏。

## 进程回收
- `RUN` 用 `start_new_session=True` 建独立进程组
- `_kp(p)` **无条件** `killpg(SIGKILL)`：主进程已退出时，组内孙进程可能仍持有 tty 并读走键盘输入
  （曾表现为"授权按了 y 却毫无反应"）；旧版 `if p.poll() is None` 守卫会让这步被整体跳过
- `RUN` 的 `finally` 统一 `_kp(_proc)`，避免残留

## 崩溃兜底
`q=_img(q)` 包 `try/except`：未闭合引号（`shlex.split` 抛 `ValueError`）等异常按纯文本处理，不再退出主循环。

## 函数地图
| 函数 | 职责 |
|---|---|
| main | 交互循环 + 压缩调度 + 工具循环 |
| llm | OpenAI 兼容请求，流式解析 content/reasoning/tool_calls/usage；stdin 轮询支持中断 |
| build_context | SYSTEM + 快照链 + 历史 |
| compress | 压缩历史 → 新快照（append） |
| sanitize_hist | 丢弃 tool_calls 与 tool 回填不配对的消息段 |
| match_danger / _first_hit / _split_segs / _unquote | 危险判定四层 |
| confirm_block | 授权闸门（tcflush + NFKC + 回车确认） |
| RUN | 执行命令，select 边读边响应中断，超时 3600s |
| _kp | 无条件 killpg 回收整组 |
| _img / _shrink / _shrink_raw / _dec / _enc | 图片转 base64（自研解码，无外部依赖） |
| load/save_api_key | key.bin 读写（machine-id XOR + base64，0600） |

## 密钥
`API_KEY = load_api_key()` 只从 `~/.config/term_agent/key.bin` 读，源码内不含明文 Key；
缺失时 `main` 调 `welcome()` 向导写入（保存即 `chmod 600`）。换 Key 只需重写 key.bin，不必改源码。

## 改哪 / 怎么验
- 改提示词 → `SYSTEM`（**同步到别的机器时严禁整文件覆盖**：本仓库这份是 Bazzite，Termux 侧有其自己的环境口径）
- 改黑名单 → `DANGER_BL` / `PIPE_PATTERNS` / `_first_hit` / `match_danger`（四处联动）
- 改闸门 → `confirm_block`（`tcflush` 与 `NFKC` 两处都不要回退）
- 改压缩 → `compress` / `build_context` / `main` 压缩段（三处联动）
- 语法：`python3 -m py_compile term_agent.py`
- 危险判定回归（不启动宿主，直接加载模块）：
```python
import importlib.util
spec = importlib.util.spec_from_file_location("ta", "term_agent.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert m.match_danger("bash -c 'rm -rf ~/x'") == "bash -c → rm"
assert m.match_danger("echo $(rm -rf /tmp/x)") == "命令替换 → rm"
assert m.match_danger("echo x > ~/.bashrc").startswith("重定向覆盖")
assert m.match_danger("$EDITOR notes.md") is None
assert m.match_danger("echo hi > /dev/null") is None
```

## 约束
- 新终端 = 新对话（`mem_hist` 纯内存，无持久化）
- 压缩请求非流式、关闭思考（`think=False`）
- 依赖 `readline`（交互输入）
- 单命令执行上限 3600s，超时整组 kill
- 零注释风格：解释写进本文件，源码不写行内注释
