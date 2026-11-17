#!/usr/bin/env bash
# install-deps.sh — cli-agent 全部依赖一次装齐
# 平台: Termux / Debian系 / Arch / dnf系 / Alpine / macOS
# 自举: 只用 bash + coreutils，新机上即便没有 python/node 也能跑
# 顺序: 系统包 → pip → npm（Termux 上反序会让 lxml/cryptography 走源码编译）
set -uo pipefail

usage() {
  cat <<'EOF'
usage: install-deps.sh [-n|--dry-run] [-y|--yes] [-u|--update] [-i DIR|--isolate[=DIR]]
  -n  只打印将执行的命令（默认就是预览）
  -y  真正执行安装
  -u  先更新包索引
  -i  隔离模式：系统包只模拟不装，python/node 装进 DIR（默认 ~/.cache/cli-agent-deps）
  --force  隔离模式下无视已装，强制重装
exit: 0 全绿 | 1 有失败项 | 2 平台未识别 | 4 参数错
EOF
}

DRY=0; ASSUME=0; UPDATE=0; FORCE=0; ISO=""
while [ $# -gt 0 ]; do
  case "$1" in
    -n|--dry-run) DRY=1 ;;
    -y|--yes)     ASSUME=1 ;;
    -u|--update)  UPDATE=1 ;;
    --force)      FORCE=1 ;;
    -i|--isolate) if [ $# -ge 2 ] && [ "${2#-}" = "$2" ]; then ISO="$2"; shift
                  else ISO="$HOME/.cache/cli-agent-deps"; fi ;;
    -i=*|--isolate=*) ISO="${1#*=}" ;;
    -h|--help)    usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage >&2; exit 4 ;;
  esac
  shift
done
[ "$ASSUME" = 1 ] && DRY=0

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
FAILED=()
say()  { printf '\n== %s\n' "$*"; }
ok()   { printf '   ok   %s\n' "$*"; }
skip() { printf '   skip %s\n' "$*"; }
warn() { printf '   warn %s\n' "$*"; }

run() {
  if [ "$DRY" = 1 ]; then printf '   dry  %s\n' "$*"; return 0; fi
  printf '   run  %s\n' "$*"
  if "$@"; then return 0; fi
  FAILED+=("$*"); return 1
}

# ---------- 1. 平台判定 ----------
PLAT=""
if [ -n "${TERMUX_VERSION:-}" ] || printf '%s' "${PREFIX:-}" | grep -q 'com\.termux'; then
  PLAT=termux
else
  case "$(uname -s 2>/dev/null)" in
    Darwin) PLAT=macos ;;
    Linux)
      ID=""
      [ -r /etc/os-release ] && . /etc/os-release 2>/dev/null
      case "${ID:-}" in
        debian|ubuntu|kali|raspbian|linuxmint|pop|deepin|devuan) PLAT=debian ;;
        arch|manjaro|endeavouros|artix) PLAT=arch ;;
        fedora|rhel|centos|rocky|almalinux|ol) PLAT=dnf ;;
        alpine) PLAT=alpine ;;
        *) PLAT=unknown ;;
      esac ;;
    *) PLAT=unknown ;;
  esac
fi
if [ "$PLAT" = unknown ]; then
  for c in pkg apt-get pacman dnf apk brew; do
    if command -v "$c" >/dev/null 2>&1; then
      case "$c" in
        pkg) PLAT=termux ;; apt-get) PLAT=debian ;; pacman) PLAT=arch ;;
        dnf) PLAT=dnf ;; apk) PLAT=alpine ;; brew) PLAT=macos ;;
      esac
      break
    fi
  done
fi
if [ "$PLAT" = unknown ]; then
  echo "无法识别平台（既非 Termux 也非已知发行版）" >&2; exit 2
fi

SUDO=()
case "$PLAT" in
  termux|macos) : ;;
  *) [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO=(sudo) ;;
esac
case "$PLAT" in
  termux) PM=(pkg install -y);                  PMU=(pkg update -y) ;;
  debian) PM=("${SUDO[@]}" apt-get install -y); PMU=("${SUDO[@]}" apt-get update -y) ;;
  arch)   PM=("${SUDO[@]}" pacman -S --needed --noconfirm); PMU=("${SUDO[@]}" pacman -Sy) ;;
  dnf)    PM=("${SUDO[@]}" dnf install -y);     PMU=("${SUDO[@]}" dnf makecache) ;;
  alpine) PM=("${SUDO[@]}" apk add);            PMU=("${SUDO[@]}" apk update) ;;
  macos)  PM=(brew install);                    PMU=(brew update) ;;
esac

say "平台"
ok "plat=$PLAT arch=$(uname -m)"
[ "$DRY" = 1 ] && warn "预览模式：不改动系统，真装加 --yes"

# ---------- 2. 系统包 ----------
# 顺序有意：libc++ 必须排在 numpy 前（<30 缺 __hash_memory，numpy 导入即崩）
case "$PLAT" in
  termux) PKGS=(libc++ python nodejs git curl python-numpy python-lxml python-pillow python-onnxruntime python-cryptography chromium ffmpeg yt-dlp) ;;
  debian) PKGS=(python3 python3-pip python3-venv nodejs npm git curl python3-numpy python3-lxml python3-pil python3-cryptography chromium ffmpeg yt-dlp) ;;
  arch)   PKGS=(python python-pip nodejs npm git curl python-numpy python-lxml python-pillow python-cryptography chromium ffmpeg yt-dlp) ;;
  dnf)    PKGS=(python3 python3-pip nodejs npm git curl python3-numpy python3-lxml python3-pillow python3-cryptography chromium ffmpeg yt-dlp) ;;
  alpine) PKGS=(python3 py3-pip nodejs npm git curl py3-numpy py3-lxml py3-pillow py3-cryptography chromium ffmpeg yt-dlp) ;;
  macos)  PKGS=(python3 node git curl ffmpeg yt-dlp) ;;
esac

if [ -n "$ISO" ]; then
  say "1/3 系统包（隔离：只模拟，不写 \$PREFIX）"
  for p in "${PKGS[@]}"; do
    if command -v apt-get >/dev/null 2>&1; then
      sim="$(apt-get -s install "$p" 2>&1)"
      case "$sim" in
        *"Inst $p"*)             ok "源中存在 $p" ;;
        *"already the newest"*)  ok "已装 $p（未改动）" ;;
        *) warn "源中未见 $p"; FAILED+=("simulate: $p") ;;
      esac
    else
      warn "无 apt-get，无法模拟 $p"
    fi
  done
else
  say "1/3 系统包（${#PKGS[@]} 项）"
  [ "$UPDATE" = 1 ] && run "${PMU[@]}"
  for p in "${PKGS[@]}"; do run "${PM[@]}" "$p"; done
fi

# ---------- 3. pip ----------
say "2/3 pip"
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  warn "找不到 python，跳过 pip 段"
  FAILED+=("python missing -> pip skipped")
else
  ok "$("$PY" -V 2>&1)"
  PIPFLAGS=(); TARGET=()
  if [ -n "$ISO" ]; then
    mkdir -p "$ISO/py" "$ISO/js"
    TARGET=(--target "$ISO/py")
    ok "隔离目录 $ISO（不写 site-packages）"
  elif [ -z "${TERMUX_VERSION:-}" ] && ls /usr/lib/python3*/EXTERNALLY-MANAGED >/dev/null 2>&1; then
    PIPFLAGS=(--break-system-packages)
    warn "PEP 668 环境：加 --break-system-packages"
  fi
  # 模|pip规格|标记（sys = 系统包提供，隔离模式下跳过，避免走源码编译）
  PIP_DEPS=(
    "PIL|Pillow|sys"
    "numpy|numpy|sys"
    "lxml|lxml|sys"
    "cryptography|cryptography|sys"
    "markitdown|markitdown[docx,pdf,pptx]|"
    "openpyxl|openpyxl|"
    "xlrd|xlrd|"
    "pptx|python-pptx|"
    "mammoth|mammoth|"
    "pdfplumber|pdfplumber|"
    "selenium|selenium|"
    "fpdf|fpdf2|"
    "fontTools|fonttools|"
  )
  for item in "${PIP_DEPS[@]}"; do
    mod="${item%%|*}"; rest="${item#*|}"; spec="${rest%%|*}"; flag="${rest#*|}"
    [ "$flag" = "$rest" ] && flag=""
    if [ -n "$ISO" ]; then
      if [ "$flag" = sys ] && "$PY" -c "import $mod" >/dev/null 2>&1; then
        skip "py:$mod（系统包提供）"; continue
      fi
      if [ "$FORCE" = 0 ] && PYTHONPATH="$ISO/py" "$PY" -S -c "import $mod" >/dev/null 2>&1; then
        skip "py:$mod（隔离区已有）"; continue
      fi
    elif "$PY" -c "import $mod" >/dev/null 2>&1; then
      skip "py:$mod"; continue
    fi
    run "$PY" -m pip install --no-input "${PIPFLAGS[@]}" "${TARGET[@]}" --upgrade "$spec"
  done
fi

# ---------- 4. npm ----------
say "3/3 npm"
if ! command -v npm >/dev/null 2>&1; then
  warn "找不到 npm，跳过 npm 段"
  FAILED+=("npm missing -> npm skipped")
else
  NPM_ROOT="$SKILL_DIR"; [ -n "$ISO" ] && NPM_ROOT="$ISO/js"
  for d in docx pptxgenjs; do
    if [ -d "$NPM_ROOT/node_modules/$d" ] && [ "$FORCE" = 0 ]; then skip "npm:$d"; continue; fi
    mkdir -p "$NPM_ROOT"
    run npm install --no-audit --no-fund --prefix "$NPM_ROOT" "$d"
  done
fi

# ---------- 5. 环境资源 ----------
say "字体（md2pdf 依赖）"
if [ -f /system/fonts/DroidSansChinese.ttf ]; then
  ok "/system/fonts/DroidSansChinese.ttf"
elif command -v fc-list >/dev/null 2>&1 && fc-list 2>/dev/null | grep -qi 'cjk\|noto sans sc'; then
  ok "系统 CJK 字体可用"
else
  warn "无 CJK 字体：md2pdf 需 MD2PDF_CN_FONT=<ttf路径>"
fi

# ---------- 6. 自检 ----------
say "自检"
for c in python3 node npm git curl ffmpeg yt-dlp; do
  if command -v "$c" >/dev/null 2>&1; then ok "$c"; else warn "缺命令 $c"; fi
done
for c in chromium-browser chromium google-chrome; do
  if command -v "$c" >/dev/null 2>&1; then ok "$c"; break; fi
done
NPM_ROOT="$SKILL_DIR"; [ -n "$ISO" ] && NPM_ROOT="$ISO/js"
check_mod() {
  if [ -n "$ISO" ]; then PYTHONPATH="$ISO/py" "$PY" -c "import $1" >/dev/null 2>&1 && return 0; fi
  "$PY" -c "import $1" >/dev/null 2>&1
}
if [ -n "${PY:-}" ] && [ -x "${PY:-/nonexistent-binary}" ]; then
  bad=""
  for item in PIL numpy lxml markitdown openpyxl xlrd pptx selenium fpdf fontTools; do
    check_mod "$item" || bad="$bad $item"
  done
  if [ -z "$bad" ]; then ok "python 关键模块齐全"; else warn "缺模块:$bad"; fi
fi
for d in docx pptxgenjs; do
  if [ -d "$NPM_ROOT/node_modules/$d" ]; then ok "node:$d"
  elif [ "$DRY" = 1 ] && [ -n "$ISO" ]; then warn "node:$d 待装（隔离）"
  else warn "缺 node 包 $d"; fi
done

# ---------- 7. 汇总 ----------
if [ -n "$ISO" ]; then
  {
    echo "# 激活隔离依赖：. $ISO/env.sh"
    echo "export PYTHONPATH=\"$ISO/py\${PYTHONPATH:+:\$PYTHONPATH}\""
    echo "export NODE_PATH=\"$ISO/js/node_modules\${NODE_PATH:+:\$NODE_PATH}\""
    echo "export PATH=\"$ISO/py/bin:\$PATH\""
  } > "$ISO/env.sh"
  say "隔离产物"
  ok "python -> $ISO/py"
  ok "node   -> $ISO/js/node_modules"
  ok "激活: . $ISO/env.sh（不 source 则仍走系统环境）"
fi
echo
if [ "${#FAILED[@]}" -gt 0 ]; then
  say "失败 ${#FAILED[@]} 项"
  printf '   %s\n' "${FAILED[@]}"
  exit 1
fi
if [ "$DRY" = 1 ]; then
  if [ -n "$ISO" ]; then echo "预览结束；隔离真装: $0 --isolate=$ISO --yes"
  else echo "预览结束；真装: $0 --yes"; fi
  exit 0
fi
echo "全部就绪"
exit 0
