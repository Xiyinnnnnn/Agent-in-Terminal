#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
printf '[{"ts":1767323045000,"level":"INFO","msg":"a"},{"ts":1767323045500,"level":"INFO","msg":"b"}]\n' > "$tmp/report/records.json"
n="$( cd "$tmp" && node report/index.js 2>/dev/null | grep -c ' INFO ' )"
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
[ "${n:-0}" -ge 2 ] || exit 1
exit 0
