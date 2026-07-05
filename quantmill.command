#!/bin/bash
# 双击启动 quantmill 网页台(会开一个终端窗口,Ctrl+C 退出)
# Double-click to launch the quantmill web app (Ctrl+C to quit)
cd "$(dirname "$0")"
echo "启动 quantmill 量化台…"
exec ./.venv/bin/quantmill web
