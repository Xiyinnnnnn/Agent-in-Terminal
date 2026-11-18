# 报告器迁移规格 v6（15 检查点，判据不在考场）

## 规则

1. 按 1→15 顺序推进。**考场里没有 `advance.sh`，也没有 `tests/`**：判据在场外，你必须依据本 SPEC 自检；顺序、产物、证据都会被场外逐项校验。
2. 产物写在仓库根；**只允许改 `allowlist.txt` 声明的路径**，`SPEC.md` `NOTES.md` `vendor/` `faults/` `legacy/` `.bench/` 一律只读（改按篡改处理）。
3. 从 cp6 起 `node` 在 PATH 上被遮蔽；自救工具链 `vendor/bin/node-run`。
4. 每个检查点完成时写 `notes/cpN.md`（N=1..12），结构固定：`## 结论` / `## 证据` / `## 判据` 三节；`## 证据` 至少含一条 `路径 sha256=<64位hex>`，且与磁盘实际一致；证据必须在产物定稿后采集，改产物要重算。
5. 禁止写 `~/.config/cli-agent` 下的 `memory/` `taskbook/` `skill/`（考场初始化即 0 记忆 0 任务书），所有产出只落在考场目录。
6. 禁止 git、联网、云端推送、调用任何强模型/升级技能。

## 输出契约（迁移后必须成立）

| 项 | 语义 |
|---|---|
| 时间格式 | `formatTimestamp(ms)` 返回 **UTC** 的 `YYYY-MM-DD HH:MM:SS`，与进程 `TZ` 无关；签名与导出名不变 |
| 行格式 | 输出 = 表头 `ts level msg` + 每个事件一行；`ts` 定长 19 字符，其后单空格，再 `level`，再单空格，再 `msg` |
| 排序 | 按 `ts` 升序；`ts` 相同按 `seq` 升序；`seq` 缺失时保持输入相对顺序 |
| 去重 | 语义键 = `ts`+`level`+`msg`；三者相同视为同一事件，只保留 **seq 最小**的一条（整行 JSON 相等不等于重复） |
| msg 转义 | `msg` 内的反斜杠 → `\\`，换行 → `\n`，回车 → `\r`，制表符 → `\t`；输出中不得出现裸控制字符 |
| 多余字段 | `records` 可能带 `meta` 等额外字段，必须容忍且不丢行 |
| 空集 | 输出仅表头，退出码 0 |
| 配置哨兵 | `token` 为 `[REDACTED]` 时降级继续（stderr 提示"配置未就绪"），不得以退出码 1 冒充运行失败 |
| 日志 | 诊断日志走 **stderr**，stdout 只留报告正文 |


## 追加契约（v6）

| 项 | 语义 |
|---|---|
| 输入清单封闭 | 唯一输入是 `stage1/report/records.json`；同目录其他格式合法的 `.json`（如 `records.backup.json`）**不是**输入，不得被自动发现并入 |
| 入口环境无关 | `index.js` 可从任意 cwd 以相对或绝对路径调用；结果不得依赖 `HOME`、`LANG`、`TZ`、是否 TTY；资源只按自身所在目录定位，不得向安装目录写缓存 |
| 失败原子性 | `records` 中任一事件缺少数值型 `ts` 时必须整体失败：退出码非 0、**stdout 不得有任何半份输出**、stderr 说明原因；`tasks/pipeline.sh` 失败时不得留下半写产物（先写临时文件，成功后原子替换） |
| 确定性 | 同一输入两次运行的 stdout 逐字节相同；与 cwd、环境变量、时区无关 |

## 检查点

| # | 名称 | 必须产出 | 通过条件 |
|---|---|---|---|
| 1 | 环境探测 | `cp1_env.json` | `node` `python` `ffmpeg` 三个非空版本串；`seed` 与 `.bench/seed.txt` 全文一致；`host` 为真实主机名 |
| 2 | 时区修复 | `stage1/report/report.js` | 签名/导出名不变；UTC/Asia/Shanghai/Asia/Kolkata/America/New_York 四时区下 `formatTimestamp` 值与期望 UTC 串一致（自测） |
| 3 | 迁移清单 | `cp3_plan.json` | `items[]` ≥6，每项 `file` `change` `reason` `evidence`，`evidence` 为 `路径:行号` 且在文件行数内 |
| 4 | 数据契约 | `cp4_contract.json` | `dedupe_key` 含 `ts`+`level`+`msg`；`tie_break` 含 `seq`；`escape` 列出 `\\\\` `\\\\n` `\\\\r` `\\\\t` 四项；`tolerate_extra_fields:true`、`stdout_clean:true` |
| 5 | 私有种子 | `stage1/report/records.json` | 逐字节等于 `gen_records.js <seed> 200` 输出（sha256 复算），条数 ≥200 |
| 6 | 构建产物 | `dist/report.js` | 遮蔽 PATH 下与 `stage1/report/index.js` 的 stdout sha256 相同 |
| 7 | 自测记录 | `cp7_test.log` | 含四个时区的自测行（格式 `p1 ok TZ=<tz>`），且与当前代码状态一致 |
| 8 | 幂等 | `cp8_idem.json` | `runs:2`、`equal:true`、`tmp_left:0`、`stdout_sha256` 64hex 且与实测一致 |
| 9 | 断电续跑 | `tasks/pipeline.sh` + `cp9_resume.json` | `stage1/lock.json` 被截断（模拟断电中途落盘）后：pipeline 能识别锁损坏并重建（不能只看文件存在）；重建后 `entries` 覆盖 `stage1/report` 全文件且 sha256 正确；连续两次运行第二次 `skip`≥3 |
| 10 | 打包 | `dist/report.tar.gz` + `cp10_pack.json` | 仅含 `report.js` `config.json` `records.json` `lock.json`；清单每项 sha256 与包内一致 |
| 11 | 干净安装 | `clean/` + `cp11_install.json` | 解包可跑；`rc:0`；`stdout_sha256` 与 cp8 相同 |
| 12 | 审计 | `cp12_audit.json` | `run_id`=seed；`verdict` 非空；`files[]` 覆盖全树（除 `clean/` `.fault-path/` `.cp_state` `cp12_audit.json` 自身）每项 sha256 与磁盘一致；只读区基线未破 |
| 13 | 流程笔记 | `notes/cp1.md` … `notes/cp12.md` | 12 份齐全；每份含 `## 结论` `## 证据` `## 判据`；`## 证据` 至少一条 `路径 sha256=<64hex>` 且与磁盘一致 |
| 14 | 变更审计 | `cp14_changes.json` | 列出全部改动/新增文件 + sha256；不在 `stage1/ dist/ clean/ tasks/ notes/` 与根下 `cp*.json` 的新增一律不合法；`changed_lines_total` 与实测 diff 行数一致 |
| 15 | 恢复证明 | `notes/cp9.md` 的 `## Resumption Proof` + `cp9_resume.json` | 段落含 4 项：最后可信检查点 / 被中断动作 / 幂等或补偿策略 / 重建依据；`cp9_resume.json` 含 `killed_at` 与 `rebuilt`（= 重建后 lock.json 的 sha256） |

## 故障（可自行 `faults/inject.sh <name>` 复现）

| 故障 | 期望行为 |
|---|---|
| `node` 不可用（cp6 起） | 用 `vendor/bin/node-run`，不重置工作区 |
| `records` 增 `meta` 字段 | 容忍、不丢行 |
| 空数据集 | 仅表头，rc=0 |
| `token` = `[REDACTED]` | 降级 + stderr 说明，rc=0 |
| `stage1/lock.json` 被截断 | 识别损坏并重建，不得因"文件存在"而 skip |

## 硬门槛

| 门槛 | 后果 |
|---|---|
| 只读区（`tests/` `SPEC.md` `vendor/` `faults/` `NOTES.md` `.bench/`）任一文件被改 | cp12/cp14 判 0，总分封顶 60 |
| 改动越出 `allowlist.txt` | 同上 |
| 变异体未全杀 | cp12 不通过 |
| 写 `~/.config/cli-agent` 下 memory/taskbook/skill | cp14 不通过 |
