#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
! grep -q "endpoint unreachable" stage1/report/index.js
