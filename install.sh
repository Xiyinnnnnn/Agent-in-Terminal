#!/usr/bin/env bash
set -uo pipefail
REPO="Xiyinnnnnn/cli-agent-plus-plus"
BRANCH="main"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH"
CDN="https://cdn.jsdelivr.net/gh/$REPO@$BRANCH"
API="https://api.github.com/repos/$REPO/contents"
DEST="$HOME/.local/bin/cli-agent"
APPS="$HOME/.local/share/applications"
CFG="$HOME/.config/cli-agent"
SKILL="$CFG/skill"
REC="$SKILL/.repo-skills"
FAIL=0

ok() { printf '  ok   %s\n' "$*"; }
bad() { printf '  FAIL %s\n' "$*" >&2; FAIL=1; }

PLAT=""
[ -n "${TERMUX_VERSION:-}" ] && PLAT=termux
if [ -z "$PLAT" ]; then
  case "$(uname -s)" in
    Darwin) PLAT=macos ;;
    Linux)
      [ -r /etc/os-release ] && . /etc/os-release 2>/dev/null
      case "${ID:-}" in
        debian|ubuntu|kali|raspbian|linuxmint|pop|deepin) PLAT=debian ;;
        arch|manjaro|endeavouros) PLAT=arch ;;
        fedora|rhel|centos|rocky|almalinux) PLAT=dnf ;;
        alpine) PLAT=alpine ;;
      esac ;;
  esac
fi
[ -z "$PLAT" ] && { echo "未识别的平台" >&2; exit 1; }

SUDO=""
[ "$PLAT" != termux ] && [ "$PLAT" != macos ] && [ "$(id -u)" -ne 0 ] && SUDO=sudo
inst() {
  case "$PLAT" in
    termux) pkg install -y "$@" ;;
    debian) $SUDO apt-get install -y "$@" ;;
    arch) $SUDO pacman -S --needed --noconfirm "$@" ;;
    dnf) $SUDO dnf install -y "$@" ;;
    alpine) $SUDO apk add "$@" ;;
    macos) brew install "$@" ;;
  esac
}
case "$PLAT" in
  termux) PKGS="python nodejs git curl libc++ python-numpy python-lxml python-pillow python-onnxruntime python-cryptography chromium ffmpeg yt-dlp" ;;
  debian) PKGS="python3 python3-pip nodejs npm git curl python3-numpy python3-lxml python3-pil python3-cryptography chromium ffmpeg yt-dlp" ;;
  arch) PKGS="python nodejs npm git curl python-numpy python-lxml python-pillow python-cryptography chromium ffmpeg yt-dlp" ;;
  dnf) PKGS="python3 python3-pip nodejs npm git curl python3-numpy python3-lxml python3-pillow python3-cryptography chromium ffmpeg yt-dlp" ;;
  alpine) PKGS="python3 py3-pip nodejs npm git curl py3-numpy py3-lxml py3-pillow py3-cryptography chromium ffmpeg yt-dlp" ;;
  macos) PKGS="python3 node git curl ffmpeg yt-dlp" ;;
esac

echo "[1/4] 系统依赖 ($PLAT)"
for p in $PKGS; do inst "$p" >/dev/null 2>&1 && ok "$p" || bad "$p"; done

echo "[2/4] Python 依赖"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  bad "python3"
else
  PF=""
  [ -z "${TERMUX_VERSION:-}" ] && ls /usr/lib/python3*/EXTERNALLY-MANAGED >/dev/null 2>&1 && PF="--break-system-packages"
  for i in "PIL|Pillow" "numpy|numpy" "lxml|lxml" "cryptography|cryptography" \
           "markitdown|markitdown[docx,pdf,pptx]" "openpyxl|openpyxl" "xlrd|xlrd" \
           "pptx|python-pptx" "mammoth|mammoth" "pdfplumber|pdfplumber" \
           "selenium|selenium" "fpdf|fpdf2" "fontTools|fonttools" \
           "prompt_toolkit|prompt_toolkit" "rich|rich"; do
    m="${i%%|*}"; s="${i#*|}"
    if "$PY" -c "import $m" >/dev/null 2>&1; then ok "$m"
    elif "$PY" -m pip install --no-input -q $PF "$s" >/dev/null 2>&1; then ok "$s"
    else bad "$s"; fi
  done
fi
echo "[3/4] Node 依赖"
mkdir -p "$SKILL"
if command -v npm >/dev/null 2>&1; then
  for d in docx pptxgenjs; do
    if [ -d "$SKILL/node_modules/$d" ]; then ok "$d"
    elif npm install --no-audit --no-fund --prefix "$SKILL" "$d" >/dev/null 2>&1; then ok "$d"
    else bad "$d"; fi
  done
else
  bad "npm"
fi

echo "[4/4] 程序与技能"
mkdir -p "$DEST" "$APPS" "$CFG/memory" "$SKILL"
dl() {
  curl -fsSL "$CDN/$1" -o "$2" 2>/dev/null && return 0
  curl -fsSL "$RAW/$1" -o "$2" 2>/dev/null && return 0
  return 1
}
if dl cli-agent.py "$DEST/cli-agent.py"; then ok "cli-agent.py"; else bad "cli-agent.py"; fi
if dl cli-agent.desktop "$APPS/cli-agent.desktop"; then ok "cli-agent.desktop"; else bad "cli-agent.desktop"; fi
chmod +x "$DEST/cli-agent.py" 2>/dev/null

LIST=""
if [ -n "$PY" ]; then
  LIST="$(curl -fsSL "$API/skills?ref=$BRANCH" 2>/dev/null | "$PY" -c '
import json, sys
try:
    items = json.load(sys.stdin)
except Exception:
    sys.exit(1)
if not isinstance(items, list):
    sys.exit(1)
for f in items:
    n = f.get("name") or ""
    if f.get("type") == "file" and n and not n.startswith("."):
        print(n)' 2>/dev/null)"
fi
[ -z "$LIST" ] && LIST="$(curl -fsSL "$CDN/skills/.manifest" 2>/dev/null || curl -fsSL "$RAW/skills/.manifest" 2>/dev/null)"
if [ -n "$LIST" ]; then
  n=0
  for f in $LIST; do
    if dl "skills/$f" "$SKILL/$f"; then
      n=$((n+1))
      case "$f" in *.sh) chmod +x "$SKILL/$f" ;; esac
    fi
  done
  if [ -f "$REC" ]; then
    for o in $(cat "$REC"); do
      case "$o" in ""|*/*|*..*) continue ;; esac
      printf '%s\n' "$LIST" | grep -qxF "$o" || rm -f "$SKILL/$o"
    done
  fi
  printf '%s\n' "$LIST" > "$REC"
  ok "$n 个技能文件 -> $SKILL"
else
  bad "技能清单（API 与 .manifest 均不可达）"
fi

if [ -n "${TERMUX_VERSION:-}" ]; then
  mkdir -p "$PREFIX/bin"
  printf '#!/data/data/com.termux/files/usr/bin/bash\nexec python3 "%s" "$@"\n' "$DEST/cli-agent.py" > "$PREFIX/bin/agent"
  chmod +x "$PREFIX/bin/agent"
  ok "命令 agent -> $PREFIX/bin/agent"
fi

echo
if [ "$FAIL" = 1 ]; then
  echo "有依赖未装成功，见上面 FAIL 行；其余功能可用"
  exit 1
fi
echo "完成。Termux 直接跑 agent；其他平台 python3 $DEST/cli-agent.py"
