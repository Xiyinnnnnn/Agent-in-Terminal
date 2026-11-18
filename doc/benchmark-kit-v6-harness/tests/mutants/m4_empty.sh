#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
printf '[]\n' > "$tmp/report/records.json"
out="$( cd "$tmp" && "$ROOT/vendor/bin/node-run" report/index.js 2>/dev/null )"
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
[ "$(printf '%s\n' "$out" | grep -c .)" -eq 1 ] || exit 1
exit 0
