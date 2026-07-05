# -*- coding: utf-8 -*-
"""
web —— 网页应用 | Web app
==========================
本地起一个 Flask 服务,浏览器打开就是一个现代深色仪表盘:
实时行情自动刷新 + 模型信号徽章 + 迷你走势图 + 纸面账户。
Local Flask app: a modern dark dashboard with live quotes, model signals, sparklines, paper account.

用法 | Usage:  quantmill web   (然后浏览器开 http://127.0.0.1:8787)
"""

from quantmill.web.app import serve

__all__ = ["serve"]
