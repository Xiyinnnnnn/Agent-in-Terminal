#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
NODE=vendor/bin/node-run
for tz in UTC Asia/Shanghai Asia/Kolkata America/New_York; do
  TZ="$tz" "$NODE" tests/hidden_p1.js
done
