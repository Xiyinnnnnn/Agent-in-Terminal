#!/usr/bin/env python3
"""lin_ui.py — Linux 界面树（AT-SPI）：枚举 → 动作；坐标点击只在 X11 可靠
STATE 未实机验证 2026-11-17（本机 Termux，无 flatpak/Wayland 宿主）
用法见同目录 00-图形界面操作.md
退出码 0 ok ｜ 2 无 a11y 总线 ｜ 4 无命中 ｜ 5 参数或能力不支持 ｜ 6 目标未找到
"""
import argparse, os, shutil, subprocess, sys
BACKEND = None
def die(msg, code):
    print(msg, file=sys.stderr)
    sys.exit(code)
def _init():
    global BACKEND
    try:
        import gi
        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
        Atspi.init()
        BACKEND = ("gi", Atspi)
        return
    except Exception as e1:
        try:
            import pyatspi
            BACKEND = ("pyatspi", pyatspi)
            return
        except Exception:
            die("[a11y] 无 AT-SPI 绑定 (exit 2)：apt install python3-gi gir1.2-atspi-2.0 或 python3-pyatspi\n%s" % e1, 2)
def desk():
    k, mod = BACKEND
    return mod.get_desktop(0) if k == "gi" else mod.Registry.getDesktop(0)
def kids(a):
    return [a.get_child_at_index(i) for i in range(a.get_child_count())]
def nm(a):
    return a.get_name() or ""
def role(a):
    return a.get_role_name() or ""
def showing(a):
    k, mod = BACKEND
    if k == "gi":
        return a.get_state_set().contains(mod.StateType.SHOWING)
    return a.getState().contains(mod.STATE_SHOWING)
def ext(a):
    k, mod = BACKEND
    try:
        if k == "gi":
            c = a.get_component_iface()
            if not c:
                return None
            e = c.get_extents(mod.CoordType.SCREEN)
        else:
            c = a.queryComponent()
            if not c:
                return None
            e = c.getExtents(mod.DESKTOP_COORDS)
        return (e.x, e.y, e.width, e.height)
    except Exception:
        return None
def acts(a):
    k, mod = BACKEND
    try:
        ac = a.get_action_iface() if k == "gi" else a.queryAction()
        if not ac:
            return []
        return [ac.get_action_name(i) for i in range(ac.get_n_actions())]
    except Exception:
        return []
def do(a, i):
    k, mod = BACKEND
    ac = a.get_action_iface() if k == "gi" else a.queryAction()
    return ac.do_action(i)
def walk(a, path, idx, depth, maxd):
    if depth > maxd or len(idx) >= maxd * 20:
        return
    idx[path] = a
    for n, c in enumerate(kids(a)):
        walk(c, "%s.%d" % (path, n), idx, depth + 1, maxd)
def hid(path, a):
    import hashlib
    return hashlib.sha1(("%s|%s|%s" % (path, role(a), nm(a))).encode()).hexdigest()[:8]
def _sh(cmd):
    if not shutil.which(cmd[0]):
        return None
    return subprocess.run(cmd, capture_output=True, text=True)
def cmd_prep(a):
    g = _sh(["gsettings", "get", "org.gnome.desktop.interface", "toolkit-accessibility"])
    print("# toolkit-accessibility = %s" % ((g.stdout.strip() if g else "") or "? (无 gsettings：非 GNOME 或未装)"))
    b = _sh(["busctl", "--user", "list"])
    ok = ("org.a11y.Bus" in (b.stdout or "")) if b else None
    print("# a11y bus = %s" % ("yes" if ok else ("no → at-spi-bus-launcher 未起，树会空" if ok is False else "? (无 busctl)")))
    print("# flatpak 应用需：flatpak override --user --talk-name=org.a11y.Bus <appid>")
    _init()
    print("# backend = %s apps = %d" % (BACKEND[0], desk().get_child_count()))
def cmd_tree(a):
    _init()
    rows = []
    for app in kids(desk()):
        if a.app and a.app.lower() not in nm(app).lower():
            continue
        idx = {}
        walk(app, "app:%s" % nm(app), idx, 0, a.depth)
        for path, acc in idx.items():
            if not showing(acc):
                continue
            e = ext(acc)
            r = role(acc)
            if not a.all and r in ("filler", "panel", "unknown") and not nm(acc):
                continue
            flag = "local" if (not e or (e[0] == 0 and e[1] == 0)) else "-"
            rows.append((hid(path, acc), r, nm(acc)[:32] or "-", e, acts(acc), flag))
            if a.max and len(rows) >= a.max:
                break
        if a.max and len(rows) >= a.max:
            break
    print("# n=%d backend=%s coords_local=%d" % (len(rows), BACKEND[0], sum(1 for r in rows if r[5] == "local")))
    for i, r, n, e, ac, fl in rows:
        print("\t".join([i, r, n, ("%d,%d,%d,%d" % e) if e else "-", ",".join(ac[:3]) or "-", fl]))
    if rows and sum(1 for r in rows if r[5] == "local") == len(rows):
        print("# 提示：全部 local → Wayland 下拿不到全局坐标，用 act 走 Action 而不是 click", file=sys.stderr)
def cmd_act(a):
    _init()
    idx = {}
    for app in kids(desk()):
        walk(app, "app:%s" % nm(app), idx, 0, a.depth)
    for path, acc in idx.items():
        if hid(path, acc) == a.id:
            names = acts(acc)
            if not names:
                die("[act] 该节点无 Action (exit 6)：%s %s" % (role(acc), nm(acc)), 6)
            i = names.index(a.name) if (a.name and a.name in names) else 0
            do(acc, i)
            print("# act ok id=%s action=%s" % (a.id, names[i]))
            return
    die("[act] id %s 未命中 (exit 6)" % a.id, 6)
def _find(a):
    _init()
    idx = {}
    for app in kids(desk()):
        walk(app, "app:%s" % nm(app), idx, 0, a.depth)
    for path, acc in idx.items():
        if hid(path, acc) == a.id:
            return acc
    die("[id] %s 未命中 (exit 6)：先跑 tree 拿 id" % a.id, 6)
def cmd_click(a):
    acc = _find(a)
    e = ext(acc)
    if not e:
        die("[click] 无 extents (exit 5)：改用 act", 5)
    if e[0] == 0 and e[1] == 0 and not a.force:
        die("[click] 坐标疑为窗口局部(0,0)，Wayland 下不可信 (exit 5)：改用 act", 5)
    x, y = e[0] + e[2] // 2, e[1] + e[3] // 2
    if shutil.which("ydotool"):
        subprocess.run(["ydotool", "mousemove", "-a", "-x", str(x), "-y", str(y)], check=False)
        subprocess.run(["ydotool", "click", "0xC0"], check=False)
        print("# click ydotool %d,%d" % (x, y))
    elif shutil.which("xdotool"):
        subprocess.run(["xdotool", "mousemove", str(x), str(y), "click", "1"], check=False)
        print("# click xdotool %d,%d" % (x, y))
    else:
        die("[click] 需 ydotool(通吃) 或 xdotool(仅 X11) (exit 5)", 5)
def cmd_shot(a):
    if os.environ.get("WAYLAND_DISPLAY"):
        cands = [["grim", a.out], ["spectacle", "-b", "-n", "-o", a.out], ["gnome-screenshot", "-f", a.out]]
    else:
        cands = [["import", "-window", "root", a.out], ["scrot", a.out],
                 ["ffmpeg", "-y", "-f", "x11grab", "-i", os.environ.get("DISPLAY", ":0"), a.out]]
    for c in cands:
        if shutil.which(c[0]):
            subprocess.run(c, capture_output=True, text=True)
            if os.path.exists(a.out):
                print("# shot %s via %s" % (a.out, c[0]))
                return
    die("[shot] 无可用截图工具 (exit 5)：Wayland 装 grim/spectacle，X11 装 imagemagick/scrot", 5)
def build_ap():
    ap = argparse.ArgumentParser(prog="lin_ui.py", description="Linux AT-SPI 界面树与动作")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    p = sub.add_parser("prep", help="查 a11y 总线与后端")
    p.set_defaults(f=cmd_prep)
    p = sub.add_parser("tree", help="枚举界面树 TSV")
    p.add_argument("--app")
    p.add_argument("--max", type=int, default=300)
    p.add_argument("--depth", type=int, default=25)
    p.add_argument("--all", action="store_true")
    p.set_defaults(f=cmd_tree)
    p = sub.add_parser("act", help="用 Action 触发（Wayland 首选）")
    p.add_argument("--id", required=True)
    p.add_argument("--name")
    p.add_argument("--depth", type=int, default=25)
    p.set_defaults(f=cmd_act)
    p = sub.add_parser("click", help="坐标点击（仅 X11 可靠）")
    p.add_argument("--id", required=True)
    p.add_argument("--depth", type=int, default=25)
    p.add_argument("--force", action="store_true")
    p.set_defaults(f=cmd_click)
    p = sub.add_parser("shot", help="截图到文件")
    p.add_argument("-o", "--out", default="shot.png")
    p.set_defaults(f=cmd_shot)
    return ap
def main():
    a = build_ap().parse_args()
    a.f(a)
if __name__ == "__main__":
    main()
