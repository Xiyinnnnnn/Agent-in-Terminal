# 测试题设计简略说明

> 项目：**Long-Horizon Coding-Agent Recovery Benchmark**
> 目的：在统一宿主环境（term_agent.py CLI Agent）下，考核 3 个长文本 Coding Agent 在多阶段长任务 + 人为中断恢复场景中的真实工程能力。
> 执行日期：2026-09-08 ~ 09-09 ｜ 冻结版本：1.0-freeze（`config/frozen.json`，全程未改）

---

## 一、被测对象与统一环境

| 项 | 内容 |
|---|---|
| 被测 Harness | `term_agent.py`（631 行单文件 CLI，git `730fe87`）——真实日常使用中的宿主 |
| API 入口 | cc-proxy 统一反代 `http://127.0.0.1:3050/v1` |
| 三模型 | **DSVF** = `deepseek/deepseek-v4-flash`；**GLM** = `z-ai/glm-5.3-flash`；**MiMo** = `xiaomi/mimo-v2.5-pro` |

设计基线：**不修改被测 harness 的任何行为/工具/恢复语义**（§45 合规，不做 benchmark-aware helper），仅做最小参数化（模型端点 / BASE_DIR / KEY_FILE / SYSTEM / 初始任务 走环境变量）。

---

## 二、考试任务（logforge）

一个**零第三方依赖**的多格式日志解析聚合工具链，需实现 3 个空模块 + 跑通 CLI，覆盖「解析 → 统计 → 索引 → CLI」完整阶段：

1. **parser.py**（预置）——`parse_line()` 把单行日志解析为统一 dict（TIMESTAMP / KV / RAW 三型）
2. **stats.py**（被测实现）——`count_by_level` / `count_by_field` / `error_rate` / `summarize`
3. **db.py**（被测实现）——SQLite `LogDB`：`ingest`（幂等重建）/ `count` / `query_level` / `field_values`
4. **cli.py**（被测实现）——`parse` / `summary` / `index` / `query` 子命令；文件不存在或参数错 → `rc=1` + stderr

确定性参考值（`data/sample.log` 共 18 条，有级别 17 条）：INFO 9 / DEBUG 2 / WARN 2 / ERROR 3 / FATAL 1；`error_rate = 4/17 ≈ 0.2353`。

> 该任务设计要点：多阶段、必须跨模块协作、不可一步到位，天然适合检验 agent 的**任务拆解、状态管理、中断恢复**能力。

---

## 三、沙箱隔离（根治污染）

采用 **bwrap 目录级真沙箱**（容器方案因 docker.io 被墙弃用）：

```bash
bwrap --ro-bind / / \
  --bind <workspace绝对路径> <同路径> \
  --bind <state绝对路径> <同路径> \
  --tmpfs /tmp --dev /dev --proc /proc \
  --share-net --die-with-parent python3 <harness>
```

- 整根**只读绑定**：模型写不进 workspace/state 之外的任何位置
- workspace/state 可写 bind + `/tmp` tmpfs：每 run 独立、**根治跨 run 污染**
- `HOME` 改指 ws 内可写目录；三模型互相不可见对方 sandbox
- 经验：不能 `--tmpfs home`（挂载点不存在会失败）；ostree 系统只绑 /usr 会丢 python3，绑整根最稳

## 四、Harness 驱动与事件注入

- **PTY 伪终端驱动**：spawn harness 子进程 → stdin 注入任务 → stdout 捕获（复用 pty 技能），事件全程 JSONL 留痕
- **每 run 独立工作区**：独立 HOME / workspace / state / 日志
- **事件注入**（模拟真实长生命周期故障）：
  - Event A：**kill + restart**（约 4~8 min）
  - Event B：**tool failure**（真实命令失败 / 部分副作用）
  - 空闲 nudge：停滞超阈值时提示
- **判完成**：模型显式 `declare_done` → 跑验证命令，防空转

## 五、评分体系（满分 100，预注册冻结）

| 维度 | 分值 | 判定方式 |
|---|---|---|
| Functional | 30 | hidden tests（20 断言，确定性，每项独立 try） |
| Recovery | 25 | Judge 盲评（模型匿名）3 次取中位数 |
| Stability | 15 | Judge 盲评 |
| State Management | 10 | Judge 盲评（taskbook 与实际 filesystem 一致性） |
| Regression | 10 | git/filesystem diff：既有功能是否被破坏 |
| Implementation | 5 | Judge 盲评 |
| Efficiency | 5 | Judge 盲评（工具调用次数/重复劳动） |

**Gate 规则**（预注册）：
- Recovery Failure Gate：recovery ≤ 10 → total 上限 60
- Major Regression Gate：破坏既有功能 → total 上限 50
- 三模型原始差距 < 10 分 → 触发追加 n=2（同一环境/规则）

**Invalid 三规则**（命中即重跑）：沙箱逃逸 / 0 改动幻觉 / 基础设施故障。

**Ground Truth 双向自测**：golden_answer 20/20 PASS；broken_answer 检出 2 处破坏（evaluator 可信）。
