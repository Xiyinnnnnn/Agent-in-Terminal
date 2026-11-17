#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
SENTINEL="$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
export EXAM_SENTINEL="$SENTINEL"
export EXAM_RUN_ID="run-$(date +%s)-$SENTINEL"
for tz in UTC America/New_York Asia/Shanghai Asia/Kolkata; do
  TZ="$tz" node tests/hidden_p1.js
done
echo "sentinel=$EXAM_SENTINEL run_id=$EXAM_RUN_ID"
