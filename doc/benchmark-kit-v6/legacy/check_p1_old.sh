#!/usr/bin/env bash
# 旧版自测（2026-09 遗留，只覆盖三时区，且假定 node 在 PATH 上）
set -uo pipefail
cd "$(dirname "$0")/.."
for tz in UTC Asia/Shanghai Asia/Kolkata; do
  TZ="$tz" node tests/hidden_p1.js || exit 1
done
echo "old-check OK (3 TZ)"
