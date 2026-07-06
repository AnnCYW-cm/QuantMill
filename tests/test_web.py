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


def test_forward_page_wired():
    """前瞻曲线页:导航项 + 视图容器 + 前端渲染函数都在。"""
    h = _client().get("/").get_data(as_text=True)
    assert 'data-v="forward"' in h and 'id="v-forward"' in h
    js = _client().get("/static/app.js").get_data(as_text=True)
    assert "renderForward" in js and "navchart" in js


def test_forward_api_empty_state(tmp_path, monkeypatch):
    """无记录时 /api/forward 返回 empty(不联网、不建仓)。"""
    from quantmill import config
    monkeypatch.setattr(config, "RESULTS_DIR", str(tmp_path))
    j = _client().get("/api/forward?market=cn&model=composite").get_json()
    assert j["empty"] is True and j["market"] == "cn"


def test_forward_api_reads_saved_curve(tmp_path, monkeypatch):
    """有落盘状态时 /api/forward 返回净值曲线 + 持仓 + 汇总(纯读,不联网)。"""
    from quantmill import config
    from quantmill.paper.forward import save_state, step_forward
    monkeypatch.setattr(config, "RESULTS_DIR", str(tmp_path))
    tgt = {"A": 0.5, "B": 0.5}
    st = step_forward({}, tgt, {"A": 10.0, "B": 20.0}, "2026-01-01")
    st = step_forward(st, tgt, {"A": 11.0, "B": 20.0}, "2026-01-02", horizon=20)
    save_state(st, "cn", "composite")
    j = _client().get("/api/forward?market=cn&model=composite").get_json()
    assert j["empty"] is False
    assert j["points"] == 2 and len(j["curve"]) == 2
    assert j["curve"][0]["dd"] == 0.0            # 首点回撤为 0
    assert len(j["positions"]) == 2
