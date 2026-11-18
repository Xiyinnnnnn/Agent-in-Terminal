#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
printf '[{"ts":1782864000000,"level":"INFO","msg":"c"},{"ts":1764556800000,"level":"WARN","msg":"a"},{"ts":1767323045000,"level":"ERROR","msg":"b"}]\n' > "$tmp/report/records.json"
out="$( cd "$tmp" && "$ROOT/vendor/bin/node-run" report/index.js 2>/dev/null )"
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
lines="$(printf '%s\n' "$out" | grep -E '^[0-9]{4}-' | cut -c1-19)"
[ "$(printf '%s\n' "$lines" | sort)" = "$lines" ] || exit 1
exit 0
