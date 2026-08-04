#!/usr/bin/env bash
# ============================================================
#  term_agent 一键安装脚本
#
#   一条命令安装：
#    curl -fsSL https://raw.githubusercontent.com/Xiyinnnnnn/Agent-in-Terminal/main/install.sh | bash
#
#  安装内容：
#    term_agent.py     → ~/.local/bin/term_agent/       (主程序，零依赖)
#    term-agent.desktop→ ~/.local/share/applications/   (应用菜单双击入口)
#    config.json       → ~/.config/term_agent/          (API Key 配置)
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

echo "⬇️  从 $BASE 下载..."
mkdir -p "$DEST" "$APPS" "$CONFIG_DIR" "$MEMORY_DIR"

curl -fsSL "$BASE/term_agent.py" -o "$DEST/term_agent.py"
curl -fsSL "$BASE/term-agent.desktop" -o "$APPS/term-agent.desktop"
chmod +x "$DEST/term_agent.py" "$APPS/term-agent.desktop"

if [ ! -f "$CONFIG_DIR/key.bin" ]; then
    echo "🔑 首次运行会自动引导输入 API Key（getpass 不显示，机器绑定加密保存）"
    echo "   或提前运行: python3 $DEST/term_agent.py 按提示输入"
fi

echo ""
echo "✅ 安装完成！"
echo "   🖱️  双击运行：应用菜单搜索『终端智能体』"
echo "   ⌨️  命令行运行：python3 $DEST/term_agent.py"
echo ""
echo "   📝 提示：新终端=新对话；压缩阈值900K/模型/64K上限写死在程序里，"
echo "      想改就让它自己改：对 agent 说『修改你的程序参数』即可"
