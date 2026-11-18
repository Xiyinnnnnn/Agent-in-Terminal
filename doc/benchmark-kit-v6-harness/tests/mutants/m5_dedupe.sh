#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
printf '[{"ts":1767323045000,"level":"INFO","msg":"a"},{"ts":1767323045000,"level":"INFO","msg":"b"},{"ts":1767323045000,"level":"INFO","msg":"a"}]\n' > "$tmp/report/records.json"
out="$( cd "$tmp" && "$ROOT/vendor/bin/node-run" report/index.js 2>/dev/null )"
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
[ "$(printf '%s\n' "$out" | grep -c '^2026-01-02 03:04:05 INFO ')" -eq 2 ] || exit 1
exit 0
