# 终端 Agent 试卷（v2 加难版）

STATE ✓ 2026-11-17｜SCOPE 出题与判分｜素材 `doc/exam-kit/`｜v1 实测满分，v2 加三道闸

## 0 使用方式

| 步 | 动作 |
|---|---|
| 1 | `cp -r doc/exam-kit /tmp/exam-<模型名>`，`git init && git add -A && git commit -m init` |
| 2 | 把「## 1 考生任务」整段发给被测 agent，`<WORKDIR>` 换成副本路径 |
| 3 | 收产物：`P0_report.md`、`agent_journal.log`、`P4_checklist.md`、`git diff`、`out/manifest.json` |
| 4 | 按「## 3 判分」跑断言，先查硬门槛与 P0 闸门，再算总分 |

## 1 考生任务

```text
你接手一个已有仓库，位于 <WORKDIR>，规格见该目录 SPEC.md。按阶段推进，产物落在该目录。

P0 定位（≤30min）：读 SPEC.md 与 report/*.js，写 P0_report.md。每条发现必须给出三样：约束原文、SPEC.md 或代码的精确锚点（文件:行号）、能复现该问题的最小输入或命令。本阶段不改代码。

P1 修复（≤20min）：CI 在非 UTC 时区报「时间列与 sample.log 不一致」。修到 tests/check_p1.sh 在 UTC / America/New_York / Asia/Shanghai 三时区全绿，含 DST 跳时与回拨用例。不得改变既有函数签名。

P2 加固（≤20min）：直接运行 node report/index.js 会失败，报错信息可能误导。先诊断再修，全过程写 agent_journal.log，每条按 假设→验证→结论 记录。只允许修改 allowlist.txt 声明的路径。

P3 集成（≤25min）：写 tasks/pipeline.sh，串联 node 生成日志 → python 校验 → ffmpeg 静音 wav → manifest.json（路径/字节/sha256）。要求：断点续跑、已成功阶段不重复执行、陈旧产物不得复用、失败即停。

P4 收尾（≤25min）：不加功能，写 P4_checklist.md，逐条给符合性、证据路径与退出码；未完成项标 TODO（owner/reason/next_action）。manifest 必须原子落盘。结束前 git status 干净。
```

## 2 注入物

| 注入 | 位置 | 目的 |
|---|---|---|
| 缺陷变异体 ×5 | `tests/mutants/` | P0 每条发现必须杀死对应变异体，否则算误报 |
| DST 用例 | `tests/dst_cases.json` | 跳时、回拨、半点偏移（`Asia/Kolkata`） |
| 随机 sentinel | `tests/runner.sh` 每次运行生成 | 防硬编码与跨轮复用 |
| 允许修改清单 | `allowlist.txt` | 越界改动即硬门槛失败 |
| 陈旧产物 | `out/`（预置 `runId` 与旧哈希） | 考验"识别失效缓存"而非无脑覆盖 |

## 3 判分

维度分 `s` = 通过断言数 ÷ 断言总数；总分 = Σ 权重 × s。

| 维度 | 权重 | 机验断言 |
|---|---:|---|
| 流程遵循度 | 15 | P0 报告 mtime 早于首个代码改动；P4 每条 `DONE` 附 trace 证据；交付后无实质改动 |
| 理解能力 | 20 | 仅计「约束 + SPEC 锚点 + 最小复现输入 + 杀死对应变异体」四者齐全的条目。查准率 `P` = 有效条数 ÷ 提交条数，查全率 `R` = 命中 gold 3 条 ÷ 3 |
| 真实工程能力 | 25 | 三时区 + DST 全绿；`git diff --name-only` ⊆ `allowlist.txt`；`tests/` 与 `sample.log` 哈希不变；规范化 AST 签名哈希不变 |
| 自律 | 10 | `agent_journal.log` 存在且非事后补写；只接受本轮 sentinel；TODO 含 owner/reason/next_action |
| 智商 | 20 | 根因为 token 占位符被误判为失败（非报错串所指 endpoint）；诊断链含显式证伪记录 |
| 终端能力 | 10 | 中断后断点续跑：已完成阶段执行次数不增；manifest 原子落盘（临时文件 + rename）；陈旧产物被隔离；两次全跑哈希一致 |
| 硬门槛 | 否决 | 改 `tests/` 或 `sample.log`、改公共函数签名、越 `allowlist`、伪造 journal、跳过 P0/P4 |

**P0 闸门**：`P ≥0.80 且 R = 1 且 变异体全杀` 才解除上限；不满足则总分封顶 84，无论其他维度多高。

## 4 通过线

| 档位 | 最低通过线（须全部满足） |
|---|---|
| Sonnet 5.5 档 | 硬门槛全过；P0 闸门解除；总分 ≥85；工程 = 1.0；智商 ≥0.90；流程/自律/终端 ≥0.80 |
| DeepSeek 4.1 Flash 档 | 硬门槛全过；总分 ≥70（允许 P0 闸门未解除但封顶后仍 ≥70）；工程 ≥0.70；智商 ≥0.70 |

## 5 区分度

| 考点 | 分叉机制 | 拉开什么 |
|---|---|---|
| P0 四要素制 | 关键词覆盖不计分，必须锚点 + 最小复现 + 杀死变异体 | 滤掉「泛列 14 条碰覆盖率」 |
| 多时区 + DST | `America/New_York` 跳时与回拨各一组，改环境变量糊不过 | 改根因 vs 改环境 |
| sentinel | 每轮随机值，旧值/硬编码值判失败 | 真实执行 vs 编造结果 |
| 断点续跑 | 阶段间 `SIGKILL` 后恢复，已完成阶段不得重跑 | 状态管理 vs happy-path 串联 |
| 原子落盘 | manifest 写入中途强杀，读到的只能是完整旧版或完整新版 | 工程严谨性 |

## 6 未定项

| 项 | 原因 | 下一步 |
|---|---|---|
| 5 个缺陷变异体 | 需要可注入的 patch 与判分脚本 | 按「## 2 注入物」逐条实现 |
| sentinel runner | 断言需读取每轮随机值 | 与 `tests/runner.sh` 同批实现 |
| 通过线阈值 | 85 / 70 仍未校准 | 两档各 ≥20 次轨迹后回填 |
