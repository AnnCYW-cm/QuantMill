"""
cross_view.py —— 横截面选股 | cross-sectional selection blueprint
=====================================================================
路由:/api/cross(后台算 → 轮询)。model=composite(稳健组合)/ ml(LightGBM)。
"""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request

from quantmill.web.state import _XCACHE, _XPROG
from quantmill.web.util import get_market

bp = Blueprint("cross", __name__)
_LOCK = threading.Lock()   # 保护"检查是否在跑→启动线程",防并发重复启动


def _compute_cross_bg(market, model="composite"):
    """后台跑横截面:面板 → (稳健组合/ML)打分 → top-k 回测 → DSR + 跨市场验证。"""
    key = f"{market}:{model}"
    _XPROG[key] = {"running": True, "stage": "建面板 / 打分回测…"}
    try:
        from quantmill.credibility.stats import deflated_sharpe_ratio, sharpe
        from quantmill.cross import (
            composite_score,
            factor_columns,
            get_panel,
            ic_table,
            topk_backtest,
            walk_forward_scores,
        )
        panel = get_panel(market=market, verbose=False)
        cols = factor_columns(panel)
        if model == "composite":
            score = composite_score(panel)
        else:
            score = walk_forward_scores(panel, cols, horizon=20, init_train=504, step=63)
        res = topk_backtest(panel, score, k=20, horizon=20, cost=0.0015)
        eq = res["equity"]
        sc = (1 + eq["long"]).cumprod()
        bc = (1 + eq["bench"]).cumprod()
        equity = [{"d": str(d.date()), "s": round(float(s), 4), "b": round(float(b), 4)}
                  for d, s, b in zip(eq.index, sc, bc)]
        m = res["metrics"]
        tab = ic_table(panel, cols).head(8)
        ic = [{"factor": r.factor, "IC": r.IC, "ICIR": r.ICIR} for r in tab.itertuples()]
        trials = [sharpe(topk_backtest(panel, score, k=kk, horizon=20, cost=0.0015)["equity"]["long"])
                  for kk in (10, 20, 30, 50)]
        dsr = deflated_sharpe_ratio(eq["long"], sr_trials=trials, n_trials=20)["dsr"]
        # 跨市场验证:稳健组合在 A股+港股各跑一遍(只用已缓存面板,失败则跳过)
        valid = []
        for mk in ("cn", "hk"):
            try:
                p = get_panel(market=mk, verbose=False)
                n = int(p.index.get_level_values(1).nunique())
                kk = int(min(20, max(8, n // 7)))
                mm = topk_backtest(p, composite_score(p), k=kk, horizon=20,
                                   cost=0.0015)["metrics"]["策略 top-k"]
                valid.append({"market": mk.upper(), "universe": n,
                              "excess": mm["超额年化"], "sharpe": mm["夏普"]})
            except Exception:  # noqa: BLE001
                pass
        _XCACHE[key] = {
            "model": model, "strat": m["策略 top-k"], "bench": m["基准 等权"],
            "ic": ic, "equity": equity, "valid": valid,
            "periods": len(eq), "winrate": round(float((eq["long"] > eq["bench"]).mean() * 100)),
            "dsr": round(float(dsr), 3), "universe": int(panel.index.get_level_values(1).nunique()),
            "start": equity[0]["d"], "end": equity[-1]["d"],
        }
    except Exception as e:  # noqa: BLE001
        _XCACHE[key] = {"error": f"{type(e).__name__}: {e}"}
    _XPROG[key]["running"] = False


@bp.route("/api/cross")
def api_cross():
    """横截面选股:算好返回;没算就后台启动并返回进度(前端轮询)。model=composite/ml。"""
    m = get_market("cn")
    model = request.args.get("model", "composite")
    if model not in ("composite", "ml"):
        model = "composite"
    key = f"{m}:{model}"
    if request.args.get("refresh"):
        _XCACHE.pop(key, None)
        _XPROG.pop(key, None)
    if key in _XCACHE:
        return jsonify({"status": "ready", "data": _XCACHE[key]})
    with _LOCK:                                    # 原子:检查+启动,避免并发重复起线程
        pr = _XPROG.get(key)
        if not pr or not pr["running"]:
            pr = {"running": True, "stage": "启动中…"}
            _XPROG[key] = pr
            threading.Thread(target=_compute_cross_bg, args=(m, model), daemon=True).start()
    return jsonify({"status": "computing", "stage": pr.get("stage", "计算中…")})
