# 图形界面操作（Linux / AT-SPI）
STATE ✗ 2026-11-17 未实机（本机无 flatpak/Wayland 宿主）｜SCOPE Linux 桌面与 flatpak 应用的控件树与动作｜SCRIPT `lin_ui.py`
## 何时用
Linux 上点 GUI/flatpak 应用自动化/X11 或 Wayland 下读控件/`xdotool` 不好使/窗口坐标对不上
## 命令
```bash
cd ~/.config/cli-agent/skill
./lin_ui.py prep                        # toolkit-accessibility / a11y bus / backend 三项体检
./lin_ui.py tree --app firefox --max 200  # 枚举控件 TSV：id role name extents actions flags
./lin_ui.py act --id 1a2b3c4d           # Wayland 首选：走 Action，不动鼠标
./lin_ui.py click --id 1a2b3c4d         # 坐标点击，仅 X11 可信
./lin_ui.py shot -o s.png               # grim / spectacle / gnome-screenshot / import 自适应
flatpak override --user --talk-name=org.a11y.Bus <appid>   # 沙箱应用上不了树时先补这条
```
## 参数 / 退出码
| 参数 | 说明 |
|---|---|
| `--app` / `--max` / `--depth` | 限定应用 / 节点上限 / 递归深度 |
| `--id` | `tree` 输出的 8 位 id |
| `--name` | `act` 指定 action 名，缺省取序号 0 |
| `--force` | 坐标疑似窗口局部时仍强点（自行核对） |
| 码 | `0` 成功 ｜ `2` 无 a11y 绑定或总线 ｜ `4` 无命中 ｜ `5` 能力不支持 ｜ `6` id 未命中 |
## 失败处置
| 现象 | 原因 | 动作 |
|---|---|---|
| `prep` 报 no bus | `at-spi-bus-launcher` 未起 | `gsettings set org.gnome.desktop.interface toolkit-accessibility true` 后重登 |
| 树是空的 | flatpak 沙箱挡了 a11y 总线 | `flatpak override --user --talk-name=org.a11y.Bus <appid>` |
| `flags=local` | Wayland 给的是窗口局部坐标 | 改用 `act`，别 `click` |
| `click` 需注入器 | 无 ydotool/xdotool | `apt install ydotool`（X11 可用 xdotool） |
## 陷阱
- Wayland 下 `get_extents(SCREEN)` 常返回 `0,0`：能用 Action 就别算坐标。
- 枚举依赖应用**自己实现 a11y**：Electron/Qt 需相应开关，自绘界面（游戏）没树。
- `--depth` 过大会拖慢；先 `--max 200` 看结构再定点。
