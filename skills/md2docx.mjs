#!/usr/bin/env node
// md2docx.mjs — Markdown → Word(.docx)，纯 JS（npm docx）
// 用法: node md2docx.mjs in.md [out.docx] [--title "标题"]
import fs from "node:fs";
import path from "node:path";
import * as docx from "docx";

const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, Footer, PageNumber,
} = docx;

const A4_W = 11906, MARGIN = 960, CONTENT_W = A4_W - MARGIN * 2;

function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const s = m[0];
    if (s.startsWith("**")) out.push(new TextRun({ text: s.slice(2, -2), bold: true, ...base }));
    else if (s.startsWith("`")) out.push(new TextRun({ text: s.slice(1, -1), font: "Consolas", ...base }));
    else out.push(new TextRun({ text: s.slice(1, -1), italics: true, ...base }));
    last = m.index + s.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out.length ? out : [new TextRun({ text: "", ...base })];
}

function splitRow(line) {
  return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
}

function table(rows) {
  const body = rows.filter((r) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(r)).map(splitRow);
  if (!body.length) return null;
  const cols = Math.max(...body.map((r) => r.length));
  const w = Math.floor(CONTENT_W / cols);
  const mk = (cells, head) => new TableRow({
    tableHeader: head,
    children: Array.from({ length: cols }, (_, i) =>
      new TableCell({
        width: { size: w, type: WidthType.DXA },
        shading: head ? { type: ShadingType.CLEAR, fill: "EFEFEF" } : undefined,
        children: [new Paragraph({ children: runs(cells[i] || "", head ? { bold: true } : {}) })],
      })),
  });
  return new Table({
    columnWidths: Array(cols).fill(w),
    width: { size: CONTENT_W, type: WidthType.DXA },
    rows: [mk(body[0], true), ...body.slice(1).map((r) => mk(r, false))],
  });
}

function build(md) {
  const lines = md.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.trim()) { i++; continue; }

    const fence = ln.match(/^\s*```(\w*)\s*$/);
    if (fence) {
      const buf = [];
      i++;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) buf.push(lines[i++]);
      i++;
      blocks.push(new Paragraph({
        children: buf.map((t, k) => new TextRun({ text: t || " ", font: "Consolas", size: 18, break: k > 0 })),
        shading: { type: ShadingType.CLEAR, fill: "F5F5F5" },
        spacing: { before: 80, after: 80 },
        indent: { left: 200 },
      }));
      continue;
    }

    if (/^\s*\|/.test(ln) && /^\s*\|/.test(lines[i + 1] || "")) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const t = table(rows);
      if (t) { blocks.push(t); blocks.push(new Paragraph({ text: "" })); }
      continue;
    }

    const h = ln.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const lvl = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3,
                   HeadingLevel.HEADING_4, HeadingLevel.HEADING_5, HeadingLevel.HEADING_6][h[1].length - 1];
      blocks.push(new Paragraph({ heading: lvl, children: runs(h[2]), spacing: { before: 240, after: 120 } }));
      i++; continue;
    }

    if (/^\s*([-*+]|\d+\.)\s+/.test(ln)) {
      const items = [];
      const ordered = /^\s*\d+\./.test(ln);
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
        items.push(new Paragraph({
          children: runs(lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, "")),
          numbering: { reference: ordered ? "md-number" : "md-bullet", level: 0 },
        }));
        i++;
      }
      blocks.push(...items);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(ln)) {
      blocks.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "CCCCCC" } }, children: [new TextRun("")] }));
      i++; continue;
    }

    if (/^\s*>\s?/.test(ln)) {
      const buf = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(new Paragraph({
        children: runs(buf.join(" "), { italics: true, color: "555555" }),
        indent: { left: 360 },
        border: { left: { style: BorderStyle.SINGLE, size: 12, color: "BBBBBB" } },
      }));
      continue;
    }

    const para = [];
    while (i < lines.length && lines[i].trim() && !/^\s*(#{1,6}\s|\||```|>|([-*+]|\d+\.)\s)/.test(lines[i])) {
      para.push(lines[i++]);
    }
    blocks.push(new Paragraph({ children: runs(para.join(" ")), spacing: { after: 120 } }));
  }
  return blocks;
}

const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith("--")));
const pos = args.filter((a) => !a.startsWith("--"));
const src = pos[0], dst = pos[1] || src.replace(/\.md$/i, "") + ".docx";
const titleIdx = args.indexOf("--title");
const title = titleIdx > -1 ? args[titleIdx + 1] : null;

if (!src || !fs.existsSync(src)) {
  console.error("usage: node md2docx.mjs in.md [out.docx] [--title \"标题\"]");
  process.exit(2);
}

const blocks = build(fs.readFileSync(src, "utf8"));
if (title) blocks.unshift(new Paragraph({ heading: HeadingLevel.TITLE, children: runs(title), alignment: AlignmentType.CENTER }));

const doc = new Document({
  styles: {
    default: {
      document: { run: { font: "Microsoft YaHei", size: 21 }, paragraph: { spacing: { line: 300 } } },
    },
  },
  numbering: {
    config: [
      { reference: "md-bullet", levels: [{ level: 0, format: "bullet", text: "\u2022",
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "md-number", levels: [{ level: 0, format: "decimal", text: "%1.",
        style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ],
  },
  sections: [{
    properties: {
      page: { size: { width: A4_W, height: 16838 },
        margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } },
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({ alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "888888" })] })],
      }),
    },
    children: blocks,
  }],
});

fs.mkdirSync(path.dirname(path.resolve(dst)), { recursive: true });
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(dst, buf);
  console.log(JSON.stringify({ ev: "ok", src, out: dst, bytes: buf.length, blocks: blocks.length }));
}).catch((e) => { console.error("FAIL: " + e.message); process.exit(1); });
