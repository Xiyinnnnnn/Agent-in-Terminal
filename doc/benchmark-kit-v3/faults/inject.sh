#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  schema)
    node -e '
const fs=require("node:fs");
const f="stage1/report/records.json";
if(!fs.existsSync(f)) { console.error("先完成 cp2"); process.exit(1); }
const d=JSON.parse(fs.readFileSync(f,"utf8"));
for (const r of d) r.meta={schema:"1.1"};
fs.writeFileSync(f, JSON.stringify(d,null,2)+"\n");
console.log("注入 schema 1.1：records 增加 meta 字段");'
    ;;
  dead-node)
    mkdir -p .fault-path
    printf '#!/bin/sh\necho "node: command not found" >&2\nexit 127\n' > .fault-path/node
    chmod +x .fault-path/node
    echo "注入 dead-node：用 PATH=\$PWD/.fault-path:\$PATH 模拟；自救用 vendor/bin/node-run"
    ;;
  *) echo "用法: faults/inject.sh schema|dead-node" >&2; exit 2 ;;
esac
