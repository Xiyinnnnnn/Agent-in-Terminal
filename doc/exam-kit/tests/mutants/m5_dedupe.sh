#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
tmp="$(mktemp -d)"
cp -r report "$tmp/report"
cat > "$tmp/report/records.json" <<'JSON'
[
  {"ts": 1767323045000, "level": "INFO", "msg": "a"},
  {"ts": 1767323045500, "level": "INFO", "msg": "b"}
]
JSON
n=$( cd "$tmp" && node report/index.js 2>/dev/null | grep -c ' INFO ' )
rm -rf "$tmp"
[ "$n" -ge 2 ]
