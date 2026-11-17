#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md2pdf.py — Termux/Android 本地 Markdown → PDF（纯 Python，依赖 fpdf2 + fonttools）

用法: python3 md2pdf.py 输入.md [输出.pdf] [--size 8] [--landscape]

要点:
  * 系统无 pandoc/LaTeX 时可用；中文字体用 /system/fonts/DroidSansChinese.ttf
    (TrueType/glyf，fpdf2 可渲染；NotoSansCJK 是 CFF2，fpdf2 不支持)
  * 中文缺 ASCII，故主字体 DroidSansChinese + 缺字回退 DroidSans
  * 支持: 标题 #/##/###、表格(自动列宽+换行+续页表头)、列表、分隔线、
    代码块、**粗体**(渲染为深红)、自动分页、页脚页码
"""
import os, re, sys

from fpdf import FPDF
from fontTools.ttLib import TTFont

CN_FONT = os.environ.get('MD2PDF_CN_FONT', '/system/fonts/DroidSansChinese.ttf')
LAT_FONT = os.environ.get('MD2PDF_LAT_FONT', '/system/fonts/DroidSans.ttf')

INK = (26, 26, 26)
MUTED = (120, 120, 120)
BOLD_C = (176, 28, 28)
GRID = (190, 190, 190)
HEAD_BG = (238, 240, 244)
CODE_BG = (245, 245, 245)


def _cmap(path):
    f = TTFont(path, lazy=True)
    s = set()
    for t in f['cmap'].tables:
        s |= set(t.cmap)
    f.close()
    return s


def _vis(s):
    """视觉宽度：CJK 记 2，其它记 1"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def _runs(text):
    """把 **bold** 拆成 [(text, bold)]"""
    text = re.sub(r'`([^`]*)`', r'\1', text)
    out, i = [], 0
    for m in re.finditer(r'\*\*(.+?)\*\*', text):
        if m.start() > i:
            out.append((text[i:m.start()], False))
        out.append((m.group(1), True))
        i = m.end()
    if i < len(text):
        out.append((text[i:], False))
    return out or [(text, False)]


def _tokens(runs):
    """ASCII 字母数字串视为不可拆分 token，其余逐字符"""
    toks = []
    for text, bold in runs:
        buf = ''
        for ch in text:
            if ch.isascii() and (ch.isalnum() or ch in '%./-+<>'):
                buf += ch
            else:
                if buf:
                    toks.append((buf, bold)); buf = ''
                toks.append((ch, bold))
        if buf:
            toks.append((buf, bold))
    return toks


class MD2PDF(FPDF):
    def __init__(self, size=8.0, landscape=True):
        super().__init__(orientation='L' if landscape else 'P', unit='mm', format='A4')
        self.set_margins(12, 11, 12)
        self.set_auto_page_break(False)
        self.base_size = size
        self.add_font('cn', '', CN_FONT)
        self.add_font('lat', '', LAT_FONT)
        self.cn_set = _cmap(CN_FONT)
        self.lat_set = _cmap(LAT_FONT)
        self._wc = {}
        self.table_header = None
        self.src_note = ''

    # ---------- 度量 ----------
    def fam(self, ch):
        o = ord(ch)
        if o in self.cn_set:
            return 'cn'
        if o in self.lat_set:
            return 'lat'
        return 'lat'

    def cw(self, ch, size):
        k = (ch, size)
        v = self._wc.get(k)
        if v is None:
            self.set_font(self.fam(ch), '', size)
            v = self.get_string_width(ch)
            self._wc[k] = v
        return v

    def tok_w(self, text, size):
        return sum(self.cw(c, size) for c in text)

    def line_h(self, size):
        return size * 1.5 * 0.3528

    # ---------- 分页 ----------
    def bottom(self):
        return self.h - self.b_margin - 7  # 给页脚留位

    def need(self, h):
        if self.get_y() + h > self.bottom():
            self.add_page()

    # ---------- 绘制 ----------
    def draw_tokens(self, x, y, h, toks, size, color=INK):
        segs = []
        for text, bold in toks:
            for ch in text:
                key = (self.fam(ch), bold)
                if segs and segs[-1][0] == key:
                    segs[-1][1] += ch
                else:
                    segs.append([key, ch])
        cx = x
        for (f, bold), s in segs:
            self.set_font(f, '', size)
            self.set_text_color(*(BOLD_C if bold else color))
            w = self.get_string_width(s)
            self.set_xy(cx, y)
            self.cell(w, h, s)
            cx += w
        self.set_text_color(*color)
        return cx

    def wrap(self, toks, maxw, size):
        lines, cur, curw = [], [], 0.0
        for text, bold in toks:
            w = self.tok_w(text, size)
            if w > maxw and len(text) > 1:          # 超宽 token 逐字符拆
                for ch in text:
                    cwv = self.cw(ch, size)
                    if curw + cwv > maxw and cur:
                        lines.append(cur); cur, curw = [], 0.0
                    cur.append((ch, bold)); curw += cwv
                continue
            if curw + w > maxw and cur:
                lines.append(cur); cur, curw = [], 0.0
            cur.append((text, bold)); curw += w
        if cur:
            lines.append(cur)
        return lines or [[]]

    # ---------- 块渲染 ----------
    def heading(self, text, level):
        size = {1: 15.0, 2: 12.0, 3: 10.5}.get(level, 10.0)
        lh = self.line_h(size) * 1.05
        toks = _tokens(_runs(text))
        lines = self.wrap(toks, self.w - self.l_margin - self.r_margin, size)
        self.need(len(lines) * lh + 4)
        y = self.get_y()
        for ln in lines:
            self.draw_tokens(self.l_margin, y, lh, ln, size)
            y += lh
        if level == 1:
            self.set_draw_color(60, 60, 60)
            self.set_line_width(0.4)
            self.line(self.l_margin, y + 0.8, self.w - self.r_margin, y + 0.8)
            y += 2.5
        self.set_y(y + 1.2)

    def para(self, text):
        size = self.base_size
        lh = self.line_h(size)
        lines = self.wrap(_tokens(_runs(text)), self.w - self.l_margin - self.r_margin, size)
        for ln in lines:
            self.need(lh)
            self.draw_tokens(self.l_margin, self.get_y(), lh, ln, size)
            self.set_y(self.get_y() + lh)
        self.set_y(self.get_y() + 0.8)

    def bullet(self, text, indent=0.0):
        size = self.base_size
        lh = self.line_h(size)
        x0 = self.l_margin + indent
        avail = self.w - self.r_margin - x0 - 4
        lines = self.wrap(_tokens(_runs(text)), avail, size)
        self.need(len(lines) * lh)
        y = self.get_y()
        for i, ln in enumerate(lines):
            if i == 0:
                self.set_font('cn', '', size)
                self.set_text_color(*MUTED)
                self.set_xy(x0, y)
                self.cell(4, lh, '·')
            self.draw_tokens(x0 + 4, y, lh, ln, size)
            y += lh
        self.set_y(y)

    def code_block(self, lines):
        size = self.base_size - 0.5
        lh = self.line_h(size)
        pad = 1.8
        h = len(lines) * lh + 2 * pad
        self.need(h + 2)
        x, y = self.l_margin, self.get_y()
        self.set_fill_color(*CODE_BG)
        self.rect(x, y, self.w - self.l_margin - self.r_margin, h, style='F')
        yy = y + pad
        for ln in lines:
            self.draw_tokens(x + 2, yy, lh, _tokens(_runs(ln or ' ')), size)
            yy += lh
        self.set_y(y + h + 2)

    def hr(self):
        self.need(4)
        y = self.get_y() + 1.5
        self.set_draw_color(*GRID)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.set_y(y + 2)

    def table(self, rows):
        ncol = max(len(r) for r in rows)
        rows = [r + [''] * (ncol - len(r)) for r in rows]
        head, body = rows[0], rows[1:]
        size = self.base_size
        lh = self.line_h(size)
        pad = 1.9
        avail = self.w - self.l_margin - self.r_margin

        weights = []
        for c in range(ncol):
            m = max(_vis(r[c]) for r in rows)
            weights.append(max(m, 3) ** 0.82)
        tot = sum(weights)
        widths = [max(12.0, avail * w / tot) for w in weights]
        scale = avail / sum(widths)
        widths = [w * scale for w in widths]

        def row_lines(r):
            return [self.wrap(_tokens(_runs(r[c])), widths[c] - 2 * pad, size) for c in range(ncol)]

        def draw_row(r, is_head):
            ls = row_lines(r)
            h = max(len(x) for x in ls) * lh + 2 * pad
            if self.get_y() + h > self.bottom():
                self.add_page()
                if not is_head:
                    draw_row(head, True)
            y = self.get_y()
            x = self.l_margin
            for c in range(ncol):
                if is_head:
                    self.set_fill_color(*HEAD_BG)
                    self.rect(x, y, widths[c], h, style='F')
                self.set_draw_color(*GRID)
                self.set_line_width(0.25)
                self.rect(x, y, widths[c], h)
                yy = y + pad
                for ln in ls[c]:
                    if is_head:
                        self.draw_tokens(x + pad, yy, lh, [(t, True) for t, _ in ln], size)
                    else:
                        self.draw_tokens(x + pad, yy, lh, ln, size)
                    yy += lh
                x += widths[c]
            self.set_y(y + h)

        draw_row(head, True)
        for r in body:
            draw_row(r, False)
        self.set_y(self.get_y() + 3)

    # ---------- 页脚 ----------
    def draw_footers(self, note):
        n = len(self.pages)
        sep = '·' if ord('·') in self.lat_set or ord('·') in self.cn_set else '-'
        for i in sorted(self.pages):
            self.page = i
            toks = _tokens(_runs(f'{note}   {sep}   {i} / {n}'))
            w = sum(self.tok_w(t, 7) for t, _ in toks)
            self.draw_tokens(max(self.l_margin, (self.w - w) / 2), self.h - 9, 5, toks, 7, MUTED)
        self.set_text_color(*INK)


def parse(md):
    """→ [(kind, payload)]"""
    lines = md.splitlines()
    blocks, i = [], 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1; continue
        if s.startswith('```'):
            i += 1; buf = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                buf.append(lines[i]); i += 1
            i += 1
            blocks.append(('code', buf)); continue
        m = re.match(r'^(#{1,6})\s+(.*)$', s)
        if m:
            blocks.append(('head', (len(m.group(1)), m.group(2)))); i += 1; continue
        if re.match(r'^(-{3,}|\*{3,})$', s):
            blocks.append(('hr', None)); i += 1; continue
        if s.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s:\-\|]+\|?$', lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cur = lines[i].strip()
                if not re.match(r'^\|[\s:\-\|]+\|?$', cur):
                    cells = [c.strip() for c in cur.strip('|').split('|')]
                    rows.append(cells)
                i += 1
            blocks.append(('table', rows)); continue
        m = re.match(r'^([-*+]|\d+[.)])\s+(.*)$', s)
        if m:
            indent = 0.0
            blocks.append(('li', (m.group(2), indent))); i += 1; continue
        if s.startswith('>'):
            blocks.append(('para', s.lstrip('> ').strip())); i += 1; continue
        blocks.append(('para', s)); i += 1
    return blocks


def main():
    args = [a for a in sys.argv[1:]]
    size, landscape = 8.0, True
    if '--size' in args:
        k = args.index('--size'); size = float(args[k + 1]); del args[k:k + 2]
    if '--portrait' in args:
        landscape = False; args.remove('--portrait')
    if not args:
        print(__doc__); sys.exit(1)
    src = os.path.abspath(args[0])
    dst = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '.pdf'

    md = open(src, encoding='utf-8').read()
    pdf = MD2PDF(size=size, landscape=landscape)
    pdf.src_note = os.path.basename(src)
    pdf.add_page()
    for kind, payload in parse(md):
        if kind == 'head':
            pdf.heading(payload[1], payload[0])
        elif kind == 'table':
            pdf.table(payload)
        elif kind == 'code':
            pdf.code_block(payload)
        elif kind == 'hr':
            pdf.hr()
        elif kind == 'li':
            pdf.bullet(payload[0])
        else:
            pdf.para(payload)
    pdf.draw_footers(os.path.basename(src))
    pdf.output(dst)
    print(f'OK -> {dst}  ({os.path.getsize(dst)/1024:.0f} KB, {len(pdf.pages)} 页)')


if __name__ == '__main__':
    main()
