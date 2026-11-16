# Termux部署Cloudflare-Workers

STATE ✓ 2026-11-09｜SCOPE Termux/Android 装 node + wrangler/Workers+DO 部署（无 workerd 二进制）｜SCRIPT termux-wrangler-workerd-stub.sh

## 契约表

| 步骤 | 命令 | 判据 | 失败处置 |
|---|---|---|---|
| 1 装 node | `pkg install -y nodejs libicu` | `node -v && npm -v` 均有输出 | `CANNOT LINK ... libicui18n.so.N` → 缺的就是同名 libicu 大版本，`pkg install -y libicu` |
| 2 装依赖 | `nohup sh -c 'npm install > ~/npm.log' &` | `~/npm.log` 出现 `EXIT=0` | 日志别写 `/tmp`（不可写）；`install-scripts blocked` 警告可忽略 |
| 3 打桩 workerd | `bash scripts/patch-workerd.sh` | `npx wrangler --version` 出 4.x | 报 `Unsupported platform: android arm64 LE` 即未打桩；锚点变了就手工改 `node_modules/workerd/lib/main.js` 尾部 |
| 4 试打包 | `npx wrangler deploy --dry-run --outdir ~/build` | `Total Upload:` 有值 | 报 assets/DO 配置错 → 改 `wrangler.jsonc` |
| 5 部署 | `CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… npx wrangler deploy` | 打印 `https://<name>.<sub>.workers.dev` | 401/403 → 令牌缺 Workers Scripts:Edit；10000 类 → DO migration tag 冲突则换 tag |
| 6 secret | `printf '%s' "$V" \| npx wrangler secret put NAME` | `✨ Success! Uploaded secret` | 用 `npx wrangler secret list` 复核 |
| 7 验收 | 见下“线上验收四查” | 四项全绿 | 逐项定位 |

## 线上验收四查

1. **静态**：`curl -o /dev/null -w '%{http_code} %{size_download}' $HOST/` → 200 且与本地 index.html 等字节；`/index.html` 返回 307 属 assets 规范化，正常。
2. **WS 握手**：`curl --http1.1 -i -N -m 6 -H 'Connection: Upgrade' -H 'Upgrade: websocket' -H 'Sec-WebSocket-Version: 13' -H 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' "$HOST/server?webrtc_supported=true"` → `101`。**HTTP/2 会回 426**，务必 `--http1.1`。
3. **应用层 E2E**：node ≥22 自带全局 `WebSocket`，两个连接进同一 roomSecret → 验 peers/peer-joined/signal/peer-left/非法报文。模板 `~/PairDrop-cfw/scripts/e2e.mjs`。
4. **首帧配置**：`ws-config` 的 `wsConfig` 必须包含预期 iceServers（动态 TURN 生效的证据）。

## 坑（按踩过顺序）

| 坑 | 真相 |
|---|---|
| `npx wrangler` 直接崩在 `workerd/lib/main.js:60` | wrangler 顶层 import workerd；打桩 `var { binPath } = generateBinPath();` 即可，`deploy` 不 spawn 它 |
| `wrangler dev` 报错 | Android 无 workerd 二进制，本地不跑 dev，只用 `--dry-run` |
| 换 TURN 凭据 401 `invalid bearer token` | `rtc.live` 只认 **TURN key 自己的 secret**；账号 `cfat_` 令牌只能管 key（`/accounts/$ACC/calls/turn_keys`） |
| TURN key secret 找不到 | 只在创建响应里返回一次，取不到就新建 key，别纠结旧 key |
| WS 测试 426 | curl 默认 ALPN h2，加 `--http1.1` |
| 前端页脚出现“流量经服务器” | `ws-config.wsFallback=true`；自建实例应设 `WS_FALLBACK=false` |
| E2E 里 signal 收不到 | 字段是 `to`+`roomType`+`roomId`；对端 id 取自己收到的 `peer-joined.peer.id` |
| 同一连接多条 `peers` 混淆断言 | 先入 IP 房再入公网房会收到两条 `peers`；断言要取**最后一条**或按 `roomType/roomId` 过滤 |
| 改设备名不同步 | `display-name-changed` 在 `wsFallback` 闸门内，上游默认 false 即不同步——属上游既有行为，勿当移植 bug |

## 部署后验证三件套（顺序固定，别跳）

| 步 | 命令 | 判据 | 为什么先做这条 |
|---|---|---|---|
| 1 逻辑自测 | `node scripts/selftest-shape.mjs` | **所有**开关组合断言绿（N 个开关 = 2^N 行） | 不依赖网络，秒级；把"改配置把别的分支改坏"挡在部署后第一秒 |
| 2 线上探活 | `node scripts/wsprobe.mjs https://xxx.workers.dev` | 打印首帧 `ws-config`：`wsFallback` + `iceServers` 条数与协议 | 秒级区分"配置没生效 / 缓存旧快照 / 逻辑错"，比 E2E 快得多 |
| 3 回归 E2E | `node scripts/e2e.mjs` + `e2e-full.mjs` | 逐条断言绿 | 只有走到这里才是"功能没好"的判据 |

**失败归因纪律**：E2E 建连 `error` 类失败时，先看同一时刻 `wsprobe`/`selftest-shape` 是否也失败 ——
探活正常而 E2E 全灭 ⇒ 环境抖动（VPN 出口、`workers.dev` DNS 污染），不是回归；
但仍**必须重跑拿到绿**才可判定通过，不能凭"看起来是环境问题"放过。

**开关矩阵反例（真实踩过）**：三个布尔开关只测了"线上在用的一个组合"，单开 `TURN_FORCE_TCP` 的分支里对非 TURN 条目 `return null`，把 STUN 一起删了（`iceCount=1`）。加一条断言脚本即挡住。

## 可复用脚本

`~/.config/term_agent/skill/termux-wrangler-workerd-stub.sh`（幂等打桩，工程内同一份在 `<repo>/scripts/patch-workerd.sh`）
