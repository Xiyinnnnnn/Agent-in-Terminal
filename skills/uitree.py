#!/usr/bin/env python3
"""uitree.py — Android 界面树：dump → 剪枝 → 确定性可点集 → 动作 → 校验
用法见同目录 00-图形界面操作.md
退出码 0 ok ｜ 2 设备或 dump 失败 ｜ 3 UiAutomation 被占 ｜ 4 树为空 ｜ 5 参数或能力不支持 ｜ 6 目标未找到
"""
import argparse, hashlib, json, os, re, subprocess, sys, time
from xml.etree import ElementTree as ET
os.environ.setdefault("TMPDIR", os.path.expanduser("~/.cache"))
BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
MIN_AREA = 64
SIGNAL_CLS = {"EditText", "Button", "CheckBox", "Switch", "RadioButton", "ImageButton", "Tab", "SeekBar", "ToggleButton", "Spinner"}
STEP = 100
def die(msg, code):
    print(msg, file=sys.stderr)
    sys.exit(code)
def adb(args, serial=None, timeout=90, binary=False):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    try:
        return subprocess.run(cmd, capture_output=True, text=not binary, timeout=timeout)
    except subprocess.TimeoutExpired:
        die("[adb] timeout %ss: %s" % (timeout, " ".join(args)), 2)
def dump_raw(serial=None):
    r = adb(["exec-out", "uiautomator", "dump", "--compressed", "/dev/tty"], serial=serial)
    txt = (r.stdout or "") + (r.stderr or "")
    if "already registered" in txt or "Killed" in txt or r.returncode == 137:
        die("[dump] UiAutomation 被占/被杀 (exit 3)：重启手机或 force-stop 占用者；先用 shot+grid+roi 兜底\n" + txt.strip()[:200], 3)
    i, j = txt.find("<hierarchy"), txt.rfind("</hierarchy>")
    if i < 0 or j < 0:
        die("[dump] rc=%s 无 hierarchy (exit 2)：%s" % (r.returncode, txt.strip()[:200]), 2)
    return txt[i:j + len("</hierarchy>")]
def load(path=None, serial=None):
    txt = open(path, encoding="utf-8").read() if path else dump_raw(serial)
    i, j = txt.find("<hierarchy"), txt.rfind("</hierarchy>")
    if i < 0 or j < 0:
        die("[parse] 无 hierarchy (exit 4)", 4)
    return ET.fromstring(txt[i:j + len("</hierarchy>")])
def walk(el, parent, path, nodes):
    m = BOUNDS.search(el.get("bounds", ""))
    b = tuple(int(x) for x in m.groups()) if m else None
    i = len(nodes)
    nodes.append({"a": el.attrib, "p": parent, "k": [], "path": path, "b": b})
    if parent is not None:
        nodes[parent]["k"].append(i)
    for n, ch in enumerate(el):
        walk(ch, i, "%s.%d" % (path, n), nodes)
def parse_tree(root):
    nodes = []
    walk(root, None, "0", nodes)
    return nodes
def screen_of(nodes):
    for n in nodes:
        if n["p"] == 0 and n["b"]:
            return (n["b"][2], n["b"][3])
    xs = [n["b"][2] for n in nodes if n["b"]]
    ys = [n["b"][3] for n in nodes if n["b"]]
    return (max(xs + [0]), max(ys + [0]))
def cls_of(n):
    return n["a"].get("class", "").split(".")[-1]
def label_of(n):
    return (n["a"].get("text", "").strip() or n["a"].get("content-desc", "").strip())
def is_click(n):
    a = n["a"]
    return a.get("clickable") == "true" or a.get("long-clickable") == "true" or a.get("checkable") == "true"
def is_scroll(n):
    return n["a"].get("scrollable") == "true"
def is_signal(n):
    return bool(label_of(n)) or is_click(n) or is_scroll(n) or cls_of(n) in SIGNAL_CLS
def role_of(n):
    if is_scroll(n):
        return "scroll"
    c = cls_of(n)
    if c == "EditText":
        return "edit"
    return "click" if is_click(n) else "text"
def usable(n, screen):
    b = n["b"]
    if not b:
        return None
    x1, y1, x2, y2 = b
    if x2 - x1 <= 0 or y2 - y1 <= 0 or (x2 - x1) * (y2 - y1) < MIN_AREA:
        return None
    W, H = screen
    c = (max(x1, 0), max(y1, 0), min(x2, W), min(y2, H))
    if c[2] - c[0] <= 0 or c[3] - c[1] <= 0:
        return None
    return c
def mk(nodes, i, b, label, flags):
    n = nodes[i]
    a = n["a"]
    return {"src": i, "role": role_of(n), "label": label, "rid": a.get("resource-id", ""),
            "cls": cls_of(n), "bounds": b, "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2),
            "flags": flags, "text": a.get("text", "").strip(), "desc": a.get("content-desc", ""),
            "path": n["path"], "pkg": a.get("package", "")}
def hashid(nodes, e):
    a = nodes[e["src"]]["a"]
    s = "|".join([a.get("package", ""), a.get("class", ""), a.get("resource-id", ""),
                  a.get("text", "").strip(), a.get("content-desc", "").strip(), nodes[e["src"]]["path"]])
    return hashlib.sha1(s.encode()).hexdigest()[:8]
def prune(nodes, screen, keep_all=False):
    box = {i: usable(n, screen) for i, n in enumerate(nodes)}
    out = []
    if keep_all:
        for i, n in enumerate(nodes):
            if box[i]:
                out.append(mk(nodes, i, box[i], label_of(n), "all"))
    else:
        anc = {}
        for i, n in enumerate(nodes):
            p, a = n["p"], None
            while p is not None:
                if is_click(nodes[p]) and box[p]:
                    a = p
                    break
                p = nodes[p]["p"]
            anc[i] = a
        groups = {}
        for i, n in enumerate(nodes):
            if box[i] and is_signal(n) and anc[i] is not None:
                groups.setdefault(anc[i], []).append(i)
        done = set()
        for a, kids in groups.items():
            an = nodes[a]
            al = label_of(an)
            labs = {label_of(nodes[k]) for k in kids if label_of(nodes[k])}
            if len(kids) >= 2 and not is_scroll(an) and not al and len(labs) >= 2:
                for k in kids:
                    out.append(mk(nodes, k, box[k], label_of(nodes[k]), "parent_clickable"))
            else:
                lbl = al or next((label_of(nodes[k]) for k in kids if label_of(nodes[k])), "")
                out.append(mk(nodes, a, box[a], lbl, "absorb=%d" % len(kids)))
            done.add(a)
            done.update(kids)
        for i, n in enumerate(nodes):
            if box[i] and is_signal(n) and i not in done and anc[i] is None:
                out.append(mk(nodes, i, box[i], label_of(n), ""))
    seen, res = set(), []
    for e in out:
        key = (e["bounds"], e["role"], e["label"])
        if key in seen:
            continue
        seen.add(key)
        res.append(e)
    res.sort(key=lambda e: (e["bounds"][1], e["bounds"][0], e["label"]))
    for e in res:
        e["id"] = hashid(nodes, e)
    return res
def emit(rows, screen, as_json=False):
    if as_json:
        print(json.dumps({"screen": list(screen), "n": len(rows), "nodes": rows}, ensure_ascii=False))
        return
    print("# n=%d screen=%dx%d" % (len(rows), screen[0], screen[1]))
    for e in rows:
        b = e["bounds"]
        lbl = (e["label"] or "-").replace("\t", " ")[:40]
        print("\t".join([e["id"], e["role"], lbl, e["rid"] or "-",
                         "%d,%d,%d,%d" % b, "%d,%d" % e["center"], e["flags"] or "-"]))
def get_rows(args, keep_all=False):
    root = load(getattr(args, "file", None), getattr(args, "serial", None))
    nodes = parse_tree(root)
    screen = screen_of(nodes)
    rows = prune(nodes, screen, keep_all=keep_all or getattr(args, "all", False))
    if not rows:
        die("[prune] 可操作集为空 (exit 4)：动态页/画布/无 a11y，改用 shot+grid 兜底", 4)
    return rows, screen
def resolve(rows, a):
    if a.id:
        for e in rows:
            if e["id"] == a.id:
                return e
        die("[resolve] id %s 不在当前可点集 (exit 6)" % a.id, 6)
    if a.rid:
        for e in rows:
            if a.rid in e["rid"]:
                return e
        die("[resolve] rid %s 未命中 (exit 6)" % a.rid, 6)
    if a.text:
        hit = [e for e in rows if e["label"] == a.text] or [e for e in rows if a.text in e["label"]]
        if not hit:
            die("[resolve] text %s 未命中 (exit 6)" % a.text, 6)
        return hit[0]
    die("[resolve] 需 --id/--text/--rid/--xy 之一 (exit 5)", 5)
def cmd_tap(a):
    t = None
    if a.xy:
        x, y = [int(v) for v in a.xy.split(",")]
    else:
        rows, _ = get_rows(a)
        t = resolve(rows, a)
        x, y = t["center"]
    adb(["shell", "input", "tap", str(x), str(y)], serial=a.serial)
    if not t or not a.verify:
        print("# tap %d,%d sent" % (x, y))
        return
    time.sleep(0.45)
    rows2, _ = get_rows(a)
    b = {e["id"] for e in rows}
    c = {e["id"] for e in rows2}
    print("# tap %d,%d id=%s label=%s changed=%s gone=%d new=%d" %
          (x, y, t["id"], t["label"] or "-", "yes" if b ^ c else "no", len(b - c), len(c - b)))
def cmd_type(a):
    if any(ord(ch) > 127 for ch in a.content):
        die("[type] input text 只支持 ASCII (exit 5)：中文改 keyevent 拼音或装 ADBKeyboard 后 base64 广播", 5)
    if a.xy:
        x, y = [int(v) for v in a.xy.split(",")]
        adb(["shell", "input", "tap", str(x), str(y)], serial=a.serial)
    elif not (a.id or a.text or a.rid):
        die("[type] 需 --id/--text/--rid/--xy 定位输入框 (exit 5)", 5)
    else:
        rows, _ = get_rows(a)
        t = resolve(rows, a)
        adb(["shell", "input", "tap", str(t["center"][0]), str(t["center"][1])], serial=a.serial)
    time.sleep(0.2)
    adb(["shell", "input", "text", a.content.replace(" ", "%s")], serial=a.serial)
    print("# type ok: %s" % a.content)
def cmd_swipe(a):
    if a.xy:
        x, y = [int(v) for v in a.xy.split(",")]
        box = (0, 0, x * 2, y * 2)
    else:
        rows, scr = get_rows(a)
        t = resolve(rows, a)
        x, y = t["center"]
        box = (0, 0, scr[0], scr[1])
    d = box[3] // 3 if a.dir in ("up", "down") else box[2] // 3
    if a.dir == "up":
        p = (x, y, x, y - d)
    elif a.dir == "down":
        p = (x, y, x, y + d)
    elif a.dir == "left":
        p = (x, y, x - d, y)
    else:
        p = (x, y, x + d, y)
    adb(["shell", "input", "swipe", *[str(v) for v in p], str(a.dur)], serial=a.serial)
    print("# swipe %s from %d,%d" % (a.dir, x, y))
def cmd_state(a):
    r = adb(["shell", "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp' | head -3"], serial=a.serial)
    print((r.stdout or "").strip())
def cmd_shot(a):
    r = adb(["exec-out", "screencap", "-p"], serial=a.serial, binary=True)
    if r.returncode != 0 or not r.stdout:
        die("[shot] screencap 失败 (exit 2)", 2)
    open(a.out, "wb").write(r.stdout)
    print("# shot %s %d bytes" % (a.out, len(r.stdout)))
def _pil():
    try:
        from PIL import Image, ImageDraw
        return Image, ImageDraw
    except Exception:
        die("[grid] 需 Pillow (exit 5)：pip install pillow", 5)
def cmd_grid(a):
    Image, ImageDraw = _pil()
    im = Image.open(a.src).convert("RGB")
    d = ImageDraw.Draw(im, "RGBA")
    W, H = im.size
    for x in range(0, W, a.step):
        d.line([(x, 0), (x, H)], fill=(255, 0, 0, 110))
        d.text((x + 2, 2), str(x), fill=(255, 255, 0, 255))
    for y in range(0, H, a.step):
        d.line([(0, y), (W, y)], fill=(255, 0, 0, 110))
        d.text((2, y + 2), str(y), fill=(255, 255, 0, 255))
    im.save(a.out)
    print("# grid %s %dx%d step=%d" % (a.out, W, H, a.step))
def cmd_roi(a):
    Image, _ = _pil()
    x, y = [int(v) for v in a.xy.split(",")]
    im = Image.open(a.src).convert("RGB")
    box = (max(0, x - a.r), max(0, y - a.r), min(im.width, x + a.r), min(im.height, y + a.r))
    crop = im.crop(box)
    s = a.to / float(max(crop.size))
    if s != 1.0:
        crop = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))))
    crop.save(a.out)
    print("# roi %s box=%s scale=%.2f" % (a.out, box, s))
def cmd_check(a):
    r1, scr = get_rows(a)
    r2, _ = get_rows(a)
    s1 = {e["id"] for e in r1}
    s2 = {e["id"] for e in r2}
    print("# n=%d screen=%dx%d stable=%s only1=%d only2=%d" %
          (len(r1), scr[0], scr[1], "yes" if s1 == s2 else "no", len(s1 - s2), len(s2 - s1)))
    for i in sorted(s1 - s2):
        print("# only1 " + i)
    for i in sorted(s2 - s1):
        print("# only2 " + i)
def cmd_tree(a):
    rows, scr = get_rows(a, keep_all=a.all)
    emit(rows, scr, a.json)
FIX = ('<hierarchy rotation="0">'
 '<node class="android.widget.FrameLayout" package="com.t" bounds="[0,0][1080,2340]" clickable="false">'
 '<node class="android.widget.LinearLayout" bounds="[0,100][1080,180]" clickable="false">'
 '<node class="android.widget.ImageButton" content-desc="返回" bounds="[20,110][120,170]" clickable="true"/>'
 '<node class="android.widget.TextView" text="设置" bounds="[140,120][400,160]" clickable="false"/>'
 '</node>'
 '<node class="androidx.recyclerview.widget.RecyclerView" bounds="[0,200][1080,1800]" scrollable="true" clickable="false">'
 '<node class="android.widget.LinearLayout" bounds="[0,200][1080,400]" clickable="true">'
 '<node class="android.widget.TextView" text="Wi-Fi" bounds="[40,240][600,280]"/>'
 '<node class="android.widget.TextView" text="已连接" bounds="[40,300][600,340]"/>'
 '</node>'
 '<node class="android.widget.LinearLayout" bounds="[0,420][1080,620]" clickable="true">'
 '<node class="android.widget.TextView" text="蓝牙" bounds="[40,460][600,500]"/>'
 '</node>'
 '</node>'
 '<node class="android.widget.LinearLayout" bounds="[0,2000][1080,2100]" clickable="true">'
 '<node class="android.widget.TextView" text="确定" bounds="[300,2030][800,2070]"/>'
 '</node>'
 '<node class="android.widget.EditText" bounds="[40,2200][1040,2280]" text="" clickable="false"/>'
 '<node class="android.view.View" bounds="[0,0][0,0]"/>'
 '<node class="android.view.View" bounds="[0,2500][1080,2400]"/>'
 '</node></hierarchy>')
def cmd_selftest(a):
    ok = [True]
    def chk(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        ok[0] = ok[0] and bool(cond)
    nodes = parse_tree(ET.fromstring(FIX))
    scr = screen_of(nodes)
    rows = prune(nodes, scr)
    labs = [e["label"] for e in rows]
    chk(scr == (1080, 2340), "screen=(%d,%d) 期望 (1080,2340)" % scr)
    chk(len(rows) == 8, "可点集 rows=%d 期望 8" % len(rows))
    chk("返回" in labs, "图标按钮靠 content-desc 保留")
    chk("设置" in labs, "不可点纯文本节点保留")
    chk(sum(1 for e in rows if e["flags"] == "parent_clickable") == 2, "反吸收：列表行拆出 2 个子目标")
    chk(any(e["label"] == "蓝牙" and e["flags"].startswith("absorb=") for e in rows), "吸收：单子节点行合并为 1 个目标")
    chk(any(e["role"] == "edit" for e in rows), "EditText 保留为 edit")
    chk(any(e["role"] == "scroll" for e in rows), "滚动容器保留为 scroll")
    chk(all(e["bounds"][2] - e["bounds"][0] > 0 and e["bounds"][3] - e["bounds"][1] > 0 for e in rows), "零面积/倒挂节点被剔除")
    chk([e["id"] for e in prune(parse_tree(ET.fromstring(FIX)), scr)] == [e["id"] for e in rows], "两次解析 id 序列完全一致")
    print("SELFTEST " + ("OK" if ok[0] else "FAILED"))
    sys.exit(0 if ok[0] else 1)
def build_ap():
    ap = argparse.ArgumentParser(prog="uitree.py", description="Android 界面树：dump→剪枝→动作→校验")
    ap.add_argument("-s", "--serial", default=os.environ.get("ANDROID_SERIAL"), help="adb serial")
    ap.add_argument("--file", help="离线解析已有 XML")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    p = sub.add_parser("tree", help="打印剪枝后可点集 TSV")
    p.add_argument("--json", action="store_true")
    p.add_argument("--all", action="store_true", help="不剪枝")
    p.set_defaults(f=cmd_tree)
    p = sub.add_parser("check", help="连 dump 两次比对 id 稳定性")
    p.set_defaults(f=cmd_check)
    p = sub.add_parser("tap", help="按目标点击（--xy 直点不 dump）")
    for k in ("id", "text", "rid", "xy"):
        p.add_argument("--" + k)
    p.add_argument("--no-verify", dest="verify", action="store_false")
    p.set_defaults(f=cmd_tap)
    p = sub.add_parser("type", help="向输入框输入 ASCII 文本")
    p.add_argument("content")
    for k in ("id", "text", "rid", "xy"):
        p.add_argument("--" + k)
    p.set_defaults(f=cmd_type)
    p = sub.add_parser("swipe", help="滚动")
    for k in ("id", "text", "rid", "xy"):
        p.add_argument("--" + k)
    p.add_argument("--dir", default="up", choices=["up", "down", "left", "right"])
    p.add_argument("--dur", type=int, default=300)
    p.set_defaults(f=cmd_swipe)
    p = sub.add_parser("state", help="当前前台窗口/Activity")
    p.set_defaults(f=cmd_state)
    p = sub.add_parser("shot", help="截屏到文件")
    p.add_argument("-o", "--out", default="shot.png")
    p.set_defaults(f=cmd_shot)
    p = sub.add_parser("grid", help="给截图叠 100px 网格坐标")
    p.add_argument("src")
    p.add_argument("-o", "--out", default="shot_grid.png")
    p.add_argument("--step", type=int, default=STEP)
    p.set_defaults(f=cmd_grid)
    p = sub.add_parser("roi", help="裁 ROI 并缩放到边长 --to")
    p.add_argument("src")
    p.add_argument("--xy", required=True)
    p.add_argument("-o", "--out", default="roi.png")
    p.add_argument("-r", type=int, default=240)
    p.add_argument("--to", type=int, default=512)
    p.set_defaults(f=cmd_roi)
    p = sub.add_parser("selftest", help="离线跑剪枝断言")
    p.set_defaults(f=cmd_selftest)
    return ap
def main():
    a = build_ap().parse_args()
    a.f(a)
if __name__ == "__main__":
    main()
