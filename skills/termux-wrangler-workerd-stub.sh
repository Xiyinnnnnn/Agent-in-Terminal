#!/usr/bin/env bash
# Android 上 wrangler 一 require('workerd') 就抛 Unsupported platform: android arm64 LE
# deploy/secret/tail 都不需要真正的 workerd 进程，因此把 binPath 计算降级为桩；仅 wrangler dev 会受影响。
set -euo pipefail
F="node_modules/workerd/lib/main.js"
[ -f "$F" ] || { echo "先 npm install"; exit 1; }
python3 - "$F" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
if 'WORKERD_STUB' in s:
    print('已打过桩，跳过'); raise SystemExit(0)
old = 'var { binPath } = generateBinPath();'
stub = ('var { binPath } = (function(){ try { return generateBinPath(); } '
        'catch (e) { return { binPath: process.env.WORKERD_STUB || "/system/bin/true" }; } })();')
assert old in s, 'anchor not found（workerd 版本可能变了）'
open(p, 'w').write(s.replace(old, stub, 1))
print('已打桩：', p)
PY
