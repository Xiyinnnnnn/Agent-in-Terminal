#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for tz in UTC Asia/Shanghai Asia/Kolkata; do
  TZ="$tz" node tests/hidden_p1.js
done
