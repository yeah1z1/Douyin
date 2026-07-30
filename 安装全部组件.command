#!/bin/zsh
set -e
cd "$(dirname "$0")"

# 优先使用 Homebrew 的 Python，避免 macOS 自带 Python 3.9 的弃用提示。
BASE_PYTHON="/usr/local/bin/python3"
if [ ! -x "$BASE_PYTHON" ]; then
  BASE_PYTHON="$(command -v python3)"
fi

echo "1/3 安装主项目依赖…"
if [ ! -x ".venv/bin/python" ]; then
  "$BASE_PYTHON" -m venv .venv
fi
.venv/bin/python -m pip install --retries 5 --timeout 180 -r requirements.txt

echo "2/3 安装扫码登录浏览器组件…"
.venv/bin/python -m playwright install chromium

echo "3/3 安装抖音主页采集器…"
VENDOR_DIR="vendor/TikTokDownloader"
if [ ! -x "/usr/local/bin/python3" ]; then
  echo "未找到 Homebrew Python 3.12+，无法安装主页采集器。"
  exit 1
fi
if [ ! -x "$VENDOR_DIR/.venv/bin/python" ]; then
  /usr/local/bin/python3 -m venv "$VENDOR_DIR/.venv"
fi
"$VENDOR_DIR/.venv/bin/python" -m pip install --retries 5 --timeout 180 -r "$VENDOR_DIR/requirements.txt"

echo ""
echo "全部组件安装完成。现在可双击 启动程序.command。"
if [ -t 0 ]; then
  printf '按 Enter 键关闭…'
  read -r _
fi
