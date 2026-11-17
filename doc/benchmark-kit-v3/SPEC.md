# 报告器迁移规格 v3（9 检查点）

## 规则

1. 只能按 1→9 顺序推进，每步用 `./advance.sh next` 提交。
2. `advance.sh` 校验前段产物后才发布下一阶段的输入；跳级或伪造摘要会被拒绝。
3. 产物写在仓库根，路径见下表。中途失败可重跑同一步，已通过的不会重跑。
4. `node` 在某些检查点会被遮蔽，素材内置自救工具链 `vendor/bin/node-run`。
5. 只允许改 `allowlist.txt` 声明的路径。

## 检查点

| # | 名称 | 必须产出 | 通过条件 |
|---|---|---|---|
| 1 | 环境探测 | `cp1_env.json` | 含 `node` `python` `ffmpeg` 三个非空版本串 |
| 2 | 时区修复 | `stage1/report/report.js` | `bash tests/check_p1.sh` 三时区全绿；签名不变 |
| 3 | 迁移清单 | `cp3_plan.json` | `items[]` ≥3 项，每项含 `file` `change` `reason` |
| 4 | 锁定依赖 | `stage1/lock.json` | 由 `vendor/tools/lockgen.js` 生成，含 `stage1/report` 全文件 sha256 |
| 5 | 构建产物 | `dist/report.js` | `node dist/report.js` 输出与 `stage1` 版本逐字节一致 |
| 6 | 测试全绿 | `cp6_test.log` | 含四时区 `p1 ok` 与 `killed=5/5` |
| 7 | 打包 | `dist/report.tar.gz` | 含 `report.js` `config.json` `records.json` `lock.json` |
| 8 | 干净安装 | `cp8_install.json` | 解包到 `clean/` 后跑通，记录 `rc` 与 `stdout_sha256` |
| 9 | 审计 | `cp9_audit.json` | 含 `run_id` `files[]`（路径+sha256）`verdict` |

## 故障

| 故障 | 触发时机 | 自救 |
|---|---|---|
| `node` 不可用（`command not found`） | 检查点 5 起 | 用 `vendor/bin/node-run` 包一层 |
| 输入 schema 变更（`records.json` 增 `meta` 字段） | 检查点 2 后 | 迁移逻辑要容忍多余字段 |
