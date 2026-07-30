#!/bin/zsh
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "尚未完成项目依赖安装，请先双击：安装全部组件.command"
  if [ -t 0 ]; then
    printf '按 Enter 键关闭…'
    read -r _
  fi
  exit 1
fi
.venv/bin/python web_app.py
