#!/usr/bin/env python3
import hashlib, os, struct, subprocess, sys, zlib
from operator import add

MAGIC = b"\x89PNG\r\n\x1a\n"
MAXLONG = int(os.environ.get("TA_IMG_MAX") or 1000)
LEV = int(os.environ.get("TA_IMG_LEV") or 6)
CACHE = os.path.expanduser("~/.cache/term_agent/imgsmall")

def _chunk(t, d):
    c = t + d
    return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

def _unfilter(raw, w, h, ch):
    stride = w * ch
    out = bytearray(stride * h); prev = bytes(stride); pos = 0
    M7 = int.from_bytes(b"\x7f" * stride, "little")
    M1 = int.from_bytes(b"\x80" * stride, "little")
    ONE = int.from_bytes(b"\x01" * stride, "little")
    for y in range(h):
        b = y * (stride + 1); f = raw[b]; line = raw[b + 1:b + 1 + stride]
        if f == 0:
            cur = line
        elif f == 2:
            A = int.from_bytes(line, "little"); B = int.from_bytes(prev, "little")
            S = (A & M7) + (B & M7)
            C = ((A & M1) >> 7) + ((B & M1) >> 7)
            cur = ((S & M7) | ((((S & M1) >> 7) ^ (C & ONE)) << 7)).to_bytes(stride, "little")
        elif f == 1:
            c = bytearray(line)
            for k in range(ch, stride): c[k] = (c[k] + c[k - ch]) & 255
            cur = bytes(c)
        elif f == 3:
            c = bytearray(stride); pv = prev
            for k in range(stride):
                l = c[k - ch] if k >= ch else 0
                c[k] = (line[k] + ((l + pv[k]) >> 1)) & 255
            cur = bytes(c)
        else:
            ul = bytes(ch) + prev[:-ch] if ch < stride else bytes(stride)
            c = bytearray(line); pv = prev
            for k in range(ch):
                c[k] = (c[k] + pv[k]) & 255
            for k in range(ch, stride):
                a = c[k - ch]; b2 = pv[k]; d = ul[k]
                pa = b2 - d; pa = -pa if pa < 0 else pa
                pb = a - d; pb = -pb if pb < 0 else pb
                pc = a + b2 - 2 * d; pc = -pc if pc < 0 else pc
                pr = a if pa <= pb and pa <= pc else (b2 if pb <= pc else d)
                c[k] = (c[k] + pr) & 255
            cur = bytes(c)
        out[pos:pos + stride] = cur; prev = cur; pos += stride
    return out

def decode_png(d):
    if d[:8] != MAGIC: return None
    i = 8; idat = []; w = h = bd = ct = inter = None
    while i + 12 <= len(d):
        ln = struct.unpack(">I", d[i:i + 4])[0]; t = d[i + 4:i + 8]; b = d[i + 8:i + 8 + ln]; i += 12 + ln
        if t == b"IHDR": w, h, bd, ct, _, _, inter = struct.unpack(">IIBBBBB", b)
        elif t == b"IDAT": idat.append(b)
        elif t == b"IEND": break
    if bd != 8 or inter or ct not in (2, 6) or not idat: return None
    ch = 3 if ct == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    if len(raw) != h * (w * ch + 1): return None
    return w, h, ch, _unfilter(raw, w, h, ch)

def _scale(buf, w, h, ch, long):
    k = max(1, -(-max(w, h) // long))
    if k == 1: return w, h, bytes(buf)
    stride = w * ch; T = bytes(i // k for i in range(256)); ow = w // k; oh = h // k
    if ow < 2 or oh < 2: return w, h, bytes(buf)
    out = []
    for oy in range(oh):
        acc = None
        for yy in range(oy * k, oy * k + k):
            row = bytes(buf[yy * stride:(yy + 1) * stride]).translate(T)
            acc = row if acc is None else bytes(map(add, acc, row))
        out.append(b"".join(acc[x * ch * k:x * ch * k + ch] for x in range(ow)))
    return ow, oh, b"".join(out)

def encode_pal(buf, w, h, ch, lev=None):
    lev = lev or LEV; s = 256 // lev
    t1 = bytes(i // s for i in range(256))
    tr = bytes(((i * lev * lev) & 255) if i < lev else 0 for i in range(256))
    tg = bytes(((i * lev) & 255) if i < lev else 0 for i in range(256))
    r = buf[0::ch].translate(t1).translate(tr)
    g = buf[1::ch].translate(t1).translate(tg)
    b = buf[2::ch].translate(t1)
    idx = bytes(map(add, bytes(map(add, r, g)), b))
    pal = bytearray()
    for i in range(lev):
        for j in range(lev):
            for k in range(lev): pal += bytes((i * s, j * s, k * s))
    raw = b"".join(b"\x00" + idx[y * w:(y + 1) * w] for y in range(h))
    return MAGIC + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)) + _chunk(b"PLTE", bytes(pal)) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")

def _png_raw(buf, w, h, ch):
    ct = 2 if ch == 3 else 6
    raw = b"".join(b"\x00" + bytes(buf[y * w * ch:(y + 1) * w * ch]) for y in range(h))
    return MAGIC + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(raw, 6)) + _chunk(b"IEND", b"")

def shrink(data, long=None, lev=None):
    long = long or MAXLONG
    im = decode_png(data)
    if not im: return None
    w, h, ch, buf = im
    if ch == 4 and not all(x == 255 for x in buf[3::4]):
        w2, h2, b2 = _scale(buf, w, h, ch, long)
        return _png_raw(b2, w2, h2, 4)
    w2, h2, b2 = _scale(buf, w, h, ch, long)
    return encode_pal(b2, w2, h2, ch, lev)

def shrink_raw(raw, long=None, lev=None):
    if len(raw) < 16: return None
    w, h, fmt, cs = struct.unpack("<IIII", raw[:16])
    if w < 2 or h < 2 or len(raw) < 16 + w * h * 4: return None
    w2, h2, b2 = _scale(memoryview(raw)[16:], w, h, 4, long or MAXLONG)
    return encode_pal(b2, w2, h2, 4, lev)

def shrink_file(path, long=None, lev=None):
    try:
        st = os.stat(path)
        key = hashlib.sha1(("%s|%d|%d|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime), long or MAXLONG, lev or LEV)).encode()).hexdigest()[:20]
        c = os.path.join(CACHE, key + ".png")
        if os.path.isfile(c): return open(c, "rb").read()
        z = shrink(open(path, "rb").read(), long, lev)
        if z:
            os.makedirs(CACHE, exist_ok=True)
            open(c, "wb").write(z)
        return z
    except Exception:
        return None

def shot(dev=None, long=None, timeout=90):
    raw = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=20).stdout
    ds = [l.split()[0] for l in raw.splitlines()[1:] if len(l.split()) >= 2 and l.split()[1] == "device"]
    if not ds: raise RuntimeError("无在线 adb 设备")
    dev = dev or ("127.0.0.1:7957" if "127.0.0.1:7957" in ds else ds[0])
    b = subprocess.run(["adb", "-s", dev, "exec-out", "screencap"], capture_output=True, timeout=timeout).stdout
    if not b: raise RuntimeError("screencap 无输出")
    return shrink_raw(b, long) if b[:8] != MAGIC else (shrink(b, long) or b)

def main():
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print("imgshrink.py shot [out.png] [长边]\nimgshrink.py file in.png [out.png] [长边] [色阶]\nimgshrink.py bench in.png")
        return 0
    if a[0] == "bench":
        import time
        d = open(a[1], "rb").read()
        t0 = time.monotonic(); im = decode_png(d); t1 = time.monotonic()
        print("decode %dx%d ch=%d  %.2fs" % (im[0], im[1], im[2], t1 - t0) if im else "decode 失败")
        t0 = time.monotonic(); z = shrink(d); t1 = time.monotonic()
        print("shrink %d B -> %d B  %.2fs" % (len(d), len(z), t1 - t0)); return 0
    if a[0] == "shot":
        out = a[1] if len(a) > 1 else os.path.expanduser("~/.cache/ctxinject/shot_small.png")
        long = int(a[2]) if len(a) > 2 else None
        z = shot(long=long); open(out, "wb").write(z); print("%s %d B" % (out, len(z))); return 0
    src = a[1] if len(a) > 1 else a[0]
    dst = a[2] if len(a) > 2 else src.rsplit(".", 1)[0] + ".small.png"
    long = int(a[3]) if len(a) > 3 else None
    lev = int(a[4]) if len(a) > 4 else None
    d = open(src, "rb").read(); z = shrink(d, long, lev)
    if not z: print("跳过（不支持的格式）"); return 1
    open(dst, "wb").write(z)
    print("%s -> %s  %d -> %d B  %.1f%%" % (src, dst, len(d), len(z), 100.0 * len(z) / len(d)))
    return 0

if __name__ == "__main__":
    sys.exit(main())
