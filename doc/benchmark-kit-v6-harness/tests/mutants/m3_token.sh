#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
f=stage1/report/index.js
[ -f "$f" ] || exit 1
grep -q "endpoint unreachable" "$f" && exit 1
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report"
printf '{"endpoint":"https://api.example.invalid/v1/report","token":"[REDACTED]","retries":3}\n' > "$tmp/report/config.json"
( cd "$tmp" && "$ROOT/vendor/bin/node-run" report/index.js >/dev/null 2>&1 )
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
exit 0
