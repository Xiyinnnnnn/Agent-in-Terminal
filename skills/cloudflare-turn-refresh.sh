#!/usr/bin/env bash
# 静态文件模式的凭据刷新器（不改源码：docker 挂载 rtc_config.json 的做法）
# 逻辑：向 Cloudflare 换新凭据 → 原子写 rtc_config.json → 重启 PairDrop 进程（PairDrop 只在启动时读一次该文件）
#
# 用法：
#   CF_TURN_KEY_ID=xxx CF_TURN_KEY_API_TOKEN=yyy ./turn-refresh.sh
#   RESTART_CMD="docker restart pairdrop" CF_TURN_KEY_ID=... ./turn-refresh.sh
# cron（每 12 小时）：
#   0 */12 * * * CF_TURN_KEY_ID=xxx CF_TURN_KEY_API_TOKEN=yyy RESTART_CMD="docker restart pairdrop" /path/turn-refresh.sh >> /var/log/pairdrop-turn.log 2>&1
set -euo pipefail

: "${CF_TURN_KEY_ID:?需要 CF_TURN_KEY_ID}"
: "${CF_TURN_KEY_API_TOKEN:?需要 CF_TURN_KEY_API_TOKEN}"
TURN_TTL="${TURN_TTL:-172800}"     # CF 实测上限 48h，别给 0 或超过 172800
OUT="${OUT:-./rtc_config.json}"
RESTART_CMD="${RESTART_CMD:-}"

raw="$(curl -fsS -m 30 -X POST \
  "https://rtc.live.cloudflare.com/v1/turn/keys/${CF_TURN_KEY_ID}/credentials/generate-ice-servers" \
  -H "Authorization: Bearer ${CF_TURN_KEY_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"ttl\":${TURN_TTL}}")"

servers="$(printf '%s' "$raw" | sed -e 's/^{"iceServers": *//' -e 's/} *$//')"
case "$servers" in
  \[*turn*) ;;
  *) echo "[turn-refresh] 响应异常或没有 TURN 条目，放弃写入：$raw" >&2; exit 1 ;;
esac

tmp="${OUT}.tmp.$$"
printf '{\n  "sdpSemantics": "unified-plan",\n  "iceServers": %s\n}\n' "$servers" > "$tmp"
mv "$tmp" "$OUT"
echo "[turn-refresh] $(date -u +%FT%TZ) 已更新 $OUT (ttl=${TURN_TTL}s)"

if [ -n "$RESTART_CMD" ]; then
  sh -c "$RESTART_CMD" && echo "[turn-refresh] 已执行重启：$RESTART_CMD"
fi
