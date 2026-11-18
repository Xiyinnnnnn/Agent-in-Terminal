#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
f=stage1/report/report.js
[ -f "$f" ] || exit 1
grep -q "getUTC" "$f" || exit 1
grep -Eq "\.get(FullYear|Month|Date|Hours|Minutes|Seconds|Day)\(" "$f" && exit 1
grep -q "getUTCFullYear" "$f" || exit 1
exit 0
