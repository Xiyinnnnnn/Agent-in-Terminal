#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
out="$(vendor/bin/node-run stage1/report/index.js 2>/dev/null)" || exit 1
[ -n "$out" ] || exit 1
! printf '%s\n' "$out" | grep -qEv '^([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} |ts level msg$)'
