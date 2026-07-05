# -*- coding: utf-8 -*-
"""
test_web.py —— 网页前端服务冒烟(纯离线,不碰网络 API)
test_web.py —— web frontend serving smoke test (offline; no network APIs)
=====================================================================
拆分后前端在 static/{index.html,app.css,app.js},这里锁死它们能被正确服务。
"""

from quantmill.web.app import app


def _client():
    return app.test_client()


def test_index_served():
    r = _client().get("/")
    assert r.status_code == 200
    assert r.mimetype == "text/html"


def test_index_references_split_assets():
    """首页应引用抽出来的 css/js,而不是内联。"""
    h = _client().get("/").get_data(as_text=True)
    assert "/static/app.css" in h
    assert "/static/app.js" in h
    assert "<style>" not in h        # 已不再内联 CSS


def test_static_css_and_js_served():
    c = _client()
    css = c.get("/static/app.css")
    js = c.get("/static/app.js")
    assert css.status_code == 200 and css.mimetype == "text/css"
    assert js.status_code == 200 and "javascript" in js.mimetype
    assert ".btn" in css.get_data(as_text=True)
    assert "loadCross" in js.get_data(as_text=True)


def test_error_handler_returns_json_and_real_code():
    """未知路由 -> 404;错误处理器给 JSON 体 + 真实状态码。"""
    r = _client().get("/no-such-route")
    assert r.status_code == 404
    assert r.is_json
    assert "error" in r.get_json()
