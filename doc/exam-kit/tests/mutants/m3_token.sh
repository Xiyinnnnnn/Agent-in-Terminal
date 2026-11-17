#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/../.."
! grep -q "endpoint unreachable" report/index.js
