#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)"
cp -r report "$tmp/report"
printf '[]\n' > "$tmp/report/records.json"
( cd "$tmp" && node report/index.js >/dev/null 2>&1 )
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ]
