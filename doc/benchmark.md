# 终端 Agent 基准测试（v2 加难版）

STATE ✓ 2026-11-17｜SCOPE 出题与判分｜素材 `doc/benchmark-kit/`｜v1 实测满分，v2 加三道闸

## 0 使用方式

| 步 | 动作 |
|---|---|
| 1 | `cp -r doc/benchmark-kit /tmp/bench-<模型名>`，`git init && git add -A && git commit -m init` |
| 2 | 把「## 1 考生任务」整段发给被测 agent，`<WORKDIR>` 换成副本路径 |
| 3 | 收产物：`P0_report.md`、`agent_journal.log`、`P4_checklist.md`、`git diff`、`out/manifest.json` |
| 4 | 按「## 3 判分」跑断言，先查硬门槛与 P0 闸门，再算总分 |
| 5 | 跑前把 `~/.config/cli-agent/{skill,memory,taskbook}` 复制到备份目录；**禁止执行 `push_skills.py` 或 `git push`**，考场产物不算 `00-` 技能 |
| 6 | 跑后还原：删除本次新增的 `skill/*.md`、`memory/*.md`、`taskbook/*-eol.md`，再核对 `5s_check` errors=0 |

## 1 考生任务

```text
你接手一个已有仓库，位于 <WORKDIR>，规格见该目录 SPEC.md。按阶段推进，产物落在该目录。

P0 定位（≤30min）：读 SPEC.md 与 report/*.js，写 P0_report.md。每条发现必须给出三样：约束原文、SPEC.md 或代码的精确锚点（文件:行号）、能复现该问题的最小输入或命令。本阶段不改代码。

P1 修复（≤20min）：CI 在非 UTC 时区报「时间列与 sample.log 不一致」。修到 tests/check_p1.sh 在 UTC / America/New_York / Asia/Shanghai 三时区全绿，含 DST 跳时与回拨用例。不得改变既有函数签名。

P2 加固（≤20min）：直接运行 node report/index.js 会失败，报错信息可能误导。先诊断再修，全过程写 agent_journal.log，每条按 假设→验证→结论 记录。只允许修改 allowlist.txt 声明的路径。

P3 集成（≤25min）：写 tasks/pipeline.sh，串联 node 生成日志 → python 校验 → ffmpeg 静音 wav → manifest.json（含 run_id、每个文件路径/字节/sha256）。run_id 取自环境变量 BENCH_RUN_ID，为空时自行生成。要求：断点续跑、已成功阶段不重复执行、陈旧产物不得复用、失败即停、manifest 原子落盘。

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
| 终端能力 | 10 | 中断后断点续跑：已完成阶段执行次数不增；manifest 原子落盘（临时文件 + rename）；陈旧产物被隔离；两次全跑 files 哈希一致且 run_id 不同 |
| 硬门槛 | 否决 | 改 `tests/` 或 `sample.log`、改公共函数签名、越 `allowlist`、伪造 journal、跳过 P0/P4 |

**P0 闸门**：`P ≥0.80 且 R = 1 且 变异体全杀` 才解除上限；不满足则总分封顶 84，无论其他维度多高。

## 4 通过线

单一线：**总分 ≥80 才能用，低于 80 不可用**。

| 版本 | 实测 | 判定 |
|---|---|---|
| v1 | 100 | 可用 |
| v2 | 100 | 可用 |
| v3 | 80（仅计可判项） | 压线可用 |

阈值未用弱模型对照校准；一旦引入更弱模型，80 这条线才有区分意义。

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
| 通过线阈值 | 85 / 70 仍未校准 | 两档各 ≥20 次轨迹后回填 |
| v3 素材 | 9 检查点包图、故障注入器、私有种子评分器未建 | 见「## 7」 |

## 7 v3 加难（设计已定，素材待建）

外部参考：Terminal-Bench（ICLR 2026）——任务需数百依赖动作与长时序状态，考验跨序列保态、死路恢复、自知完成、抗记忆化、分级奖励；最常见失败是 command-not-found（规划与执行脱节）；轮数与 token 数同成功率无相关。

| 措施 | 分 | 新增 | 机验断言 |
|---|---|---|---|
| 长链状态 | 45 | 9 检查点迁移链：环境探测 → codemod → 依赖迁移 → 锁文件 → 构建 → 测试 → 打包 → 干净安装 → 审计；逐级发布，后段消费前段真实产物 | 跳级、伪造摘要、重放不一致均拒绝；每过 1 个检查点 5 分，允许部分分 |
| 执行失真恢复 | 30 | 检查点注入两故障：`node`/`npm` 不可用（素材内藏本地工具链）、上游 schema 变更令旧 codemod 失效；保留故障前工作区 | 干净重放必现两故障；trace 无 reset；工具自救 10 分、保态恢复并全绿 20 分；重置后通过本项 0 分 |
| 私有变体 | 25 | 每场由 `BENCH_SEED` 改包名、数据与故障位置；提交 run-id 与最终树摘要 | 公开与私有种子 clean-replay 全绿、测试哈希未变、无网络；泛化 15 分 + 五变异全杀 5 分 + 声明与 trace 一致 5 分 |

已落地：`BENCH_SEED` + `tests/gen_records.js`（每场输入数据不同，抗记忆化）。
待建：9 检查点包图、故障注入器、私有种子评分器。v2 仍是当前唯一可整卷判分的版本。
