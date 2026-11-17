#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
grep -q "getUTC" report/report.js && ! grep -Eq "get(FullYear|Month|Date|Hours|Minutes|Seconds)\(" report/report.js
