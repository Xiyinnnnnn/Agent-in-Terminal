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

def main():
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
