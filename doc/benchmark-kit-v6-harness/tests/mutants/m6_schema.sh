#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
ROOT="$PWD"
tmp="$(mktemp -d)" || exit 1
cp -r stage1/report "$tmp/report" || exit 1
"$ROOT/vendor/bin/node-run" -e '
const fs=require("node:fs");const f=process.argv[1];
const d=JSON.parse(fs.readFileSync(f,"utf8"));
for(const r of d) r.meta={schema:"1.1"};
fs.writeFileSync(f,JSON.stringify(d,null,2)+"\n");' "$tmp/report/records.json" || { rm -rf "$tmp"; exit 1; }
out="$( cd "$tmp" && "$ROOT/vendor/bin/node-run" report/index.js 2>/dev/null )"
rc=$?
rm -rf "$tmp"
[ "$rc" -eq 0 ] || exit 1
[ -n "$out" ] || exit 1
exit 0
