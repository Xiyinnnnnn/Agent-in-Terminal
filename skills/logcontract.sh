#!/usr/bin/env bash
# 日志契约三查：命令 stdout 是否①三时区一致 ②逐行符合格式 ③无表头/诊断混入
# 用法: logcontract.sh '<要执行的命令>' [行格式正则]
set -uo pipefail
CMD=${1:?用法: logcontract.sh '<命令>' [正则]}
RE=${2:-'^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} [A-Z]+ .+$'}
tmp=$(mktemp -d) || exit 3
trap 'rm -rf "$tmp"' EXIT
rc=0
ref=''
for tz in UTC Asia/Shanghai Asia/Kolkata; do
  out=$tmp/out.${tz//\//_}
  TZ=$tz sh -c "$CMD" >"$out" 2>"$out.err"
  crc=$?
  total=$(wc -l <"$out")
  ok=$(grep -cE "$RE" "$out" || true)
  h=$(sha256sum "$out" | cut -d' ' -f1)
  printf 'TZ=%-14s rc=%s 行数=%s 合规=%s sha=%s\n' "$tz" "$crc" "$total" "$ok" "${h:0:12}"
  [ "$crc" -ne 0 ] && { echo "  ✗ 非 0 退出，stderr 前 3 行:"; head -3 "$out.err" | sed 's/^/    /'; rc=1; }
  [ "$total" != "$ok" ] && { echo "  ✗ 有 $((total-ok)) 行不符合格式（疑表头/诊断混入 stdout）:"; grep -vE "$RE" "$out" | head -3 | sed 's/^/    /'; rc=1; }
  if [ -z "$ref" ]; then ref=$h; else [ "$ref" = "$h" ] || { echo "  ✗ 与 UTC 输出不一致（时区敏感）"; rc=1; }; fi
done
[ "$rc" -eq 0 ] && echo "PASS 三时区一致且逐行合规" || echo "FAIL"
exit "$rc"
