#!/usr/bin/env node
// md2pptx.mjs — Markdown → PowerPoint(.pptx)，纯 JS（npm pptxgenjs）
// 用法: node md2pptx.mjs in.md [out.pptx] [--theme "1F3864"]
import fs from "node:fs";
import path from "node:path";
import PptxGenJS from "pptxgenjs";

const args = process.argv.slice(2);
const pos = args.filter((a) => !a.startsWith("--"));
const ti = args.indexOf("--theme");
const accent = (ti > -1 ? args[ti + 1] : "1F3864").replace(/^#/, "");
const src = pos[0], dst = pos[1] || src.replace(/\.md$/i, "") + ".pptx";

if (!src || !fs.existsSync(src)) {
  console.error('usage: node md2pptx.mjs in.md [out.pptx] [--theme "1F3864"]');
  process.exit(2);
}

const strip = (s) => s.replace(/\*\*([^*]+)\*\*/g, "$1").replace(/`([^`]+)`/g, "$1")
  .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
const isRow = (l) => /^\s*\|/.test(l);
const isSep = (l) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l);

// 把 md 拆成 [{title, level, bullets[], tables[[..]]}]
const slides = [];
let cur = null;
for (const raw of fs.readFileSync(src, "utf8").replace(/\r\n?/g, "\n").split("\n")) {
  const ln = raw.trimEnd();
  const h = ln.match(/^(#{1,3})\s+(.*)$/);
  if (h) {
    if (h[1].length <= 2) {
      cur = { title: strip(h[2]), level: h[1].length, bullets: [], tables: [] };
      slides.push(cur);
    } else if (cur) cur.bullets.push(strip(h[2].replace(/^#+\s*/, "")) + "\u200b");
    continue;
  }
  if (!cur) { if (ln.trim()) { cur = { title: "", level: 1, bullets: [], tables: [] }; slides.push(cur); } else continue; }
  if (isRow(ln)) {
    if (isSep(ln)) continue;
    const cells = ln.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => strip(c.trim()));
    const last = cur.tables[cur.tables.length - 1];
    if (last && last.open) last.rows.push(cells); else cur.tables.push({ open: true, rows: [cells] });
    continue;
  }
  if (cur.tables.length) cur.tables[cur.tables.length - 1].open = false;
  if (/^\s*([-*+]|\d+\.)\s+/.test(ln)) cur.bullets.push(strip(ln.replace(/^\s*([-*+]|\d+\.)\s+/, "")));
  else if (ln.trim() && !/^\s*```/.test(ln) && !/^STATE|^REF/.test(ln.trim())) cur.bullets.push(strip(ln.trim()));
  if (cur.bullets.length > 40) cur.bullets = cur.bullets.slice(0, 40);
}

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";
pres.author = "cli-agent";
const cover = slides.length && slides[0].title && slides[0].level === 1 ? slides.shift() : null;

if (cover) {
  const s = pres.addSlide();
  s.background = { color: accent };
  s.addText(cover.title, { x: 0.8, y: 2.2, w: 11.7, h: 1.4, fontSize: 40, bold: true, color: "FFFFFF" });
  const sub = cover.bullets.slice(0, 3).join("\n");
  if (sub) s.addText(sub, { x: 0.85, y: 3.7, w: 11.5, h: 1.6, fontSize: 14, color: "D9E2F3", lineSpacingMultiple: 1.3 });
}

for (const sl of slides) {
  const pages = [];
  const chunks = [];
  for (let i = 0; i < sl.bullets.length; i += 7) chunks.push(sl.bullets.slice(i, i + 7));
  if (!chunks.length) chunks.push([]);
  chunks.forEach((group, k) => pages.push({ bullets: group, tables: k === 0 ? sl.tables : [], first: k === 0 }));
  for (const pg of pages) {
    const s = pres.addSlide();
    s.addShape("rect", { x: 0, y: 0, w: 13.33, h: 0.9, fill: { color: accent } });
    s.addText(sl.title || " ", { x: 0.5, y: 0.12, w: 12.3, h: 0.66, fontSize: 22, bold: true, color: "FFFFFF" });
    let y = 1.15;
    if (pg.bullets.length) {
      s.addText(pg.bullets.map((b) => ({ text: b, options: { bullet: true, breakLine: true } })),
        { x: 0.55, y, w: 12.2, h: Math.min(3.2, 0.42 * pg.bullets.length + 0.3), fontSize: 14, color: "222222", valign: "top" });
      y += Math.min(3.6, 0.42 * pg.bullets.length + 0.5);
    }
    for (const t of pg.tables) {
      const rows = t.rows.slice(0, 9).map((r) => r.map((c) => ({ text: c, options: {} })));
      if (!rows.length) continue;
      s.addTable(rows, { x: 0.55, y, w: 12.2, fontSize: 10, border: { pt: 0.5, color: "BFBFBF" },
        fill: { color: "FFFFFF" }, color: "222222", autoPage: false });
      y += 0.36 * rows.length + 0.25;
    }
  }
}

await pres.writeFile({ fileName: dst });
console.log(JSON.stringify({ ev: "ok", src, out: dst, slides: slides.length + (cover ? 1 : 0) }));
