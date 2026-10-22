#!/usr/bin/env python3
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path

BASE = Path.home() / ".cache/videowatch"
CTX = Path.home() / ".config/term_agent/skill/ctxinject.py"
URL = re.compile(r"^https?://", re.I)
VEXT = (".mp4", ".mkv", ".webm", ".mov", ".flv", ".m4v", ".avi")

def sh(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("失败(%d) %s\n%s" % (r.returncode, " ".join(cmd)[:200], (r.stderr or r.stdout).strip()[:900]))
    return r.stdout

def need(b, hint):
    if shutil.which(b) is None:
        sys.exit("缺 %s → %s" % (b, hint))

def wdir(src):
    key = src if URL.match(src) else "%s|%d" % (src, os.path.getsize(src))
    return BASE / hashlib.sha1(key.encode()).hexdigest()[:10]

def fetch(url, d):
    need("yt-dlp", "pip install yt-dlp")
    d.mkdir(parents=True, exist_ok=True)
    got = sorted([p for p in d.iterdir() if p.suffix.lower() in VEXT and p.stat().st_size > 10240],
                 key=lambda p: -p.stat().st_size)
    if got:
        print("复用已下载 %s (%.1fMB)" % (got[0].name, got[0].stat().st_size / 1048576))
        return got[0]
    print("下载中 …")
    sh(["yt-dlp", "--no-playlist", "-f", "bv*[height<=720]+ba/b[height<=720]/b",
        "-o", str(d / "src.%(ext)s"), url])
    got = sorted([p for p in d.iterdir() if p.suffix.lower() in VEXT], key=lambda p: -p.stat().st_size)
    if not got: sys.exit("下载完成但没找到视频文件")
    print("已下载 %s (%.1fMB)" % (got[0].name, got[0].stat().st_size / 1048576))
    return got[0]

def probe(src):
    need("ffprobe", "pkg install ffmpeg")
    j = json.loads(sh(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=width,height,duration:format=duration",
                       "-of", "json", str(src)]))
    st = (j.get("streams") or [{}])[0]
    w, h = int(st.get("width") or 0), int(st.get("height") or 0)
    if w < 2 or h < 2: sys.exit("没有视频流（纯音频/损坏）")
    dur = float(st.get("duration") or (j.get("format") or {}).get("duration") or 0)
    return w, h, dur

def extract(src, frames, long, maxsec):
    need("ffmpeg", "pkg install ffmpeg")
    w, h, dur = probe(src)
    if dur > maxsec:
        sys.exit("时长 %.0fs > --max-sec %d（1fps 会出 %.0f 帧），确认要跑就显式调大" % (dur, maxsec, dur))
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

def est(p, long=None):
    try:
        sys.path.insert(0, str(Path.home() / ".local/bin/term_agent"))
        from term_agent import _shrink
        if long:
            from PIL import Image
            im = Image.open(p).convert("RGB")
            w, h = im.size
            k = min(1.0, long / max(w, h))
            if k < 1.0: im = im.resize((max(1, int(w * k)), max(1, int(h * k))))
            t = BASE / "est.jpg"
            im.save(t, "JPEG", quality=88, optimize=True)
            b = _shrink(str(t))
        else:
            b = _shrink(str(p))
        import base64
        return len(base64.b64encode(b)) // 4 if b else None
    except Exception:
        return None

def fit(items, budget, long):
    cand = [q for q in (est(x["p"]) for x in items) if q]
    per = max(cand) if cand else None
    if not per or not budget or per * len(items) <= budget: return items, long, per
    from PIL import Image
    for L in (480, 360, 300, 240, 180):
        if L >= long: continue
        q = est(items[0]["p"], L)
        if q and q * len(items) <= budget: return items, L, q
    q = est(items[0]["p"], 180) or per
    n = max(1, budget // q)
    if n < len(items):
        idx = [round(i * (len(items) - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]
        items = [items[i] for i in sorted(set(idx))]
    return items, 180, q

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
    cmd = [sys.executable, str(CTX), "inject"]
    if pid: cmd += ["--pid", str(pid)]
    if wake: cmd += ["-w"]
    cmd += [text] + [x["p"] for x in items]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    print((r.stdout or r.stderr).strip())
    m = re.search(r"已落地[^{]*(\{.*\})", r.stdout)
    if not m:
        print("排队中（宿主 tool_calls 未收尾），看守会自动补插：%s" % (BASE.parent.parent / "ctxinject" / ("watch_%d.log" % pid) if pid else "见 ~/.cache/ctxinject/watch_*.log"))
        return 3
    d = json.loads(m.group(1))
    got = sum(1 for x in (d.get("content") or []) if x and x[0] == "image_url")
    print("自检 图 %d/%d 落地%s" % (got, len(items), "" if got == len(items) else " ← 不符"))
    return 0 if got == len(items) else 4

def main():
    ap = argparse.ArgumentParser(prog="videowatch")
    ap.add_argument("src", help="本地视频路径 或 http(s) 链接")
    ap.add_argument("--thr", type=float, default=6.0, help="灰度均差阈值 0-255，默认 6")
    ap.add_argument("--max-frames", type=int, default=16)
    ap.add_argument("--budget", type=int, default=150000, help="注入 token 预算，默认 150k（0=不限）")
    ap.add_argument("--long", type=int, default=480, help="帧长边像素，默认 480")
    ap.add_argument("--max-sec", type=int, default=900, help="时长上限，默认 900s")
    ap.add_argument("--no-inject", action="store_true", help="只出图，不注入宿主")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--quiet", action="store_true", help="不唤醒宿主（排队注入）")
    a = ap.parse_args()

    src, d = a.src, wdir(a.src if URL.match(a.src) else os.path.abspath(a.src))
    if URL.match(src):
        vid = fetch(src, d)
    else:
        vid = Path(src).expanduser()
        if not vid.is_file(): sys.exit("无此文件 %s" % src)
    w, h, dur, twth, n1, fps = extract(vid, d / "f1", a.long, a.max_sec)
    keep, sc, cut = detect(d / "f1", a.thr, a.max_frames)
    pre = organize(d / "f1", keep, d / "out", fps=fps)
    pre, long_out, per = fit(pre, a.budget, min(a.long, max(twth)))
    items = pre if long_out == min(a.long, max(twth)) else organize(d / "f1", [x["i"] for x in pre], d / "out", long_out, fps)
    cut += len(keep) - len(items)
    print("源 %dx%d %.1fs → %gfps %d帧 @%dx%d → 关键帧 %d（阈值%.1f 压缩%.0f%%%s）"
          % (w, h, dur, fps, n1, twth[0], twth[1], len(items), a.thr,
             100.0 * (1 - len(items) / max(1, n1)), "，超限裁掉%d" % cut if cut else ""))
    if per: print("预算 %dk → 每帧约 %.1fk token × %d = %.1fk（长边 %d）"
                  % (a.budget // 1000, per / 1000.0, len(items), per * len(items) / 1000.0, long_out))
    from PIL import Image, ImageStat
    means = {x["p"]: ImageStat.Stat(Image.open(x["p"]).convert("L")).mean[0] for x in items}
    for x in items: print("  %6.1fs mean%5.1f %s" % (x["t"] / 1000.0, means[x["p"]], x["p"]))
    json.dump({"src": str(vid), "size": [w, h], "dur": dur, "thr": a.thr,
               "frames": items}, open(d / "manifest.json", "w"), ensure_ascii=False, indent=1)
    if a.no_inject: return 0
    if max(means.values()) < 2.0:
        print("关键帧全为空场（最亮帧灰度均值 %.2f < 2）→ 不注入：调 --thr 或按秒手工定点抽帧"
              % max(means.values()))
        return 5
    return inject(items, "视频%ds %dx%d 关键帧" % (dur, w, h), not a.quiet, a.pid)

if __name__ == "__main__":
    sys.exit(main())
