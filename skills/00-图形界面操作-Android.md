# 图形界面操作（Android / termux+adb）
STATE ✓ 2026-11-17｜SCOPE adb 可达的 Android：读控件树、点元素、截图量坐标｜SCRIPT `uitree.py`｜PRUNE 4 条：面积≥64 且与屏相交 · 信号保留(clickable/scrollable/text/desc/控件类) · 吸收(可点祖先吞子) · 反吸收(行内≥2文案拆开)
## 何时用
点某个按钮/元素点不到/要控件信息/读列表有哪些项/只有截图没有控件/游戏·画布·视频页/坐标量不准/`uiautomator` 报 already registered
## 命令
```bash
cd ~/.config/cli-agent/skill; export TMPDIR=$HOME/.cache; D=127.0.0.1:7957
./uitree.py -s $D tree                  # 剪枝后可点集 TSV：id role label rid bounds center flags
./uitree.py -s $D tree --all            # 不剪枝，排查"为什么没出现"
./uitree.py -s $D check                 # 连 dump 两次比 id 稳定性
./uitree.py -s $D tap --text 确定        # 定位→tap→回读校验 changed
./uitree.py -s $D tap --xy 636,1400     # 直点（兜底链用，物理像素）
./uitree.py -s $D type "hello" --rid et # 仅 ASCII
./uitree.py -s $D swipe --text 列表 --dir up
./uitree.py -s $D shot -o s.png && ./uitree.py grid s.png -o g.png   # 兜底：截图+100px 网格
./uitree.py roi s.png --xy 636,700 -r 200 -o r.png                   # 裁 ROI 到 512 再问
./uitree.py selftest                    # 离线断言，不连设备
```
## 参数 / 退出码
| 参数 | 说明 |
|---|---|
| `-s` / `ANDROID_SERIAL` | adb 序列号；多设备必给 |
| `--file` | 离线解析已有 XML（调试/自测） |
| `--all` `--json` | 不剪枝 / 输出 JSON |
| `--no-verify` | `tap` 后不回读校验 |
| 码 | `0` 成功 ｜ `2` 无设备或 dump 失败 ｜ `3` UiAutomation 被占/被杀 ｜ `4` 树为空 ｜ `5` 能力不支持 ｜ `6` 目标未找到 |
## 失败处置
| 现象 | 原因 | 动作 |
|---|---|---|
| `exit 3` | UiAutomation 独占被抢（`already registered` / `Killed`） | 重启手机或 force-stop 占用者；先转 `shot`+`grid` 兜底，别在树上重试 |
| `exit 4` | 动态页/画布/无 a11y | 兜底链 |
| `exit 6` | 文案与实际不符 | `--all` 看真实 text/content-desc |
| `changed=no` | 坐标命中但无反应 | 点 `flags=parent_clickable` 的父级，或先 `swipe` 滚进视野 |
## 陷阱
- `input text` 仅 ASCII；中文改 keyevent 拼音或装 ADBKeyboard 后 base64 广播。
- dump 是**调用瞬间**的树：动画/加载中先 `check`，别复用旧坐标。
- `--xy` 吃物理像素（`wm size`），不是 dp。
- Termux 无 `/tmp` 写权限：中间文件走 `$HOME/.cache`。
- Linux 侧：`apt install android-tools-adb`（或发行版对应包），`export TMPDIR` 可省，其余命令一致。
