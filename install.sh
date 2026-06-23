#!/bin/bash
# ============================================================
# 个人行程与报销 Skill - 一键安装脚本
# 仓库: https://github.com/linson1786-cmd/nobusy-invoice-trip-organizer
# 用法: curl -sL https://raw.githubusercontent.com/linson1786-cmd/nobusy-invoice-trip-organizer/main/install.sh | bash
# ============================================================

set -e

REPO="linson1786-cmd/nobusy-invoice-trip-organizer"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/main"
DEPLOY_PY_URL="${RAW_BASE}/scripts/invoice-trip-organizer/deploy.py"
SKILL_NAME="个人行程与报销"
DEPLOY_PATH="$HOME/.workbuddy/skills/invoice-trip-organizer"

echo ""
echo "=================================================="
echo "  ${SKILL_NAME} Skill - 一键安装/升级"
echo "=================================================="
echo ""

# 检查 python3
if ! command -v python3 &> /dev/null; then
    echo "  [错误] 未找到 python3，请先安装 Python 3.8+"
    exit 1
fi

# 检查是否已安装
if [ -f "$DEPLOY_PATH/scripts/VERSION" ]; then
    CURRENT_VER=$(cat "$DEPLOY_PATH/scripts/VERSION")
    echo "  当前版本: ${CURRENT_VER}"
    echo "  正在检查更新..."
else
    echo "  首次安装"
    echo "  正在下载..."
fi

# 下载 deploy.py 到临时目录
TMP_FILE=$(mktemp /tmp/invoice_deploy_XXXXXX.py)
curl -sL "$DEPLOY_PY_URL" -o "$TMP_FILE"

if [ ! -s "$TMP_FILE" ]; then
    echo "  [错误] 下载 deploy.py 失败"
    rm -f "$TMP_FILE"
    exit 1
fi

# 执行升级（--upgrade 会自动检查版本、下载、备份、部署）
python3 "$TMP_FILE" --upgrade

# 清理
rm -f "$TMP_FILE"

echo ""
echo "=================================================="
echo "  安装/升级完成!"
echo "  安装路径: ${DEPLOY_PATH}"
echo ""
echo "  后续升级方式:"
echo "    1. 对话中说「升级发票整理 Skill」"
echo "    2. 或运行: python3 ~/.workbuddy/skills/invoice-trip-organizer/scripts/deploy.py --upgrade"
echo "=================================================="
echo ""
