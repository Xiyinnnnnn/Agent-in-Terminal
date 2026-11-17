#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2md.py — 任意文件 → 标准 Markdown（MarkItDown 0.1.8 封装）

用途：给 agent 一个统一的「文件抽象层」。任何二进制/半结构化文件先转成 md，再读、再推理。
补齐项：本机无 pandas，故自带 openpyxl/xlrd 版 xlsx/xls 转换器（中文名、多 sheet、空行裁剪）。

用法：
  python3 md2md.py 文件              # 输出到 stdout
  python3 md2md.py 文件 -o out.md    # 写文件
  python3 md2md.py 目录 -o 输出目录  # 批量，保留相对路径，扩展名换成 .md
  python3 md2md.py -                 # stdin 直读
  python3 md2md.py 文件 --plain      # 关闭 onnxruntime 警告屏蔽（调试用）
"""
import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore", message=r".*Unsupported platform.*")
warnings.filterwarnings("ignore", category=UserWarning, module=r"onnxruntime.*")

from markitdown import MarkItDown
from markitdown._base_converter import DocumentConverter, DocumentConverterResult


# ---------- 自定义转换器：xlsx / xls（无 pandas 环境） ----------
def _cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>").strip()


def _rows_to_md(rows, title):
    rows = [[_cell(c) for c in r] for r in rows]
    rows = [r for r in rows if any(x for x in r)]
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["## " + title, "", "| " + " | ".join(rows[0]) + " |",
           "| " + " | ".join("---" for _ in rows[0]) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


class OpenpyxlXlsxConverter(DocumentConverter):
    ACCEPTED_FILE_EXTENSIONS = [".xlsx", ".xlsm"]
    ACCEPTED_MIME_TYPE_PREFIXES = [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ]

    def accepts(self, file_stream, stream_info, **kwargs):
        ext = (stream_info.extension or "").lower()
        if ext in self.ACCEPTED_FILE_EXTENSIONS:
            return True
        return any((stream_info.mimetype or "").lower().startswith(p)
                   for p in self.ACCEPTED_MIME_TYPE_PREFIXES)

    def convert(self, file_stream, stream_info, **kwargs):
        import openpyxl
        wb = openpyxl.load_workbook(file_stream, data_only=True, read_only=True)
        parts = []
        try:
            for ws in wb.worksheets:
                t = _rows_to_md(ws.iter_rows(values_only=True), ws.title or "Sheet")
                if t:
                    parts.append(t)
        finally:
            wb.close()
        return DocumentConverterResult(markdown=("\n\n".join(parts) + "\n") if parts else "")


class XlrdXlsConverter(DocumentConverter):
    ACCEPTED_FILE_EXTENSIONS = [".xls"]
    ACCEPTED_MIME_TYPE_PREFIXES = ["application/vnd.ms-excel", "application/excel"]

    def accepts(self, file_stream, stream_info, **kwargs):
        ext = (stream_info.extension or "").lower()
        if ext in self.ACCEPTED_FILE_EXTENSIONS:
            return True
        return any((stream_info.mimetype or "").lower().startswith(p)
                   for p in self.ACCEPTED_MIME_TYPE_PREFIXES)

    def convert(self, file_stream, stream_info, **kwargs):
        import xlrd
        data = file_stream.read()
        wb = xlrd.open_workbook(file_contents=data)
        parts = []
        for sh in wb.sheets():
            rows = [sh.row_values(i) for i in range(sh.nrows)]
            t = _rows_to_md(rows, sh.name or "Sheet")
            if t:
                parts.append(t)
        return DocumentConverterResult(markdown=("\n\n".join(parts) + "\n") if parts else "")


class PillowImageConverter(DocumentConverter):
    """图片 → md：无 exiftool 环境下用 Pillow 给出可读元数据（内置转换器此时返回空）。"""

    ACCEPTED_FILE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp",
                                ".webp", ".tif", ".tiff"]
    ACCEPTED_MIME_TYPE_PREFIXES = ["image/"]

    def accepts(self, file_stream, stream_info, **kwargs):
        if (stream_info.extension or "").lower() in self.ACCEPTED_FILE_EXTENSIONS:
            return True
        return (stream_info.mimetype or "").lower().startswith("image/")

    def convert(self, file_stream, stream_info, **kwargs):
        try:
            from PIL import Image, ExifTags
            im = Image.open(file_stream)
        except Exception:  # noqa: BLE001
            return DocumentConverterResult(markdown="")
        name = stream_info.filename or "image"
        lines = ["![%s](%s)" % (name, name), "",
                 "| 项 | 值 |", "| --- | --- |",
                 "| 格式 | %s |" % (im.format or "?"),
                 "| 尺寸 | %dx%d px |" % im.size,
                 "| 色彩模式 | %s |" % im.mode]
        try:
            exif = im.getexif()
            items = [(ExifTags.TAGS.get(k, str(k)), v) for k, v in exif.items()]
            for k, v in items[:40]:
                try:
                    v = str(v)[:120]
                except Exception:  # noqa: BLE001
                    continue
                lines.append("| EXIF.%s | %s |" % (_cell(k), _cell(v)))
        except Exception:  # noqa: BLE001
            pass
        return DocumentConverterResult(markdown="\n".join(lines) + "\n")


def build():
    md = MarkItDown(enable_plugins=False)
    md.register_converter(OpenpyxlXlsxConverter(), priority=0.0)
    md.register_converter(XlrdXlsConverter(), priority=0.0)
    md.register_converter(PillowImageConverter(), priority=-0.5)
    return md


def convert_one(md, path):
    return md.convert(path).markdown


def main():
    ap = argparse.ArgumentParser(description="任意文件 → Markdown")
    ap.add_argument("src", help="文件或目录")
    ap.add_argument("-o", "--out", help="输出文件 / 输出目录")
    ap.add_argument("--plain", action="store_true", help="不屏蔽 onnxruntime 警告")
    a = ap.parse_args()

    if a.plain:
        for f in list(warnings.filters):
            if f[1] is not None and "Unsupported platform" in str(f[1]):
                warnings.filters.remove(f)

    md = build()
    raw_src = a.src

    # stdin 直读：md2md -（与 URL 通道同样支持 -o）
    if raw_src == "-":
        try:
            text = md.convert_stream(sys.stdin.buffer).markdown
        except Exception as e:  # noqa: BLE001
            print("CONVERT FAILED: <stdin>: %s" % e, file=sys.stderr)
            return 1
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote " + a.out, file=sys.stderr)
        else:
            sys.stdout.write(text)
        return 0

    # URL 直达（markitdown 内置支持 http(s)、YouTube、Wikipedia）
    if raw_src.startswith(("http://", "https://")):
        try:
            text = md.convert(raw_src).markdown
        except Exception as e:  # noqa: BLE001
            print("CONVERT FAILED: %s: %s" % (raw_src, e), file=sys.stderr)
            return 1
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote " + a.out, file=sys.stderr)
        else:
            sys.stdout.write(text)
        return 0

    src = os.path.abspath(raw_src)

    if not os.path.exists(src):
        print("not found: " + src, file=sys.stderr)
        return 2

    if os.path.isfile(src):
        try:
            text = convert_one(md, src)
        except Exception as e:  # noqa: BLE001
            print("CONVERT FAILED: %s: %s" % (os.path.basename(src), e), file=sys.stderr)
            return 1
        if a.out:
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
            print("wrote " + a.out, file=sys.stderr)
        else:
            sys.stdout.write(text)
        return 0

    outdir = os.path.abspath(a.out or os.path.join("md_out"))
    os.makedirs(outdir, exist_ok=True)
    ok = bad = 0
    for root, _, files in os.walk(src):
        for fn in sorted(files):
            if fn.startswith(".") or fn.lower().endswith(".md"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, src)
            dst = os.path.join(outdir, rel + ".md")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            try:
                text = convert_one(md, p)
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(text)
                ok += 1
                print("OK   %-50s -> %s" % (rel, os.path.relpath(dst, outdir)), file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                bad += 1
                print("FAIL %-50s %s" % (rel, str(e)[:120]), file=sys.stderr)
    print("done: ok=%d fail=%d out=%s" % (ok, bad, outdir), file=sys.stderr)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
