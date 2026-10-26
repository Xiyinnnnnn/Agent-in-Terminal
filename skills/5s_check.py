#!/usr/bin/env python3
import json, re, sys
from pathlib import Path

ROOT = Path.home() / ".config" / "term_agent"
DIRS = ["memory", "skill", "taskbook"]
# 上限按"读一次成本"定：skill 常与命令同批载入故严格；memory 按主题隔离单篇深读
LIM = {"skill": (10 * 1024, 7 * 1024), "memory": (24 * 1024, 14 * 1024), "taskbook": (24 * 1024, 12 * 1024)}
# 索引上限按"可承载文件数 × 实测单文件行开销"定，硬限=200/100 文件规模，软限=硬限 75%
# 实测 2026-10-27：memory 154 B/文件、skill 240 B/文件、taskbook 主题式压缩增长
IDX_LIM = {"skill": 24 * 1024, "memory": 32 * 1024, "taskbook": 24 * 1024}
IDX_SOFT = {"skill": 18 * 1024, "memory": 24 * 1024, "taskbook": 18 * 1024}
LONGLINE = 240

def sev_of(kind):
    return "warn" if kind in ("near_limit", "long_line", "archive_suffix", "index_near_limit") else "error"

def emit(d): print(json.dumps(d, ensure_ascii=False, separators=(",", ":")))

def scan(d):
    out = []
    idx = d / "00-索引.md"
    top = sorted(p for p in d.glob("*.md") if p.name != "00-索引.md")
    lines = idx.read_text().splitlines() if idx.exists() else []

    # 1 索引漏收 / 重复行
    for p in top:
        hit = [l for l in lines if l.startswith("| ") and p.stem in l.split("|")[1]]
        if not hit:
            out.append({"kind": "index_missing", "file": str(p), "detail": "未进 00-索引.md"})
        elif len(hit) > 1:
            out.append({"kind": "index_dup", "file": str(p), "detail": "索引出现 %d 次" % len(hit)})
    # 2 空件 / 超限 / 缺 H2
    for p in top:
        n = p.stat().st_size
        if n < 100:
            out.append({"kind": "empty_file", "file": str(p), "detail": "%d B" % n})
        hard, soft = LIM.get(d.name, (16 * 1024, 10 * 1024))
        if n > hard:
            out.append({"kind": "too_big", "file": str(p), "detail": "%d B > %d" % (n, hard)})
        elif n > soft:
            out.append({"kind": "near_limit", "file": str(p), "detail": "%d B > %d" % (n, soft)})
        t = p.read_text()
        if "\n## " not in t:
            out.append({"kind": "no_h2", "file": str(p), "detail": "无二级标题"})
        # 3 长散文行（跳过代码块）
        fenced = False
        for i, l in enumerate(t.splitlines(), 1):
            if l.startswith("```"):
                fenced = not fenced; continue
            if fenced or l.startswith(("|", "#", "-", "*", " ", "`", ">")) or re.match(r"^\d+[.、]", l):
                continue
            if len(l) > LONGLINE:
                out.append({"kind": "long_line", "file": str(p), "line": i, "detail": "%d 字符" % len(l)})
    # 4 表格列数不一致
    for p in top:
        prev = None
        for i, l in enumerate(p.read_text().splitlines(), 1):
            if not l.startswith("|"):
                prev = None; continue
            bare = re.sub(r"`[^`]*`", "", l)
            cnt = len(re.findall(r"(?<!\\)\|", bare))
            if prev is not None and cnt != prev:
                out.append({"kind": "table_cols", "file": str(p), "line": i,
                            "detail": "%d 管符 ≠ 上行 %d" % (cnt, prev)})
            prev = cnt
    # 5 后缀：废弃件一律 -dep（后缀即标记，无需再进索引）
    for p in top:
        if p.name.count("-eol") or p.name.endswith("-dep.md"):
            continue
    # 6 索引超限
    il = IDX_LIM.get(d.name, 24 * 1024)
    isf = IDX_SOFT.get(d.name, 18 * 1024)
    if idx.exists():
        n = idx.stat().st_size
        if n > il:
            out.append({"kind": "index_too_big", "file": str(idx), "detail": "%d B > %d" % (n, il)})
        elif n > isf:
            out.append({"kind": "index_near_limit", "file": str(idx), "detail": "%d B > %d（硬限 %d）" % (n, isf, il)})
    return out

targets = sys.argv[1:] or DIRS
findings = []
for d in targets:
    p = ROOT / d
    if p.is_dir():
        findings += scan(p)
for f in findings:
    f["sev"] = sev_of(f["kind"])
errs = [f for f in findings if f["sev"] == "error"]
emit({"ev": "check", "dirs": targets, "n": len(findings), "errors": len(errs),
      "ok": not errs, "findings": findings})
sys.exit(0 if not errs else 1)
