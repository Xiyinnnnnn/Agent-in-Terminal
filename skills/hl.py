#!/usr/bin/env python
"""hl.py — 无头 chromium 抓取/截图（Termux / Linux 自适应）

启动即自愈依赖：缺 selenium → pip 装；缺 chromium/chromedriver → Termux 下 pkg 装。
用法: hl.py <cmd> <target> [out] [选项]
  cmd: check | title | text | dom | shot | pdf | js | wait
  --w 430 --h 932 --ua mobile|desktop|<串> --wait CSS --full --timeout 60 --no-install
退出码: 0 成功 | 2 缺依赖且未自动装成 | 3 页面/驱动失败
"""
import argparse, base64, os, pathlib, shutil, subprocess, sys, time

PREFIX = os.environ.get("PREFIX", "/usr")
IS_TERMUX = "com.termux" in PREFIX
CHROMES = [os.path.join(PREFIX, "bin/chromium-browser"),
           os.path.join(PREFIX, "bin/chromium"),
           os.path.join(PREFIX, "lib/chromium/chrome")]
DRIVERS = [os.path.join(PREFIX, "bin/chromedriver")]
UA_M = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/157.0.0.0 Mobile Safari/537.36")
UA_D = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36")


def die(msg, code=2):
    print("[hl] " + msg, file=sys.stderr)
    sys.exit(code)


def sh(cmd, quiet):
    if not quiet:
        print("[hl] $ " + " ".join(cmd), file=sys.stderr)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except Exception as e:
        die("执行失败 %s: %s" % (cmd[0], e))
    if r.returncode != 0:
        return None, (r.stdout + r.stderr).strip()[-800:]
    return (r.stdout + r.stderr), None


def find_first(paths, names):
    for p in paths:
        if p and (os.path.isfile(p) or (names is None)):
            return p
    for n in names:
        w = shutil.which(n)
        if w:
            return w
    return None


def ensure_deps(auto):
    """缺 pip 包 → 装；缺二进制 → Termux pkg 装。返回 (driver, chrome)"""
    env_off = os.environ.get("HL_NO_INSTALL") == "1"
    auto = auto and not env_off
    try:
        import selenium  # noqa: F401
    except ImportError:
        if not auto:
            die("缺 selenium；去掉 --no-install 且勿设 HL_NO_INSTALL=1 即自动 pip 安装，或手工 pip install selenium")
        print("[hl] 安装 selenium …", file=sys.stderr)
        if not sh([sys.executable, "-m", "pip", "install", "--quiet", "selenium"], True)[0]:
            die("pip install selenium 失败；换源再试：pip install -i https://pypi.org/simple selenium")
        try:
            import selenium  # noqa: F401
        except ImportError:
            die("selenium 装完仍导不进")
    drv = find_first([os.environ.get("HL_DRIVER")] + DRIVERS, ["chromedriver"])
    chrome = find_first([os.environ.get("HL_CHROME")] + CHROMES,
                        ["chromium-browser", "chromium", "google-chrome"])
    if (not drv or not chrome) and auto and IS_TERMUX:
        print("[hl] 安装 chromium（约 700 MB，含 chromedriver）…", file=sys.stderr)
        if sh(["pkg", "install", "-y", "chromium"], False)[0] is None:
            die("pkg install chromium 失败；先 pkg update 再重试")
        drv = find_first(DRIVERS, ["chromedriver"])
        chrome = find_first(CHROMES, ["chromium-browser", "chromium"])
    if not drv:
        die("找不到 chromedriver；Termux: pkg install chromium；Linux: apt install chromium-driver")
    if not chrome:
        die("找不到 chromium 可执行文件；用 --chrome / HL_CHROME 指定（Termux 是 bin/chromium-browser，不是 chromium）")
    return drv, chrome


def browser(a, drv, chrome):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    o = Options()
    for f in ("--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
              "--hide-scrollbars", "--disable-extensions", "--no-first-run",
              "--disable-background-networking", "--disable-sync", "--mute-audio",
              f"--window-size={a.w},{a.h}"):
        o.add_argument(f)
    ua = a.ua
    if ua == "mobile":
        ua = UA_M
    elif ua == "desktop":
        ua = UA_D
    if ua:
        o.add_argument("--user-agent=" + ua)
    o.binary_location = chrome
    d = webdriver.Chrome(service=Service(drv), options=o)
    d.set_page_load_timeout(a.timeout)
    return d


def goto(d, url, a):
    d.get(url)
    if a.wait:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import TimeoutException
        try:
            WebDriverWait(d, a.timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, a.wait)))
        except TimeoutException:
            die("等待超时：%.0fs 内未见 %s（选择器错 / 页面改版 / 需登录）" % (a.timeout, a.wait), 4)


def body_text(d):
    from selenium.webdriver.common.by import By
    return d.find_element(By.TAG_NAME, "body").text


def full_h(d):
    return d.execute_script(
        "return Math.max(document.body.scrollHeight,document.documentElement.scrollHeight,"
        "document.body.offsetHeight,document.documentElement.offsetHeight)")


def main():
    p = argparse.ArgumentParser(prog="hl.py", description="headless chromium: text/dom/shot/pdf/js")
    p.add_argument("cmd", choices=["check", "text", "dom", "shot", "js", "wait", "pdf", "title"])
    p.add_argument("target", nargs="?", help="URL；check 可省")
    p.add_argument("out", nargs="?", help="shot/pdf 输出路径；js 时为脚本路径（省略=读 stdin）")
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--ua", default="mobile")
    p.add_argument("--w", type=int, default=430)
    p.add_argument("--h", type=int, default=932)
    p.add_argument("--wait", help="先等 CSS 选择器出现")
    p.add_argument("--full", action="store_true", help="shot 全页")
    p.add_argument("--no-install", action="store_true", help="缺依赖只报错不自动装")
    a = p.parse_args()

    drv, chrome = ensure_deps(not a.no_install)
    if a.cmd == "check":
        import selenium
        print("selenium", selenium.__version__)
        print("driver  ", drv)
        print("chrome  ", chrome)
        a.target = a.target or "data:text/html,<title>HL_OK</title>"
        d = browser(a, drv, chrome)
        try:
            d.get(a.target)
            print("title   ", d.title, "|", d.current_url[:60])
            print("engine  ", d.capabilities.get("browserVersion"))
        finally:
            d.quit()
        return 0
    if not a.target:
        die("缺 target 参数")
    if a.cmd == "js":
        if a.out and a.out != "-":
            src = pathlib.Path(a.out).read_text()
        else:
            src = sys.stdin.read()
        if not src.strip():
            die("js 需要脚本：hl.py js <url> script.js 或 echo 'return ...' | hl.py js <url>")
        d = browser(a, drv, chrome)
        try:
            goto(d, a.target, a)
            print(d.execute_script(src))
        finally:
            d.quit()
        return 0

    d = browser(a, drv, chrome)
    try:
        t0 = time.time()
        goto(d, a.target, a)
        if a.cmd == "text":
            print(body_text(d))
        elif a.cmd == "title":
            print(d.title, "\n", d.current_url)
        elif a.cmd == "dom":
            print(d.page_source)
        elif a.cmd == "wait":
            print("OK", "%.1fs" % (time.time() - t0))
        elif a.cmd == "shot":
            if a.full:
                d.set_window_size(a.w, min(full_h(d) + 40, 16000))
            out = a.out or "shot.png"
            d.save_screenshot(out)
            print(out, pathlib.Path(out).stat().st_size, "bytes")
        elif a.cmd == "pdf":
            out = a.out or "page.pdf"
            r = d.execute_cdp_cmd("Page.printToPDF", {"printBackground": True,
                                                      "preferCSSPageSize": True})
            pathlib.Path(out).write_bytes(base64.b64decode(r["data"]))
            print(out, pathlib.Path(out).stat().st_size, "bytes")
    finally:
        d.quit()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        m = str(e).strip().splitlines()
        print("[hl] %s: %s" % (type(e).__name__, m[0] if m else ""), file=sys.stderr)
        sys.exit(4 if "Timeout" in type(e).__name__ else 3)
