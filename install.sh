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
INSTALLED_REC="$SKILL_DIR/.repo-skills"   
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


if [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == *"com.termux"* ]]; then
    mkdir -p "$PREFIX/bin"
    cat > "$PREFIX/bin/agent" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
exec python3 "$DEST/term_agent.py" "\$@"
EOF
    chmod +x "$PREFIX/bin/agent"
fi

if [ ! -f "$CONFIG_DIR/key.bin" ]; then
    echo "First run will guide you to enter API Key (getpass, machine-bound encrypted)"
    echo "Or run ahead: python3 $DEST/term_agent.py and follow the prompts"
fi

echo ""
echo "Installation complete!"
if [ -n "${TERMUX_VERSION:-}" ] || [[ "${PREFIX:-}" == *"com.termux"* ]]; then
    echo "   Run in terminal: agent"
else
    echo "   Run in terminal: python3 $DEST/term_agent.py"
fi
echo ""
echo "   Tip: new terminal = new conversation; ask the agent to modify its own parameters if needed"
