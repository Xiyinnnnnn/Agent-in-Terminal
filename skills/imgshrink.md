# imgshrink（视觉降 token）

截图/大图 → 同尺寸比例缩到长边 1000 的 216 色 PNG。实测 base64 降 95~97%。

```bash
S=~/.config/term_agent/skill/imgshrink.py
python3 $S shot                      # adb 截屏 → 缩放 → 默认存 ~/.cache/ctxinject/shot_small.png
python3 $S shot out.png 800          # 指定输出与长边
python3 $S file in.png               # 生成 in.small.png；也可给 out/长边/色阶
python3 $S bench in.png              # 解码耗时 + 压缩率
```
环境变量：`TA_IMG_MAX` 长边（默认 1000）、`TA_IMG_LEV` 色阶（默认 6=216 色）。

## 要点
- **screencap 不带 `-p` 是 raw RGBA**（16B 头），ctxinject 的 `shot` 已改走这条路，比解 PNG 快得多。
- 宿主 `_img()` 已挂本模块：PNG 且长边>1000 才处理，结果按 `路径|size|mtime` 缓存，异常自动回退原图。
- 只吃 PNG/raw；jpg/webp/gif 原样过。
- 改了宿主或本模块后：`python3 $S bench 样本.png` + 与参考实现比对再上线。
