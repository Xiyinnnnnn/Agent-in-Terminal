#!/usr/bin/env python3
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

BASE = Path.home() / ".cache/videowatch"
CTX = Path.home() / ".config/term_agent/skill/ctxinject.py"
URL = re.compile(r"^https?://", re.I)
VEXT = (".mp4", ".mkv", ".webm", ".mov", ".flv", ".m4v", ".avi")

def emit(d):
    print(json.dumps(d, ensure_ascii=False, separators=(",", ":")), flush=True)

def die(m, code=1):
    print(json.dumps({"ev": "err", "msg": m}, ensure_ascii=False), file=sys.stderr, flush=True)
    sys.exit(code)

def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("cmd_fail:%d:%s" % (r.returncode, " ".join(cmd)[:160] + "|" + (r.stderr or r.stdout).strip()[:400]))
    return r.stdout

def need(b, hint):
    if shutil.which(b) is None:
        die("missing_bin:%s:%s" % (b, hint))

def wdir(src):
    key = src if URL.match(src) else "%s|%d" % (src, os.path.getsize(src))
    return BASE / hashlib.sha1(key.encode()).hexdigest()[:10]

def fetch(url, d):
    need("yt-dlp", "pip install yt-dlp")
    d.mkdir(parents=True, exist_ok=True)
    got = sorted([p for p in d.iterdir() if p.suffix.lower() in VEXT and p.stat().st_size > 10240],
                 key=lambda p: -p.stat().st_size)
    if got:
        emit({"ev": "fetch_reuse", "name": got[0].name, "mb": round(got[0].stat().st_size / 1048576, 1)})
        return got[0]
    emit({"ev": "fetching", "url": url})
    sh(["yt-dlp", "--no-playlist", "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "-o", str(d / "src.%(ext)s"), url])
    got = sorted([p for p in d.iterdir() if p.suffix.lower() in VEXT], key=lambda p: -p.stat().st_size)
    if not got: die("no_video_after_download")
    emit({"ev": "fetch_done", "name": got[0].name, "mb": round(got[0].stat().st_size / 1048576, 1)})
    return got[0]

def probe(src):
    need("ffprobe", "pkg install ffmpeg")
    j = json.loads(sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=width,height,duration:format=duration",
                       "-of", "json", str(src)]))
    st = (j.get("streams") or [{}])[0]
    w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    if w < 2 or h < 2: die("no_video_stream")
    dur = float(st.get("duration") or (j.get("format") or {}).get("duration") or 0)
    return w, h, dur

def extract(src, frames, long, maxsec):
    need("ffmpeg", "pkg install ffmpeg")
    w, h, dur = probe(src)
    if dur > maxsec:
        die("too_long:%.0fs>max_sec:%d:est_frames@1fps:%.0f" % (dur, maxsec, dur))
    k = min(1.0, long / max(w, h))
    tw, th = max(2, int(w * k) // 2 * 2), max(2, int(h * k) // 2 * 2)
    frames.mkdir(parents=True, exist_ok=True)
    for f in frames.glob("*.jpg"): f.unlink()
    fps = 5 if dur < 30 else (2 if dur < 120 else 1)
    sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-an",
        "-vf", "fps=%g,scale=%d:%d" % (fps, tw, th), "-q:v", "4", str(frames / "f%05d.jpg")])
    n = len(list(frames.glob("f*.jpg")))
    return w, h, dur, (tw, th), n, fps

def detect(frames, thr, maxf):
    from PIL import Image, ImageChops, ImageStat
    fs = sorted(frames.glob("f*.jpg"))
    keep, sc, last = [], [], None
    for i, p in enumerate(fs):
        g = Image.open(p).convert("L").resize((64, 36), Image.BILINEAR)
        s = 255.0 if last is None else ImageStat.Stat(ImageChops.difference(g, last)).mean[0]
        sc.append((i, s))
        if last is None or s >= thr:
            keep.append(i); last = g
    cut = 0
    if len(keep) > maxf:
        pool = {i for i, _ in sorted(sc, key=lambda x: -x[1])[:maxf]}
        cut = len(keep) - maxf
        keep = sorted(i for i in keep if i in pool)
    return keep, sc, cut

def organize(frames, keep, out, long=0, fps=1):
    out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*.jpg"): f.unlink()
    items = []
    for n, i in enumerate(keep, 1):
        src, dst = frames / ("f%05d.jpg" % (i + 1)), out / ("t%06d_i%02d.jpg" % (int(i * 1000 / fps), n))
        if long:
            from PIL import Image
            im = Image.open(src).convert("RGB")
            w, h = im.size
            k = min(1.0, long / max(w, h))
            if k < 1.0: im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
            im.save(dst, "JPEG", quality=88, optimize=True)
        else:
            shutil.copyfile(src, dst)
        items.append({"t": int(i * 1000 / fps), "sec": round(i / float(fps), 2), "i": i, "n": n, "p": str(dst)})
    return items

def inject(items, header, wake, pid):
    text = "%s | %d帧 %s" % (header, len(items), " ".join("%.1fs" % (x["t"] / 1000.0) for x in items))
    cmd = [sys.executable, str(CTX), "inject", "--pid", str(pid)]
    if wake: cmd += ["-w"]
    cmd += [text] + [x["p"] for x in items]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    ev, d = None, None
    for ln in (r.stdout or "").splitlines():
        try: o = json.loads(ln)
        except ValueError: continue
        if o.get("ev") == "ok": ev, d = "ok", o.get("d") or {}
        elif o.get("ev") == "defer": ev = "defer"
    if ev == "ok":
        got = sum(1 for x in (d.get("content") or []) if x and x[0] == "image_url")
        emit({"ev": "inject_ok", "got": got, "want": len(items), "hist_len": d.get("hist_len")})
        return 0 if got == len(items) else 4
    if ev == "defer":
        emit({"ev": "inject_defer", "log": str(Path.home() / ".cache/ctxinject" / ("watch_%d.log" % pid))})
        return 3
    emit({"ev": "inject_err", "rc": r.returncode, "stderr": (r.stderr or "").strip()[:400]})
    return 1

SUBEXT = (".vtt", ".srt", ".ass", ".ssa")
DEF_LANGS = "zh-Hans,zh-CN,zh,en"
EXIT_NO_SUBS = 6


def ts2s(v):
    m = re.search(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})", v)
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000.0


def fmt_ts(s):
    s = int(s or 0)
    if s < 3600:
        return "%02d:%02d" % (s // 60, s % 60)
    return "%d:%02d:%02d" % (s // 3600, s // 60 % 60, s % 60)


ENT = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}


def clean_line(l):
    l = re.sub(r"<[^>]*>", "", l)
    l = re.sub(r"\{\\[^}]*\}", "", l)
    for k, v in ENT.items():
        l = l.replace(k, v)
    return re.sub(r"\s+", " ", l).strip()


def parse_timed(txt):
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    cues = []
    for block in re.split(r"\n\s*\n", txt):
        lines = [x for x in block.split("\n") if x.strip()]
        i = next((k for k, x in enumerate(lines) if "-->" in x), None)
        if i is None:
            continue
        head, _, tail = lines[i].partition("-->")
        st, en = ts2s(head), ts2s(tail)
        if st is None:
            continue
        body = [clean_line(x) for x in lines[i + 1:]]
        body = [x for x in body if x]
        if not body:
            continue
        cues.append([st, st if en is None else en, " ".join(body)])
    return cues


def dedupe(cues):
    out = []
    for st, en, text in cues:
        if out and st == out[-1][0]:
            if len(text) > len(out[-1][2]):
                out[-1][2] = text
            out[-1][1] = max(out[-1][1], en)
            continue
        if out:
            pt = out[-1][2]
            if text == pt or text in pt:
                continue
            if pt in text:
                out.pop()
        out.append([st, en, text])
    return out


def safe(n):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", n).strip("_") or "und"


def write_md(out, name, lang, kind, cues):
    end = max([c[1] for c in cues] or [0])
    hdr = ["# 字幕 %s" % name, "",
           "| 项 | 值 |", "| --- | --- |",
           "| 语言 | %s |" % (lang or "?"),
           "| 类型 | %s |" % kind,
           "| 时长 | %s |" % fmt_ts(end),
           "| 行数 | %d |" % len(cues), ""]
    body = ["[%s] %s" % (fmt_ts(st), t.replace("|", "\\|")) for st, _, t in cues]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(hdr + body) + "\n", encoding="utf-8")
    return body


def subs_local(vid, outdir):
    need("ffprobe", "pkg install ffmpeg")
    outdir.mkdir(parents=True, exist_ok=True)
    j = json.loads(sh(["ffprobe", "-v", "error", "-select_streams", "s",
                       "-show_entries", "stream=index:stream_tags=language",
                       "-of", "json", str(vid)]))
    got = []
    streams = j.get("streams") or []
    for k, st in enumerate(streams):
        lang = ((st.get("tags") or {}).get("language") or "").strip()
        if not lang or lang == "und":
            lang = "und" if len(streams) == 1 else "und%d" % k
        need("ffmpeg", "pkg install ffmpeg")
        dst = outdir / (safe(lang) + ".srt")
        sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(vid),
            "-map", "0:s:%d" % k, "-c:s", "srt", str(dst)])
        got.append((lang, dst, "embedded"))
    for p in sorted(vid.parent.glob(vid.stem + ".*")):
        if p.suffix.lower() not in SUBEXT or not p.is_file():
            continue
        lang = p.name[len(vid.stem) + 1: -len(p.suffix)] or "und"
        if p.suffix.lower() in (".ass", ".ssa"):
            need("ffmpeg", "pkg install ffmpeg")
            dst = outdir / (safe(lang) + ".srt")
            sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(p), str(dst)])
        else:
            dst = outdir / (safe(lang) + p.suffix.lower())
            shutil.copyfile(p, dst)
        got.append((lang, dst, "external." + p.suffix.lower()[1:]))
    return got


def subs_url(url, d, langs):
    need("yt-dlp", "pip install yt-dlp")
    sd = d / "subs_raw"
    sd.mkdir(parents=True, exist_ok=True)
    for f in sd.iterdir():
        if f.is_file():
            f.unlink()
    cmd = ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
           "--sub-langs", langs, "--sub-format", "vtt/srt/best",
           "--no-playlist", "-o", str(sd / "src.%(ext)s"), url]
    r = subprocess.run(cmd, capture_output=True, text=True)
    log = (r.stdout or "") + (r.stderr or "")
    files = [p for p in sd.iterdir() if p.suffix.lower() in (".vtt", ".srt")]
    if not files:
        emit({"ev": "no_subs", "src": url, "log": log.strip()[-200:]})
        sys.exit(EXIT_NO_SUBS)
    kind = "manual" if "Writing video subtitles" in log else (
        "auto" if "automatic captions" in log else "?")
    return [(p.name[len("src."):-len(p.suffix)], p, kind) for p in sorted(files)]


def subs_main(argv):
    ap = argparse.ArgumentParser(prog="videowatch subs")
    ap.add_argument("src", help="本地视频路径 或 http(s) 链接")
    ap.add_argument("--langs", default=DEF_LANGS, help="yt-dlp --sub-langs，默认 " + DEF_LANGS)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if URL.match(a.src):
        d = wdir(a.src)
        found = subs_url(a.src, d, a.langs)
    else:
        vid = Path(a.src).expanduser()
        if not vid.is_file():
            die("no_such_file:%s" % a.src)
        d = wdir(str(vid.resolve()))
        found = subs_local(vid, d / "subs")
        if not found:
            emit({"ev": "no_subs", "src": str(vid)})
            sys.exit(EXIT_NO_SUBS)
    n = 0
    for lang, p, kind in found:
        cues = dedupe(parse_timed(p.read_text(encoding="utf-8", errors="replace")))
        if not cues:
            continue
        md = d / "subs" / (safe(lang) + ".md")
        body = write_md(md, Path(a.src).name, lang, kind, cues)
        emit({"ev": "subs", "path": str(md), "lang": lang, "kind": kind,
              "lines": len(cues), "sec": round(cues[-1][1], 1), "head": body[:6]})
        n += 1
    if n == 0:
        emit({"ev": "no_subs", "src": a.src, "raw": len(found)})
        sys.exit(EXIT_NO_SUBS)
    emit({"ev": "subs_done", "n": n, "dir": str(d / "subs")})
    return 0

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "subs":
        return subs_main(sys.argv[2:])
    ap = argparse.ArgumentParser(prog="videowatch")
    ap.add_argument("src", help="本地视频路径 或 http(s) 链接")
    ap.add_argument("--thr", type=float, default=6.0, help="灰度均差阈值 0-255，默认 6")
    ap.add_argument("--max-frames", type=int, default=16)
    ap.add_argument("--long", type=int, default=480, help="帧长边像素，默认 480")
    ap.add_argument("--max-sec", type=int, default=900, help="时长上限，默认 900s")
    ap.add_argument("--no-inject", action="store_true", help="只出图，不注入宿主")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--quiet", action="store_true", help="不唤醒宿主（排队注入）")
    a = ap.parse_args()
    if not a.no_inject and not a.pid: die("need_pid:--pid <host pid>")

    src, d = a.src, wdir(a.src if URL.match(a.src) else os.path.abspath(a.src))
    if URL.match(src):
        vid = fetch(src, d)
    else:
        vid = Path(src).expanduser()
        if not vid.is_file(): die("no_such_file:%s" % src)
    w, h, dur, twth, n1, fps = extract(vid, d / "f1", a.long, a.max_sec)
    keep, sc, cut = detect(d / "f1", a.thr, a.max_frames)
    items = organize(d / "f1", keep, d / "out", fps=fps)
    long_out = min(a.long, max(twth))
    from PIL import Image, ImageStat
    means = {x["p"]: ImageStat.Stat(Image.open(x["p"]).convert("L")).mean[0] for x in items}
    json.dump({"src": str(vid), "size": [w, h], "dur": dur, "thr": a.thr,
               "frames": items}, open(d / "manifest.json", "w"), ensure_ascii=False, indent=1)
    emit({"ev": "plan", "src": str(vid), "size": [w, h], "dur": round(dur, 2), "fps": fps,
          "all_frames": n1, "frame_px": [twth[0], twth[1]], "keep": len(items), "thr": a.thr,
          "cut": cut, "long": long_out,
          "frames": [{"sec": x["sec"], "p": x["p"], "mean": round(means[x["p"]], 1)} for x in items]})
    if a.no_inject: return 0
    if max(means.values()) < 2.0:
        emit({"ev": "empty", "maxmean": round(max(means.values()), 2)})
        return 5
    return inject(items, "视频%ds %dx%d 关键帧" % (dur, w, h), not a.quiet, a.pid)

if __name__ == "__main__":
    sys.exit(main())
