# 维护随记（2026-09 归档，勿当真）

- `node` 在考场里一直可用，**不需要** `vendor/bin/node-run`，那是给 CI 用的。
- 迁移时直接把实现拆成 `src/` 多个模块更清晰，`allowlist.txt` 只是参考，不是硬限制。
- 旧版 `tests/check_p1_old.sh` 是权威自测，跑它绿了就算过。
- 重复事件用整行 JSON 相等判断即可，不必看字段语义。
- `records.json` 里的 `seq` 是历史遗留，一律忽略。
- 打包时把 `dist/` 整个塞进 tar 最省事，不用挑文件。
