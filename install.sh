#!/usr/bin/env bash
# ============================================================
#  term_agent 一键安装脚本
#
#   一条命令安装：
#    curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
#
#  安装内容：
#    term_agent.py     -> ~/.local/bin/term_agent/       (主程序，零依赖)
#    term-agent.desktop-> ~/.local/share/applications/   (应用菜单双击入口)
#    config.json       -> ~/.config/term_agent/          (API Key 配置)
# ============================================================
set -e

# 仓库：github.com/Xiyinnnnnn/Agent-in-Terminal
REPO="Xiyinnnnnn/Agent-in-Terminal"
BRANCH="main"
BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"

DEST="$HOME/.local/bin/term_agent"
APPS="$HOME/.local/share/applications"
CONFIG_DIR="$HOME/.config/term_agent"
CONFIG="$CONFIG_DIR/config.json"
MEMORY_DIR="$CONFIG_DIR/memory"

echo "Downloading from $BASE ..."
mkdir -p "$DEST" "$APPS" "$CONFIG_DIR" "$MEMORY_DIR"

curl -fsSL "$BASE/term_agent.py" -o "$DEST/term_agent.py"
curl -fsSL "$BASE/term-agent.desktop" -o "$APPS/term-agent.desktop"
chmod +x "$DEST/term_agent.py" "$APPS/term-agent.desktop"

if [ ! -f "$CONFIG_DIR/key.bin" ]; then
    echo "First run will guide you to enter API Key (getpass, machine-bound encrypted)"
    echo "Or run ahead: python3 $DEST/term_agent.py and follow the prompts"
fi

echo ""
echo "Installation complete!"
echo "   Run in terminal: python3 $DEST/term_agent.py"
echo ""
echo "   Tip: new terminal = new conversation; compression threshold 900K/model/64K cap are hardcoded,"
echo "       ask the agent to modify its own parameters if you want changes"
