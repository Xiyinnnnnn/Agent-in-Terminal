# 无头浏览器-Selenium截图抓取
STATE ✓ 2026-11-08｜SCOPE Termux(aarch64/bionic) 与 Linux 的 headless chromium 抓取；不覆盖有头 X11、playwright｜SCRIPT `hl.py`

## 何时用
- 目标内容靠 JS 渲染，`curl` 拿到的 HTML 是空壳
- 要整页截图 / PDF / 页面内 JS 求值 / 等某元素出现再取
- 环境不能上 playwright（Termux：其自带 node 为 x86_64 glibc，bionic 跑不了）

## 命令
```bash
H=~/.config/term_agent/skill/hl.py
python3 $H check                                # 自检+冒烟；首次运行自动装 selenium
python3 $H title https://a.com                  # 标题 + 最终 URL
python3 $H text  https://a.com                  # body 可见文本
python3 $H dom   https://a.com                  # page_source
python3 $H shot  https://a.com out.png --full   # --w/--h 控视口
python3 $H pdf   https://a.com out.pdf
python3 $H wait  https://a.com --wait '.card'   # 只等元素不输出
echo 'return document.title' | python3 $H js https://a.com
python3 $H js https://a.com s.js                # 脚本走第二位置参数
```

## 参数 / 退出码
| 参数 | 默认 | 说明 |
|---|---|---|
| `--w/--h` | 430/932 | 视口；桌面页用 1280/900 |
| `--ua` | mobile | `mobile`/`desktop`/任意 UA 串 |
| `--wait CSS` | — | goto 后等该选择器出现 |
| `--full` | — | 全页截图，高度封顶 16000 px |
| `--timeout` | 60 | 加载与等待超时（秒） |
| `--no-install` | — | 缺依赖只报错不装；另 `HL_NO_INSTALL=1` |

退出码 `0` 成功 ｜ `2` 依赖缺且未装成 ｜ `3` 驱动或页面异常 ｜ `4` 等待超时。覆盖路径用 `HL_CHROME` / `HL_DRIVER`。

## 失败处置
| 现象 | 处置 |
|---|---|
| 报找不到 chromium 可执行文件 | Termux `pkg install chromium`；Linux 用 `HL_CHROME` 指真实二进制 |
| `pkg install chromium` 失败 | `pkg update` 后重试；装好后跑 `check` |
| 截图空白 / 全黑 | 加 `--wait` 再截、加 `--full`、放大 `--w/--h` |
| 等待超时但肉眼有元素 | 元素在 iframe 内或需滚动触发 → 换选择器，或 js 里 `scrollTo` 后再取 |
| 需要登录态 | 本脚本不持久化 cookie；换 API 或自建 user-data-dir |

## 陷阱
- Termux 装完**没有** `chromium` 可执行文件：入口是 `$PREFIX/bin/chromium-browser`（launcher 脚本），真实二进制 `$PREFIX/lib/chromium/chrome`。`which chromium` 为空 ≠ 没装。
- 四件套业务必需：`--headless=new --no-sandbox --disable-gpu --disable-dev-shm-usage`（已内置，勿删）。
- 临时文件必须落 `$TMPDIR`；Termux 的 `/tmp` 属 shell:shell，不可写。
- 启动噪声 `file_path_watcher_inotify` 一类 ERROR 无害。
- 每次调用新起进程（约 1 s 起，真实站点 3–10 s）；批量抓多页应自上 session，别循环调本脚本。
