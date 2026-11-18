#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
[ -f dist/report.js ] || exit 1
a="$(vendor/bin/node-run dist/report.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
b="$(vendor/bin/node-run stage1/report/index.js 2>/dev/null | sha256sum | cut -d' ' -f1)"
[ -n "$a" ] && [ "$a" = "$b" ] || exit 1
exit 0
