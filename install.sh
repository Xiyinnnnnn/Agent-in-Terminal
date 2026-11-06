#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

REPO="Xiyinnnnnn/Agent-in-Terminal"
BRANCH="main"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
DEST="$PREFIX/share/term_agent"
BIN="$PREFIX/bin"
CONFIG="$HOME/.config/term_agent"
SKILL_DIR="$CONFIG/skill"
MANAGED="$SKILL_DIR/.repo-skills"

fail() { printf '[ERROR] %s\n' "$*" >&2; exit 1; }
log() { printf '\n\033[1;36m[%s]\033[0m %s\n' "$1" "$2"; }

[ -n "${PREFIX:-}" ] || fail "请在 Termux 中运行。"
command -v pkg >/dev/null 2>&1 || fail "未检测到 Termux pkg。"
command -v curl >/dev/null 2>&1 || {
  pkg update -y
  pkg install -y curl
}

log "1/6" "更新软件包并安装运行依赖"
pkg update -y
pkg install -y python curl tar tmux ffmpeg android-tools python-pillow

# yt-dlp 仅供 videowatch 技能使用；安装失败不影响主 Agent。
if ! pkg install -y yt-dlp; then
  printf '[WARN] yt-dlp 未安装，视频下载技能不可用；可稍后执行 pkg install yt-dlp\n' >&2
fi

log "2/6" "下载项目源码"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
ARCHIVE="$TMP/source.tar.gz"
URL="https://codeload.github.com/$REPO/tar.gz/refs/heads/$BRANCH"
curl -fL --retry 3 --retry-delay 2 "$URL" -o "$ARCHIVE" ||
  fail "源码下载失败，请检查网络或 GitHub 仓库地址。"
tar -xzf "$ARCHIVE" -C "$TMP"
SRC="$TMP/Agent-in-Terminal-$BRANCH"
[ -f "$SRC/term_agent.py" ] || fail "压缩包中没有找到 term_agent.py。"

log "3/6" "安装主程序"
mkdir -p "$DEST" "$BIN" "$CONFIG" "$CONFIG/memory" "$CONFIG/taskbook" "$SKILL_DIR"
install -m 644 "$SRC/term_agent.py" "$DEST/term_agent.py"
[ ! -f "$SRC/LICENSE" ] || install -m 644 "$SRC/LICENSE" "$DEST/LICENSE"
python -m py_compile "$DEST/term_agent.py"

log "4/6" "同步仓库 Skills（保留用户自建技能）"
NEW_LIST="$TMP/new-skills"
: > "$NEW_LIST"
if [ -f "$SRC/skills/.manifest" ]; then
  while IFS= read -r name; do
    [ -n "$name" ] || continue
    case "$name" in */*|*..*) continue ;; esac
    [ -f "$SRC/skills/$name" ] || continue
    install -m 644 "$SRC/skills/$name" "$SKILL_DIR/$name"
    case "$name" in *.py|*.sh) chmod 700 "$SKILL_DIR/$name" ;; esac
    printf '%s\n' "$name" >> "$NEW_LIST"
  done < "$SRC/skills/.manifest"
fi
if [ -f "$MANAGED" ]; then
  while IFS= read -r old; do
    [ -n "$old" ] || continue
    case "$old" in */*|*..*) continue ;; esac
    if ! grep -Fqx "$old" "$NEW_LIST"; then
      rm -f "$SKILL_DIR/$old"
    fi
  done < "$MANAGED"
fi
cp "$NEW_LIST" "$MANAGED"
chmod 600 "$MANAGED"

log "5/6" "创建 agent / agent-update 命令"
{
  printf '%s\n' '#!/data/data/com.termux/files/usr/bin/bash'
  printf 'exec python "%s/term_agent.py" "$@"\n' "$DEST"
} > "$BIN/agent"
cat > "$BIN/agent-update" <<'UPDATE'
#!/data/data/com.termux/files/usr/bin/bash
set -e
curl -fsSL "https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh" | bash
UPDATE
chmod 755 "$BIN/agent" "$BIN/agent-update"

log "6/6" "检查 API 配置"
grep -nE '^API_URL|^MODEL|^MAX_TOK|^MAX_OUT' "$DEST/term_agent.py" || true

cat <<EOF

================================================
 Agent-in-Terminal 已安装到 Termux
================================================
启动：       agent
更新：       agent-update
配置目录：   $CONFIG
主程序目录： $DEST
Skills：     $SKILL_DIR

首次启动会提示输入 DeepSeek API Key。
也可在启动前设置环境变量：
  export DEEPSEEK_API_KEY='你的密钥'

默认模型：deepseek-flash
官方接口：https://api.deepseek.com/chat/completions

可选模型：
  export TERM_AGENT_MODEL=deepseek-v4-pro

提示：deepseek-v4-pro 当前为文本模型；需要图片输入时请使用 deepseek-flash。
================================================
EOF
