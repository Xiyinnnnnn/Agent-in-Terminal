#!/usr/bin/env python3
# 00-wallet — 多平台额度查询，用 --provider 切换平台
#   openrouter : GET /api/v1/key + /api/v1/credits（余额=购-用）
#   opencode   : GET /inference/v1/models 探测 key；官方无公开余额接口
import argparse, json, os, sys, urllib.error, urllib.request
from pathlib import Path

CFG = Path.home() / ".config/term_agent"
P = {
    "openrouter": dict(name="OpenRouter", env="OPENROUTER_API_KEY", base_env="OPENROUTER_API_BASE",
                       base="https://openrouter.ai/api/v1", keyfile=CFG / "openrouter.key",
                       hint="https://openrouter.ai/settings/keys（新账号可用 sk-or-v1-x 占位测试 401）"),
    "opencode": dict(name="OpenCode（Console/Zen）", env="OPENCODE_API_KEY", base_env="OPENCODE_API_BASE",
                     base="https://opencode.ai/inference", keyfile=CFG / "opencode.key",
                     hint="Console → Account › Personal API keys（前缀 oc_sk_）"),
}
ALIAS = {"or": "openrouter", "oc": "opencode", "zen": "opencode"}

def key_of(name):
    c = P[name]
    for p in (c["keyfile"],):
        try:
            s = p.read_text().strip()
            if s: return s, str(p)
        except OSError: pass
    s = os.environ.get(c["env"], "").strip()
    return (s, c["env"]) if s else ("", "")

def base_of(name):
    return (os.environ.get(P[name]["base_env"]) or P[name]["base"]).rstrip("/")

def get(url, key, timeout):
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + key, "Accept": "application/json",
        "User-Agent": "cli", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"

def money(v):
    try: return "$%.2f" % float(v)
    except (TypeError, ValueError): return "—"

def bar(used, cap, w=10):
    cap = float(cap or 0); used = float(used or 0)
    p = 0 if cap <= 0 else min(1, used / cap)
    f = round(p * w)
    return "█" * f + "░" * (w - f) + " %3d%%" % round(p * 100)

def run_openrouter(key, timeout, as_json):
    b = base_of("openrouter"); errs = {}
    st1, t1 = get(b + "/key", key, timeout)
    st2, t2 = get(b + "/credits", key, timeout)
    def j(t):
        try: return json.loads(t)
        except Exception: return None
    kd, cd = j(t1), j(t2)
    if st1 >= 400: errs["key"] = f"HTTP {st1} " + (((kd or {}).get("error") or {}).get("message") or t1[:120])
    if st2 >= 400: errs["credits"] = f"HTTP {st2} " + (((cd or {}).get("error") or {}).get("message") or t2[:120])
    if as_json:
        print(json.dumps({"ok": st1 < 400, "key": kd, "credits": cd, "errors": errs}, ensure_ascii=False, indent=2))
        return 0 if st1 < 400 else (4 if st1 in (401, 403) else 1)
    d = (kd or {}).get("data") or {}
    cr = ((cd or {}).get("data") or {})
    out = ["OpenRouter 额度"]
    if d:
        kind = "管理 key" if d.get("is_management_key") else ("临时 key" if d.get("is_provisioning_key") else "普通 key")
        out.append("Key    %s  ·  %s  ·  免费层 %s" % (d.get("label", "—"), kind, "是" if d.get("is_free_tier") else "否"))
        if "total_credits" in cr:
            bal = float(cr["total_credits"]) - float(cr["total_usage"])
            out.append("余额   %s（购 %s － 已用 %s）" % (money(bal), money(cr["total_credits"]), money(cr["total_usage"])))
        if d.get("usage") is not None:
            out.append("用量   累计 %s · 日 %s · 周 %s · 月 %s" % (
                money(d.get("usage")), money(d.get("usage_daily")), money(d.get("usage_weekly")), money(d.get("usage_monthly"))))
        if d.get("limit") is not None:
            out.append("限额   %s %s / 剩 %s（重置 %s）" % (bar(d.get("usage"), d.get("limit")),
                       money(d.get("usage")), money(d.get("limit_remaining")), d.get("limit_reset") or "—"))
        else:
            out.append("限额   未设花费上限（uncapped）")
        fm = d.get("free_model_daily_requests") or {}
        if fm: out.append("免费模型 今日 %s/%s 次（剩 %s）" % (fm.get("used"), fm.get("limit"), fm.get("remaining")))
        for bd in (d.get("budgets") or [])[:3]:
            out.append("预算   %s %s / %s · 剩 %s · %s" % (bd.get("scope", "—"), money(bd.get("spend_usd")),
                       money(bd.get("limit_usd")), money(bd.get("remaining_usd")), bd.get("reset_interval") or ""))
    if "credits" in errs and st2 == 403:
        out.append("余额   需 Management key（普通 key 无权读 /credits）：%s" % errs["credits"])
    if "key" in errs:
        out.append("错误   %s" % errs["key"])
    print("\n".join(out))
    return 0 if st1 < 400 else (4 if st1 in (401, 403) else 1)

def run_opencode(key, timeout, as_json):
    b = base_of("opencode")
    st, t = get(b + "/v1/models", key, timeout)
    ok = st == 200
    if as_json:
        print(json.dumps({"ok": ok, "status": st, "models_bytes": len(t),
                          "balance_api": False, "note": "官方无公开余额接口"}, ensure_ascii=False, indent=2))
        return 0 if ok else (4 if st in (401, 403) else 1)
    out = ["OpenCode（Console / Zen）"]
    out.append("Key    %s" % ("有效 ✓" if ok else ("无效 ✗ HTTP %s" % st if st else "网络失败")))
    if st == 200:
        try: n = len(json.loads(t).get("data", []))
        except Exception: n = 0
        out.append("模型   可列 %d 个（该端点 200 = key 可鉴权）" % n)
    out.append("余额   官方未提供公开接口（issue #10448 仍在请求中）")
    out.append("查看   Console → Activity / 顶部 Billing 抽屉（快捷键 B）；Settings › Billing")
    out.append("用量   `opencode stats`（本地统计，非账户余额）")
    print("\n".join(out))
    return 0 if ok else (4 if st in (401, 403) else 1)

def main():
    ap = argparse.ArgumentParser(add_help=True, description="多平台额度查询")
    ap.add_argument("provider", nargs="?", default="openrouter", help="openrouter|opencode（可写 or/oc/zen）")
    ap.add_argument("--key", default="", help="临时指定 key（优先于环境变量与文件）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=int, default=20)
    a = ap.parse_args()
    name = ALIAS.get(a.provider.lower(), a.provider.lower())
    if name not in P:
        print("未知 provider：%s（可选 %s）" % (a.provider, " / ".join(P)), file=sys.stderr)
        return 5
    key, src = (a.key, "--key") if a.key else key_of(name)
    if not key:
        print("无 %s key。获取：%s\n配置：export %s=... 或写入 %s（chmod 600）" %
              (P[name]["name"], P[name]["hint"], P[name]["env"], P[name]["keyfile"]), file=sys.stderr)
        return 2
    return run_openrouter(key, a.timeout, a.json) if name == "openrouter" else run_opencode(key, a.timeout, a.json)

if __name__ == "__main__":
    sys.exit(main())
