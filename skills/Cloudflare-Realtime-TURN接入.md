# Cloudflare-Realtime-TURN接入

STATE ✓ 2026-11-09｜SCOPE 给自托管 WebRTC 应用接 CF 免费 TURN（不含 SFU）｜SCRIPT cloudflare-turn-refresh.sh
REF ../memory/Cloudflare-Realtime-TURN与PairDrop接入.md

## 何时用
- 要 TURN 但不想自建 coturn、不想用 OpenRelay
- PairDrop / 自研 WebRTC 应用换中继，出现「同网能传、跨网传不动」

## 命令
```bash
# 1 建 TURN key（一次性，结果记下 uid 与 secret）
curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/$ACC/calls/turn_keys" \
  -H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json" -d '{"name":"app-turn"}'

# 2 换凭据（看返回的 iceServers）
curl -s -X POST "https://rtc.live.cloudflare.com/v1/turn/keys/$KID/credentials/generate-ice-servers" \
  -H "Authorization: Bearer $KEY_SECRET" -H "Content-Type: application/json" -d '{"ttl":172800}'

# 3 落静态文件并按需重启（PairDrop 静态模式；无 RESTART_CMD 则只写文件）
CF_TURN_KEY_ID=$KID CF_TURN_KEY_API_TOKEN=$KEY_SECRET OUT=/opt/pairdrop/rtc_config.json \
  RESTART_CMD="docker restart pairdrop" ~/.config/term_agent/skill/cloudflare-turn-refresh.sh

# 4 探活（无需凭据，只看服务端是否应答 TURN）
bash -c 'exec 3<>/dev/tcp/turn.cloudflare.com/3478; printf "\x00\x03\x00\x00\x21\x12\xa4\x42\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa\xbb\xcc" >&3; timeout 8 dd bs=1 count=80 <&3 | od -An -tx1'
```

## 参数 / 退出码
| 参数 | 默认 | 说明 |
|---|---|---|
| `TURN_TTL` | 172800 | 秒；上限即 48h，越界 400 |
| `OUT` | ./rtc_config.json | 目标文件，原子替换 |
| `RESTART_CMD` | 空 | 刷新后执行的命令，如 `docker restart pairdrop` |

脚本 exit 1 = 响应异常/无 TURN 条目，**旧文件不动**；exit 2 = 缺环境变量（`set -u`）。

## 失败处置
| 现象 | 处置 |
|---|---|
| `400 invalid argument` | TTL 越界，降到 172800 |
| `401` / `403` | secret 错或 key 已删，重建 key |
| 返回只有 stun 条目 | 视为失败，脚本拒写 |
| 客户端仍不中继 | 查 `chrome://webrtc-internals` 有无 relay candidate；再查 `ws-config` 帧里 iceServers |

## 陷阱
- secret 只在服务端，禁止下发浏览器或 commit；已被看到就重建 key。
- 出向 1000 GB/月免费，大文件传输要估。
- 大陆无 CF 中国网络，中继绕境外。
- PairDrop 静态模式只启动读一次 → 必须 `RESTART_CMD`，否则改了文件也不生效。
