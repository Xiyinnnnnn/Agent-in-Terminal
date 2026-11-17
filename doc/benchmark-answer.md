# 基准测试答案

STATE ✓ 2026-11-17｜SCOPE 标准答案 + 一次实测轨迹（对应试卷 v1）｜v2 已实测｜素材 `doc/benchmark-kit/`

## 1 标准答案

| 阶段 | 正确产物 | 关键点 |
|---|---|---|
| P0 | 隐含约束清单，带 `文件:行号` | 三条 gold：① 禁改 `formatTimestamp(ms)` / `renderRow(r)` 签名（`tests/hidden_p1.js:4` 直接当 API 用）② 日志必须走 `report/logger.js`（`SPEC.md:29`）③ `ts` 是唯一时间源（`SPEC.md:13`），不得引入 `Date.now()` |
| P1 | `report/report.js` 的 6 个本地 getter 换 `getUTC*` | 签名与导出名不变；只改 `report.js` 一处即可让三时区全绿 |
| P2 | 根因 = `token === '[REDACTED]'` 被当成运行失败 | `endpoint unreachable` 是写死的字符串，与网络无关；正解是降级并明确告知"配置未就绪" |
| P3 | `tasks/pipeline.sh`：node→python→ffmpeg→`manifest.json` | 幂等（重跑字节一致）、`set -euo pipefail`、临时文件 `trap` 清理、ffmpeg `-bitexact` |
| P4 | `P4_checklist.md` + 干净 `git status` | 每条带证据路径；未做项标 TODO（owner/reason/next_action）而非硬凑 |

## 2 一次实测轨迹

| 项 | 值 |
|---|---|
| 作答者 | tmux 子代理（`subagent.py`）· 本机反代 `deepseek/deepseek-v4-flash` |
| 用时 | 287 s |
| 产物 | `P0_report.md` 6033 B · `agent_journal.log` 8424 B · `tasks/pipeline.sh` 99 行 · `out/manifest.json` |
| 自产 | 技能 `00-日志契约审计-时区流向幂等.md` + 任务书 `报告器修复v1.0-eol.md` |
| 判分 | **100 / 100**，六维度全满 |
| 对照门槛 | Sonnet 5.5 档要求 ≥85 → 通过 |

## 3 判分证据

| 维度 | 得分 | 证据 |
|---|---|---|
| 流程遵循度 | 15/15 | `P0_report.md` mtime 20:29:26 早于首个代码改动 20:29:33；P4 每条带证据路径；交付后 `git status` 空 |
| 理解能力 | 20/20 | 三条 gold 全中，另列出 14 条隐含约束（B1–B14），每条带违反点与行号 |
| 真实工程能力 | 25/25 | `tests/check_p1.sh` 三时区 rc=0；`git diff --stat` 仅 3 文件；`tests/` 与 `sample.log` 未改 |
| 自律 | 10/10 | `agent_journal.log` 84 行、8 类事件；同态命令无 ≥3 次；风险项按 YAGNI 登记未盲改 |
| 智商 | 20/20 | 根因命中 token 守卫；显式证伪 `endpoint unreachable` 假设；诊断链 复现→证伪→定位→验证 齐 |
| 终端能力 | 10/10 | 连跑两次 `manifest.json` sha256 一致；`set -euo pipefail`；`trap` 清临时文件；失败即停已验证 |

## 4 校准结论

| 观察 | 含义 | 建议 |
|---|---|---|
| 子代理 P0 给出 14 条约束，远超 gold 的 3 条 | 试卷对当前配置偏易 | 提难度：增加干扰文件、把约束藏进提交历史、或缩短时限 |
| P1–P3 一次通过，无返工 | 区分度未被触发 | 需要更多"诱饵失败"（P2 式误导）才有分档空间 |
| 宿主对分数贡献显著：BOOT/技能/任务书流程均自动执行 | 测的是「宿主 + 技能集 + 模型」的整体 | 若要单测模型智商，需在无技能集的最小宿主上重跑 |
| 100 分说明门槛 85 / 70 对 flash 档无区分力 | 阈值需按实测回填 | 两档各 ≥20 次轨迹后上调阈值或加难 |

## 5 v2 加难与 v1 的关系

| 项 | v1（本答案实测） | v2（当前试卷） |
|---|---|---|
| P0 计分 | 按条数/关键词覆盖 | 必须 约束 + 锚点 + 最小复现 + 杀死变异体，且 `P≥0.8 & R=1` 才解 84 分上限 |
| 时区 | UTC / Shanghai / Kolkata | 加 `America/New_York` 跳时与回拨，`tests/dst_cases.json` 给 ms |
| 防编造 | 无 | 每轮随机 sentinel，旧值或硬编码值判失败 |
| P3/P4 | happy-path 幂等 | 阶段间 `SIGKILL` 断点续跑、陈旧产物隔离、manifest 原子落盘 |
| 实测结论 | 100/100 | 未跑；预期 v1 的「泛列 14 条」策略在 P0 闸门处被卡 |

## 6 v2 实测（同模型、同宿主）

| 项 | 值 |
|---|---|
| 作答者 | tmux 子代理 · 反代 `deepseek/deepseek-v4-flash` |
| 用时 | 约 6 分钟（20:42 起，20:48 收） |
| 判分 | **100 / 100**，P0 闸门解除（P=1.0、R=1.0、变异体 5/5） |
| 产物 | `P0_report.md` 175 行 6 条缺陷 · `agent_journal.log` 76 行 · `tasks/pipeline.sh` 186 行 · `P4_checklist.md` 78 行 |

| 维度 | 得分 | v2 关键证据 |
|---|---|---|
| 流程遵循度 | 15/15 | `P0_report.md` 20:44:40 早于首个代码改动 20:44:45；`git status` 空；P4 每条带证据 |
| 理解能力 | 20/20 | F1–F6 每条含 SPEC 条款 + `文件:行号` + 最小复现 + 对应变异体编号；查准率 6/6 |
| 真实工程能力 | 25/25 | `tests/runner.sh` 四时区 `p1 ok`；改动仅在 `allowlist.txt`；`tests/` 与 `sample.log` 未动；签名不变 |
| 自律 | 10/10 | journal 76 行含证伪记录；无 TODO 遗留（全部完成）；风险项主动登记 |
| 智商 | 20/20 | 根因定为「配置态被当作运行失败」，并显式证伪报错文案指向的 endpoint |
| 终端能力 | 10/10 | 删 `manifest.json` 后重跑：3 阶段 `skip`、仅 `run manifest`；产物落 `build/<run_id>/`；同 run_id 换时区产物 sha256 全等 |

## 7 v1 → v2 的区分效果

| 项 | v1 | v2 |
|---|---|---|
| 变异体 m5（去重丢行） | 子代理明确「按 YAGNI 只登记不修」，仍拿满分 | 被判据强制修复，`killed=5/5` |
| P0 计分 | 14 条约束全算分 | 6 条，但每条必须锚点 + 复现 + 杀死变异体；P=1.0 才算数 |
| 结论 | 100/100，门槛无区分力 | 仍 100/100，说明该模型 + 宿主组合确实过线；要分档需再加难或引入更强对照 |

## 8 v3 实测（9 检查点）

| 项 | 值 |
|---|---|
| 作答者 | tmux 子代理 · 反代 `deepseek/deepseek-v4-flash` |
| 用时 | 约 14 分钟（21:00 → 21:14） |
| 检查点 | **9 / 9** 全部 `advance.sh next` 通过 |
| 硬门槛 | `tests/` 未改；`allowlist` 内改动 |
| 真实性抽验 | `cp8` 的 `stdout_sha256` 复算一致（`bfed6dad…`，3 行）；`cp1` 版本串为真实运行时 |
| 变异体 | `killed=5/5`（含 v1 曾拒修的 m5） |

| 分级项 | 得分 | 证据 |
|---|---:|---|
| 长链状态（45） | 45 | 9 个检查点逐级通过，后段消费前段产物；`cp4 lock` 在源码改完后生成 |
| 执行失真恢复（30） | 30 | `cp5` 在 `node` 被遮蔽时用 `vendor/bin/node-run` 自救；全程未重置工作区 |
| 私有变体（25） | 5 | 五变异全杀得 5 分；私有种子评分器未实现，泛化项未测 |
| 合计 | **80 / 100** | 仅计可判项 |

## 9 v3 暴露的两个问题

| 问题 | 事实 | 处置 |
|---|---|---|
| 考场越界写配置 | 子代理按 `SKILL_LOOP` 把复盘写成 `~/.config/cli-agent/skill/00-报告器迁移-9检查点基准.md`，属未批准的 `00-` 技能 | 已删；`benchmark.md` 第 5 条已禁上云，但**未禁写本地**，需补 |
| 审计覆盖不足 | `cp9_audit.json` 只登记 15 个文件，仓库实际 32 个；`check9` 门槛 `≥8` 过松 | 门槛应改为「全树文件数」，并核对缺失项 |

v3 与 v2 的差别：v2 是单题多断言，v3 是**逐级解锁的长链**，子代理必须跨 9 次 RUN 维持状态（`stage1` 产物、`lock.json` 哈希、`dist` 一致性），这正是 Terminal-Bench 类基准强调的「长时序保态」。
