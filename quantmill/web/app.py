"""
app.py —— Flask 网页应用(装配层)| Flask web app (assembly)
=====================================================================
本文件只负责"装配":创建 app、全局错误处理、首页、注册蓝图、serve()。
各领域逻辑在蓝图里 | domain logic lives in blueprints:
    market.py      行情 / 信号            | quotes / signals
    cross_view.py  横截面选股             | cross-sectional selection
    research.py    K线 / 因子 / 消息 / 可信度 | chart / factors / news / credibility
    trading.py     纸面 / 组合 / 总览 / 导出 / 自选 | paper / portfolio / overview / export / watchlist
共享缓存在 state.py;前端在 static/{index.html, app.css, app.js}。
"""
from __future__ import annotations

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

app = Flask(__name__)


@app.errorhandler(Exception)
def _on_error(e):     # 返回 JSON 错误体(前端友好)+ 真实 HTTP 状态码(便于排障/监控)
    code = e.code if isinstance(e, HTTPException) else 500
    return jsonify({"error": f"{type(e).__name__}: {e}"}), code


@app.route("/")
def index():
    return app.send_static_file("index.html")


# 注册各领域蓝图 | register domain blueprints
from quantmill.web import cross_view, market, research, trading  # noqa: E402

for _mod in (market, cross_view, research, trading):
    app.register_blueprint(_mod.bp)


def serve(port: int = 8787, open_browser: bool = True):
    if open_browser:
        import threading
        import webbrowser
        threading.Timer(1.3, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    print(f"🏭 quantmill web 已启动 → http://127.0.0.1:{port}   (Ctrl+C 退出)")
    print("   行情延迟约 15 分钟(免费源);信号/体检首次需训模型,稍等。")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
