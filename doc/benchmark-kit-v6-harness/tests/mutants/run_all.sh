#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")"
killed=0; total=0
for f in m[0-9]*.sh; do
  [ "$f" = "run_all.sh" ] && continue
  total=$((total+1))
  if bash "$f" >/dev/null 2>&1; then
    echo "killed  $f"; killed=$((killed+1))
  else
    echo "alive   $f"
  fi
done
echo "killed=$killed/$total"
[ "$killed" -eq "$total" ]
