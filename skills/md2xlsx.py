#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2xlsx.py — Markdown 表格 → Excel(.xlsx)，每个表格一个 sheet（openpyxl）

用法: python3 md2xlsx.py in.md [out.xlsx]
规则: sheet 名取最近的前置标题；纯数字转数值；表头加粗+底色+冻结首行；列宽自适应。
"""
import os
import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SEP = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")
BAD = re.compile(r"[\\/*?:\[\]]")


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def clean(v):
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", v)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)


def to_num(v):
    t = clean(v).replace(",", "")
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return clean(v)


def parse(md):
    out, head, cur = [], "", None
    for ln in md.splitlines():
        if re.match(r"^#{1,6}\s+", ln):
            head = re.sub(r"^#{1,6}\s+", "", ln).strip()
            continue
        if ln.strip().startswith("|"):
            if cur is None:
                cur = {"title": head or "Sheet", "rows": [cells(ln)]}
            elif SEP.match(ln):
                continue
            else:
                cur["rows"].append(cells(ln))
            continue
        if cur:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def safe_name(t, used):
    n = BAD.sub("_", t)[:31] or "Sheet"
    base, k = n, 2
    while n in used:
        n = ("%s_%d" % (base, k))[:31]
        k += 1
    used.add(n)
    return n


def main():
    if len(sys.argv) < 2:
        print("usage: md2xlsx.py in.md [out.xlsx]", file=sys.stderr)
        return 2
    src = sys.argv[1]
    if not os.path.isfile(src):
        print("no_such_file: " + src, file=sys.stderr)
        return 2
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".xlsx"

    tables = parse(open(src, encoding="utf-8").read())
    if not tables:
        print("no_tables", file=sys.stderr)
        return 6

    wb = Workbook()
    wb.remove(wb.active)
    fill = PatternFill("solid", fgColor="EFEFEF")
    for t in tables:
        ws = wb.create_sheet(safe_name(t["title"], set(wb.sheetnames)))
        for r, row in enumerate(t["rows"], 1):
            for c, v in enumerate(row, 1):
                cell = ws.cell(row=r, column=c, value=to_num(v) if r > 1 else v)
                if r == 1:
                    cell.font = Font(bold=True)
                    cell.fill = fill
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for c in range(1, max(len(r) for r in t["rows"]) + 1):
            w = max(len(str(r[c - 1])) if c <= len(r) else 0 for r in t["rows"])
            ws.column_dimensions[get_column_letter(c)].width = min(60, max(8, w * 1.8))
        ws.freeze_panes = "A2"
    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    wb.save(dst)
    print('{"ev":"ok","out":"%s","sheets":%d}' % (dst, len(tables)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
