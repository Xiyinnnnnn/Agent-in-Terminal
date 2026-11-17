#!/usr/bin/env python3
"""疑难杂症-强模型诊断 one shot：八段交接走 stdin，诊断到 stdout，不落盘。

key.bin = base64(明文 ^ sha256(machine-id))，只进 Authorization 头。
授权由 agent 在本体对话中取得，脚本不含开关。"""
import base64, hashlib, json, os, sys, time, urllib.error, urllib.request

CFG = os.path.expanduser("~/.config/cli-agent")
KEYBIN = os.path.join(CFG, "key.bin")
BASE = "http://127.0.0.1:3050/v1"
MODEL = "moonshotai/Kimi-K3.1-Pro"
LEVELS = {"high": 8192, "max": 16384}  # 档位 → 输出预算

SYSTEM = """[ROLE] 疑难诊断顾问：只出诊断，不接管执行。

[IN] 八段交接：GOAL ENV STATE EVID TRIED EXCL CONSTRAINT ASK

[RULE]
事实 | 假设 | 未知 分开写
TRIED 已失败的方案不再提
证据不足的结论标「待验证」

[OUT]
[DIAG] 最可能根因；不确定则写待验证假设
[CONF] HIGH | MEDIUM | LOW
[STEP] 下一步，≤5 条，按 信息增益 / 成本 / 改动量 排序
[IF] 观察 X → 动作 A；否则 → 动作 B
[PATCH] 最小补丁，≤15 行
[MISSING] 影响判断的关键缺失项，仅 1 条

[NEVER] 复述输入 | 编造根因 | 接管执行"""

HANDOFF = """[GOAL] 用户原始目标，1 句
[ENV] OS | 运行时版本 | 关键依赖@版本 | cwd
[STATE] 当前可观察状态，≤3 条
[EVID] 能改变判断的命令/退出码/错误/代码片段
[TRIED] 已尝试动作 → 实际结果，≤5 条
[EXCL] 已证伪假设 → 排除证据，≤3 条；无证据不列
[CONSTRAINT] 不可改变项与必须遵守的约束
[ASK] 唯一未解决问题，具体到待判断的因果或方案"""

REQUIRED = ("[GOAL]", "[ASK]")


def decode_keybin(path=KEYBIN):
    try:
        seed = open("/etc/machine-id", encoding="utf-8").read().strip()
    except OSError:
        seed = os.uname().nodename + os.path.expanduser("~")
    mk = hashlib.sha256(seed.encode()).digest()
    raw = base64.b64decode(open(path, encoding="utf-8").read().strip())
    return bytes(c ^ mk[i % len(mk)] for i, c in enumerate(raw)).decode("utf-8")


def main():
    level = sys.argv[1] if len(sys.argv) > 1 else "high"
    if level in ("-h", "--help") or len(sys.argv) > 2:
        print("用法: escalate.py [high|max] <<'EOF' … EOF\n")
        print(HANDOFF)
        return 0
    if level not in LEVELS:
        raise SystemExit("思考等级只能是 high 或 max")

    if sys.stdin.isatty():
        print("用法: escalate.py [high|max] <<'EOF' … EOF   # 交接包走 stdin，不落盘\n")
        print(HANDOFF)
        return 0

    handoff = sys.stdin.read().strip()
    lack = [t for t in REQUIRED if t not in handoff]
    if lack:
        raise SystemExit("交接包缺必需段 %s；无参运行看模板" % " ".join(lack))

    payload = {
        "model": MODEL,
        "reasoning_effort": level,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": handoff}],
        "max_tokens": LEVELS[level],
        "temperature": 1,
        "stream": False,
    }
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + decode_keybin(), "Content-Type": "application/json",
                 "User-Agent": "cli", "x-cli-environment": "production"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as f:
            d = json.loads(f.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:600]}")
    except urllib.error.URLError as e:
        raise SystemExit(f"连不上 {BASE}（{e.reason}）：先起 commandcode-proxy")

    ch = (d.get("choices") or [{}])[0]
    text = (ch.get("message") or {}).get("content") or ""
    u = d.get("usage") or {}
    print(f"[ESCALATE] {MODEL} level={level} {time.time()-t0:.1f}s "
          f"finish={ch.get('finish_reason')} tok={u.get('prompt_tokens')}/{u.get('completion_tokens')}")
    print(text or "[ESCALATE] 空返回：看 completion_tokens 是否被思考链吃满")
    return 0 if text else 1


if __name__ == "__main__":
    sys.exit(main())
