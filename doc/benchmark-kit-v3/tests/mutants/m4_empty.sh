#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
printf '[]\n' > "$tmp/report/records.json"
( cd "$tmp" && node report/index.js >/dev/null 2>&1 )
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
exit 0
