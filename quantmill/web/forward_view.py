"""
forward_view.py —— 前瞻纸面曲线 | forward paper track blueprint
=====================================================================
路由:
  GET  /api/forward         读当前前瞻记录(净值曲线+持仓+汇总),快。
  POST /api/forward/run      联网推进一步(取最新数据→按当日价追加净值点),慢 → 后台+轮询。
只前进、不回看:历史净值点绝不改写(引擎层 8 个测试焊死)。
"""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

from quantmill.web.state import _FPROG
from quantmill.web.util import get_market

bp = Blueprint("forward", __name__)
_LOCK = threading.Lock()


def _payload(market, model):
    """把落盘的前瞻状态整理成前端要的净值曲线 + 持仓 + 汇总。"""
    from quantmill.paper import forward_summary, load_state
    st = load_state(market, model)
    if not st.get("nav"):
        return {"empty": True, "market": market, "model": model}
    s = forward_summary(st)
    peak = 0.0
    curve = []
    for p in st["nav"]:
        peak = max(peak, p["nav"])
        curve.append({"d": p["date"], "nav": round(p["nav"], 2),
                      "dd": round((p["nav"] / peak - 1) * 100, 2)})
    base = st["nav"][0]["nav"] or 1
    pos = [{"sym": k, "w": round(w * 100, 1)} for k, w in st.get("positions", {}).items()]
    return {"empty": False, "market": market, "model": model,
            "inception": s["inception"], "points": s["points"], "notional": s["notional"],
            "nav": s["nav"], "ret": s["return%"], "max_dd": s["max_dd%"],
            "exposure": s["exposure"], "last_rebalance": st.get("last_rebalance"),
            "base": base, "curve": curve, "positions": pos}


def _run_forward_bg(market, model):
    key = f"{market}:{model}"
    _FPROG[key] = {"running": True, "stage": "取最新面板 + 目标票现价…"}
    try:
        from quantmill.paper import run_forward
        out = run_forward(market=market, model=model)
        _FPROG[key] = {"running": False, "stage": "done", "prices_ok": out["prices_ok"]}
    except Exception as e:  # noqa: BLE001
        _FPROG[key] = {"running": False, "stage": "error", "error": f"{type(e).__name__}: {e}"}


@bp.route("/api/forward")
def api_forward():
    m = get_market("cn")
    model = request.args.get("model", "composite")
    if model not in ("composite", "ml"):
        model = "composite"
    key = f"{m}:{model}"
    pr = _FPROG.get(key, {})
    data = _payload(m, model)
    data["running"] = bool(pr.get("running"))
    data["stage"] = pr.get("stage")
    if pr.get("stage") == "error":
        data["run_error"] = pr.get("error")
    return jsonify(data)


@bp.route("/api/forward/run", methods=["POST"])
def api_forward_run():
    """启动一次前瞻推进(后台跑,前端轮询 /api/forward 看进度与结果)。"""
    m = get_market("cn")
    model = request.args.get("model", "composite")
    if model not in ("composite", "ml"):
        model = "composite"
    key = f"{m}:{model}"
    with _LOCK:                                   # 原子:检查+启动,防并发重复推进(会污染同一状态文件)
        pr = _FPROG.get(key)
        if pr and pr.get("running"):
            return jsonify({"status": "already_running"})
        _FPROG[key] = {"running": True, "stage": "启动中…"}
        threading.Thread(target=_run_forward_bg, args=(m, model), daemon=True).start()
    return jsonify({"status": "started"})
