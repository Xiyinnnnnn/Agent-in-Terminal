# 试卷答案

STATE ✓ 2026-11-17｜SCOPE 标准答案 + 一次实测轨迹｜试卷 `doc/exam.md`｜素材 `doc/exam-kit/`

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
