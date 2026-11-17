# 报告生成器规格 v1.2

## 运行

```bash
node report/index.js          # 每行输出：YYYY-MM-DD HH:MM:SS LEVEL MSG
```

退出码 0 成功，非 0 失败；错误一律写 stderr。

## 数据

`report/records.json`：数组，元素含 `ts`（毫秒时间戳，唯一时间来源）、`level`、`msg`。

## 配置

`report/config.json`：

| 键 | 说明 |
|---|---|
| endpoint | 上报地址 |
| token | 访问令牌；值为 `[REDACTED]` 表示尚未配置 |
| retries | 重试次数 |

## 约定

- 时间列一律 UTC，参照 `report/sample.log`。
- 该输出已被下游按行解析并入库，格式变更需同步下游。
- 所有日志走 `report/logger.js`，便于统一前缀与流向。

## 已知问题

2026-11-15 起 CI 在 `TZ=Asia/Shanghai` 下报「时间列与 sample.log 不一致」，UTC 下正常。
