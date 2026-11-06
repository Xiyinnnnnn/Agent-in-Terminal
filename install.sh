#!/usr/bin/env bash
# ============================================================
#  term_agent 一键安装脚本（双源自动回退版）
#
#   一条命令安装：
#     CDN (国内直连):  curl -fsSL https://cdn.jsdelivr.net/gh/Xiyinnnnnn/Agent-in-Terminal@main/install.sh | bash
#     GitHub 直连:     curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
#
#  下载策略：jsDelivr CDN 优先（国内友好），失败自动回退 GitHub raw
#  安装内容：
#    term_agent.py      -> ~/.local/bin/term_agent/       (主程序，零依赖)
#    term-agent.desktop -> ~/.local/share/applications/   (应用菜单双击入口)
#    key.bin            -> ~/.config/term_agent/          (API Key 加密保存，首次运行生成)
#    skills/*           -> ~/.config/term_agent/skill/    (原厂技能：整目录原样复刻)
#
#  技能目录：整目录跟随仓库 —— 新增技能无需改脚本；
#            仓库里删掉的技能，重装时只清理「本脚本上次装过的同名文件」，不碰你自建的技能

# ============================================================
set -e

REPO="Xiyinnnnnn/Agent-in-Terminal"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"
CDN_BASE="https://cdn.jsdelivr.net/gh/$REPO@$BRANCH"
API_BASE="https://api.github.com/repos/$REPO/contents"

DEST="$HOME/.local/bin/term_agent"
APPS="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/term_agent"
MEMORY_DIR="$CONFIG_DIR/memory"
SKILL_DIR="$CONFIG_DIR/skill"
INSTALLED_REC="$SKILL_DIR/.repo-skills"   # 上次由本脚本安装的技能清单（用于同步删除）

# ── 依赖：仅补齐 Python / Pillow，不改变原安装与更新流程 ──
if [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == *"com.termux"* ]]; then
    command -v pkg >/dev/null 2>&1 || { echo "[FAIL] 未找到 Termux pkg" >&2; exit 1; }
    if ! python3 -c 'import PIL' >/dev/null 2>&1; then
        pkg install -y python python-pillow
    fi
else
    if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import PIL' >/dev/null 2>&1; then
        if [ "$(id -u)" -eq 0 ]; then
            ROOT=()
        elif command -v sudo >/dev/null 2>&1; then
            ROOT=(sudo)
        else
            echo "[FAIL] 安装 Python/Pillow 需要 root 权限（请安装 sudo 或以 root 运行）" >&2
            exit 1
        fi

        if command -v apt-get >/dev/null 2>&1; then
            "${ROOT[@]}" apt-get install -y python3 python3-pil
        elif command -v dnf >/dev/null 2>&1; then
            "${ROOT[@]}" dnf install -y python3 python3-pillow
        elif command -v pacman >/dev/null 2>&1; then
            "${ROOT[@]}" pacman -S --needed --noconfirm python python-pillow
        elif command -v apk >/dev/null 2>&1; then
            "${ROOT[@]}" apk add python3 py3-pillow
        else
            echo "[FAIL] 暂不支持此 Linux 包管理器，请手动安装 Python 3 和 Pillow" >&2
            exit 1
        fi
    fi
fi

python3 -c 'import sys; from PIL import Image; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || {
    echo "[FAIL] 需要 Python 3.10+ 且 Pillow 可正常导入" >&2
    exit 1
}

echo "Downloading (CDN first, GitHub fallback)..."
mkdir -p "$DEST" "$APPS" "$CONFIG_DIR" "$MEMORY_DIR" "$SKILL_DIR"

# 双源下载：CDN 优先，失败自动切 GitHub raw
dl() {
    local file="$1" out="$2"
    if curl -fsSL "$CDN_BASE/$file" -o "$out" 2>/dev/null; then
        echo "  [CDN] $file"
    elif curl -fsSL "$RAW_BASE/$file" -o "$out" 2>/dev/null; then
        echo "  [RAW] $file"
    else
        echo "  [FAIL] $file (CDN 与 GitHub 均不可达，请检查网络)" >&2
        return 1
    fi
}

dl term_agent.py "$DEST/term_agent.py"
dl term-agent.desktop "$APPS/term-agent.desktop"
chmod +x "$DEST/term_agent.py" "$APPS/term-agent.desktop"

# ── skills/ 整目录原样复刻 ───────────────────────────────────
#  清单来源①GitHub Contents API（中文名原样返回，永远最新）
#        ②API 不可达时读仓库内 skills/.manifest（静态兜底，CDN 可取）
#  文件获取仍走 dl()，即每个技能都享受「CDN 优先」；同名文件直接覆盖=与仓库一致
#  注意：只复刻 skills/ 第一层文件（不含子目录、不含 dot 文件）
list_skills_api() {
    curl -fsSL "$API_BASE/skills?ref=$BRANCH" 2>/dev/null | python3 -c '
import json, sys
try:
    items = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if not isinstance(items, list):
    sys.exit(1)
for f in items:
    name = f.get("name") or ""
    if f.get("type") == "file" and name and not name.startswith("."):
        print(name)' 2>/dev/null
}

SKILL_LIST="$(list_skills_api || true)"
if [ -z "$SKILL_LIST" ]; then
    echo "  [INFO] GitHub API 不可达，改用 skills/.manifest 兜底清单" >&2
    SKILL_LIST="$(curl -fsSL "$CDN_BASE/skills/.manifest" 2>/dev/null \
        || curl -fsSL "$RAW_BASE/skills/.manifest" 2>/dev/null || true)"
    SKILL_LIST="$(printf '%s\n' "$SKILL_LIST" | tr -d '\r' | grep -v '^[[:space:]]*$' || true)"
fi

if [ -n "$SKILL_LIST" ]; then
    n=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        if dl "skills/$f" "$SKILL_DIR/$f"; then
            case "$f" in *.sh) chmod +x "$SKILL_DIR/$f" ;; esac
            n=$((n + 1))
        else
            echo "  [WARN] 技能 $f 下载失败，已跳过" >&2
        fi
    done <<SKILLS_EOF
$SKILL_LIST
SKILLS_EOF
    # 同步清理：上次装过、本次仓库已删除的原厂技能（仅限记录名单内、且是纯文件名，不碰自建技能）
    if [ -f "$INSTALLED_REC" ]; then
        while IFS= read -r old; do
            case "$old" in ""|*/*|*..*) continue ;; esac
            if ! printf '%s\n' "$SKILL_LIST" | grep -qxF "$old"; then
                rm -f "$SKILL_DIR/$old" && echo "  [DEL] 仓库已移除：$old"
            fi
        done < "$INSTALLED_REC"
    fi
    printf '%s\n' "$SKILL_LIST" > "$INSTALLED_REC"
    echo "  skills/ 原样复刻完成：$n 个文件 -> $SKILL_DIR"
else
    echo "  [WARN] 取不到 skills/ 清单（API 与 .manifest 均不可达），本次跳过技能复刻" >&2
fi

if [ ! -f "$CONFIG_DIR/key.bin" ]; then
    echo "First run will guide you to enter API Key (getpass, machine-bound encrypted)"
    echo "Or run ahead: python3 $DEST/term_agent.py and follow the prompts"
fi

echo ""
echo "Installation complete!"
echo "   Run in terminal: python3 $DEST/term_agent.py"
echo ""
echo "   Tip: new terminal = new conversation; ask the agent to modify its own parameters if needed"
