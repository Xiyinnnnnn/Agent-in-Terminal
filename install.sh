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
# ============================================================
set -e

REPO="Xiyinnnnnn/Agent-in-Terminal"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"
CDN_BASE="https://cdn.jsdelivr.net/gh/$REPO@$BRANCH"

DEST="$HOME/.local/bin/term_agent"
APPS="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/term_agent"
MEMORY_DIR="$CONFIG_DIR/memory"

echo "Downloading (CDN first, GitHub fallback)..."
mkdir -p "$DEST" "$APPS" "$CONFIG_DIR" "$MEMORY_DIR"

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

if [ ! -f "$CONFIG_DIR/key.bin" ]; then
    echo "First run will guide you to enter API Key (getpass, machine-bound encrypted)"
    echo "Or run ahead: python3 $DEST/term_agent.py and follow the prompts"
fi

echo ""
echo "Installation complete!"
echo "   Run in terminal: python3 $DEST/term_agent.py"
echo ""
echo "   Tip: new terminal = new conversation; ask the agent to modify its own parameters if needed"
