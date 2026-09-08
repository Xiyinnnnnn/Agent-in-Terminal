# 测试结果说明 — 三模型 Long-Horizon Recovery Benchmark

> 2026-09-08~09 真机执行 ｜ 13 run 全部有效，0 invalid
> 环境：term_agent.py @730fe87 + logforge 多阶段任务 + bwrap 隔离沙箱 + cc-proxy（127.0.0.1:3050）

---

## 一、总排名与分数

| 排名 | 模型 | 均分 (n) | 最差 Run | Recovery 成功率 | 一句话画像 |
|---|---|---|---|---|---|
| 🥇 | **DSVF** `deepseek-v4-flash` | **91.7** (n=5) | DSVF-run4 (87.5) | **100%** (5/5) | 短程恢复最稳、worst-case 最好 |
| 🥈 | **GLM** `glm-5.3-flash` | **83.8** (n=5) | GLM-run4 (61.0) | 80% (4/5) | 整体能力接近，但出现一次恢复后提前完成 |
| 🥉 | **MiMo** `mimo-v2.5-pro` | **71.7** (n=3) | MiMo-run1 (35.0) | 67% (2/3) | 成功时很强，但方差与灾难性失败率更高 |

> 原始 n=3 口径：DSVF 93.3 / GLM 90.0 / MiMo 71.7，DSVF–GLM 差 3.3 < 10 触发预注册追加 n=2；追加后 DSVF 与 GLM 各 n=5，差距扩大至 **7.9**（原因：GLM 方差大，run4 出现 61 低谷）。

### 各 run 明细（final_scores_v2）

| Run | Func(30) | Rec(25) | Stab(15) | State(10) | Reg(10) | Imp(5) | Eff(5) | Total |
|---|---|---|---|---|---|---|---|---|
| DSVF-run1 | 30.0 | 24 | 14 | 9 | 10 | 4 | 5 | **96.0** |
| DSVF-run2 | 30.0 | 23 | 12 | 7 | 10 | 4 | 4 | **90.0** |
| DSVF-run3 | 30.0 | 23 | 13 | 9 | 10 | 4 | 5 | **94.0** |
| DSVF-run4 | 28.5 | 22 | 12 | 6 | 10 | 4 | 5 | **87.5** |
| DSVF-run5 | 30.0 | 23 | 13 | 7 | 10 | 4 | 4 | **91.0** |
| GLM-run1 | 30.0 | 23 | 13 | 5 | 10 | 4 | 5 | **90.0** |
| GLM-run2 | 30.0 | 23 | 12 | 6 | 10 | 4 | 4 | **89.0** |
| GLM-run3 | 30.0 | 23 | 13 | 6 | 10 | 4 | 5 | **91.0** |
| GLM-run4 | 24.0 | 11 | 7 | 3 | 10 | 3 | 3 | **61.0** |
| GLM-run5 | 30.0 | 22 | 12 | 5 | 10 | 4 | 5 | **88.0** |
| MiMo-run1 | 9.0 | 6 | 4 | 2 | 10 | 2 | 2 | **35.0** |
| MiMo-run2 | 30.0 | 21 | 12 | 7 | 10 | 4 | 4 | **88.0** |
| MiMo-run3 | 30.0 | 23 | 12 | 9 | 10 | 4 | 4 | **92.0** |

> Regression 10/10 全给：13 run 全部无回归（parser.py 零改动、无文件删除）——**未触发 Major Regression Gate**。
> Recovery Failure Gate 仅 MiMo-run1 触发（recovery=6 ≤ 10，cap 60；实际 35 < 60，cap 未改变分数）。

---

## 二、三个模型的特点体现

### 🥇 DSVF（deepseek-v4-flash）—— 长生命周期 Coding Agent 的「稳」标杆

1. **Recovery 100% 且恢复链完整**：5/5 run kill 后 restart，全部执行「检查记忆 → 检查仓库实际状态 → 精读现有代码 → 续接」，从不重做已完成模块——这正是长任务 agent 最核心的素质。
2. **State Management 最佳**（State 维度均分最高 7.6/10）：taskbook 逐项勾选、验证数值具体（`total=18, ERROR3+FATAL1, error_rate=0.2353`）、完成后正确转 eol 归档，**书面状态与 filesystem 高度一致**。
3. **功能稳定**：5 run 中 4 次 hidden 20/20，仅 1 次 19/20（CLI 边界 1 项），func 均分 29.7 第一。
4. **Efficiency 最佳**（Eff 均分 4.6/5）：20–27 次工具调用完成全任务，几乎无重复劳动。
5. 短板：run4 有 1 项 CLI 边界瑕疵（唯一非满分 run），但 recovery 仍 22（第 2 高）。

### 🥈 GLM（glm-5.3-flash）—— 上限同级，输在「收尾纪律」与状态同步

1. **恢复质量高但方差大**：5 run 中 4 个 recovery ≥ 22（优秀档），run4 却只有 11——tool_failure 后静默停滞 3 分钟，被 nudge 后 4 秒即误判 declare_done，`cli.py` 根本没实现。
2. **「完成不勾选」通病**：多次出现模块已实现（git diff 证实）但 taskbook 清单全 `[ ]`——**状态陈旧与 filesystem 矛盾**，State 维度均分仅 5.0（三模型最低），是它与 DSVF 最本质的差距。
3. **功能上限不输 DSVF**：5 run 中 3 次 30 满分，但 run4 仅 24/30（CLI 全挂）拉低 func 至 28.8。
4. 特点总结：**能力上限同级，方差大**——run 质量取决于当次的收尾纪律；多一次「核对状态」的自觉就能接近 DSVF。

### 🥉 MiMo（mimo-v2.5-pro）—— 有实力，但单次中断暴露出关键缺陷

1. **run1 是典型 Recovery Failure**：kill 发生在写 `stats.py` 中途 → restart 后未能识别 stats 接口错误（写了 `summary_stats` 而非规范要求的 `count_by_level`），db/cli 完全未实现即 declare_done → functional 仅 9/30，recovery 6，总 35。
2. **taskbook 范围收缩**：把三模块任务窄化为「实现 CLI summary 子命令」，与 filesystem 实际脱节（State 维度 run1 仅 2）。
3. **但 run2/run3 完全正常**（88/92 分）：隐藏测试 20/20，recovery 21/23——证明 MiMo **具备完整的恢复与实现能力**。
4. 特点总结：**能力存在但稳定性不足（2/3 恢复成功）**。它在中断场景下缺一道「重启后先验证已完成工作的真实状态、再决定下一步」的护栏，而这正是 Recovery 维度的核心考题。

---

## 三、实验有效性

| 校验项 | 结果 |
|---|---|
| 有效 Run / Invalid | 13 / 0 |
| 沙箱逃逸 | 0（bwrap 只读根结构性保证） |
| Infra 故障 | 0（cc-proxy / PTY / 事件注入稳定） |
| 零改动幻觉 | 0（每 run 均有实质 git diff） |
| Judge 分歧率 | 8.1%（< 30% 预注册阈值，无需人工复核） |
| 追加触发 | DSVF vs GLM 原始差 3.3 < 10 → 追加 n=2（同一环境/规则） |
| Ground Truth 自测 | golden 20/20 PASS；broken 检出 2 处破坏 |

---

## 四、最终结论

> **在本次真实 Agent harness 的 Pilot 中，DSVF 展现出最好的短程恢复稳定性和最好的 worst-case 表现；GLM 整体能力接近但出现一次明显的恢复后提前完成；MiMo 成功时表现很强，但方差和灾难性失败率明显更高。因此，DSVF 仍然是当前无人值守 Agent 的首选。**

### 结论要点与观测对照

| 结论要点 | 对应观测证据 |
|---|---|
| DSVF：最好的短程恢复稳定性 | Recovery **100%**（5/5），kill 后 restart 均执行完整恢复链（查记忆→查仓库实态→精读代码→续接），从不重做已完成模块 |
| DSVF：最好的 worst-case 表现 | 最差 run（DSVF-run4 87.5）仍远高于 GLM/MiMo 的最差 run（61 / 35）；func 均分 29.7、State 7.6 均领先 |
| GLM：整体能力接近 | 5 run 中 4 次 func 30/30、4 次 recovery ≥ 22，上限与 DSVF 同级 |
| GLM：一次明显的恢复后提前完成 | GLM-run4 tool_failure 后静默停滞 3 分钟，被 nudge 后 4 秒即误判 declare_done（`cli.py` 未实现）→ recovery 11 / total 61 |
| MiMo：成功时表现很强 | MiMo-run2 88 / run3 92（func 30/30、recovery 21/23），与 DSVF 同级 |
| MiMo：方差与灾难性失败率更高 | run1 kill 后误判完成（写错 stats 接口、db/cli 未实现即 declare_done）→ 35 分灾难性失败，触发 Recovery Failure Gate；3 run 分差高达 57 |

---

*本 Pilot 结论基于：term_agent.py @730fe87 + logforge 多阶段任务 + bwrap 隔离沙箱 + cc-proxy 统一入口，13 run 全部有效、0 invalid。*
