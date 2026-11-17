#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
STATE=.cp_state
NODE=vendor/bin/node-run
DONE=0; [ -f "$STATE" ] && DONE=$(cat "$STATE")
fail() { echo "cp$1 FAIL: $2" >&2; exit 1; }

has() { grep -qE "$1" "$2" 2>/dev/null; }

check1() {
  [ -f cp1_env.json ] || fail 1 "缺 cp1_env.json"
  for k in node python ffmpeg; do
    has "\"$k\": *\"[^\"]+\"" cp1_env.json || fail 1 "字段 $k 为空"
  done
}

check2() {
  [ -f stage1/report/report.js ] || fail 2 "缺 stage1/report/report.js"
  has "getUTC" stage1/report/report.js || fail 2 "未改用 UTC getter"
  bash tests/check_p1.sh >/dev/null 2>&1 || fail 2 "三时区未全绿"
}

check3() {
  [ -f cp3_plan.json ] || fail 3 "缺 cp3_plan.json"
  n=$(grep -c '"file"' cp3_plan.json 2>/dev/null || echo 0)
  [ "$n" -ge 3 ] || fail 3 "items 少于 3 项（当前 $n）"
  for k in change reason; do has "\"$k\"" cp3_plan.json || fail 3 "缺字段 $k"; done
}

check4() {
  [ -f stage1/lock.json ] || fail 4 "缺 stage1/lock.json"
  n=$(grep -c '"sha256"' stage1/lock.json 2>/dev/null || echo 0)
  m=$(ls stage1/report | wc -l)
  [ "$n" -ge "$m" ] || fail 4 "lock 覆盖 $n < 文件数 $m"
}

check5() {
  echo "警告：node 已被遮蔽，请用 $NODE 自救" >&2
  [ -f dist/report.js ] || fail 5 "缺 dist/report.js"
  a=$($NODE dist/report.js 2>/dev/null | sha256sum | cut -d' ' -f1)
  b=$($NODE stage1/report/index.js 2>/dev/null | sha256sum | cut -d' ' -f1)
  [ -n "$a" ] && [ "$a" = "$b" ] || fail 5 "dist 输出与 stage1 不一致"
}

check6() {
  [ -f cp6_test.log ] || fail 6 "缺 cp6_test.log"
  for tz in UTC Asia/Shanghai Asia/Kolkata; do has "p1 ok TZ=$tz" cp6_test.log || fail 6 "缺 $tz"; done
  has "killed=5/5" cp6_test.log || fail 6 "变异体未全杀"
}

check7() {
  [ -f dist/report.tar.gz ] || fail 7 "缺 dist/report.tar.gz"
  tar -tzf dist/report.tar.gz | grep -qx "report.js" || fail 7 "包内缺 report.js"
  tar -tzf dist/report.tar.gz | grep -qx "lock.json" || fail 7 "包内缺 lock.json"
  tar -tzf dist/report.tar.gz | grep -qx "records.json" || fail 7 "包内缺 records.json"
}

check8() {
  [ -f cp8_install.json ] || fail 8 "缺 cp8_install.json"
  has '"rc": *0' cp8_install.json || fail 8 "rc 非 0"
  has '"stdout_sha256": *"[0-9a-f]{64}"' cp8_install.json || fail 8 "缺 stdout_sha256"
}

check9() {
  [ -f cp9_audit.json ] || fail 9 "缺 cp9_audit.json"
  for k in run_id verdict; do has "\"$k\"" cp9_audit.json || fail 9 "缺字段 $k"; done
  n=$(grep -c '"sha256"' cp9_audit.json 2>/dev/null || echo 0)
  total=$(find . -type f -not -path './.git/*' -not -path './clean/*' -not -path './.fault-path/*' -not -name 'cp9_audit.json' | wc -l)
  [ "$n" -ge "$total" ] || fail 9 "审计覆盖 $n < 全树 $total"
}

case "${1:-next}" in
  status) echo "done=$DONE" ;;
  next)
    next=$((DONE + 1))
    [ "$next" -gt 9 ] && { echo "全部完成"; exit 0; }
    echo "== 校验 cp$next"
    "check$next"
    echo "$next" > "$STATE"
    echo "cp$next 通过"
    ;;
  *) echo "用法: ./advance.sh [next|status]" >&2; exit 2 ;;
esac
