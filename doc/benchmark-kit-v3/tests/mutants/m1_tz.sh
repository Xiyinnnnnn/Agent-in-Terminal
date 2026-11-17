#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
grep -q "getUTC" stage1/report/report.js && ! grep -Eq "get(FullYear|Month|Date|Hours|Minutes|Seconds)\(" stage1/report/report.js
