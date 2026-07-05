# -*- coding: utf-8 -*-
"""
market.py —— 行情 & 信号 | quotes & signals blueprint
=====================================================================
路由:/api/quotes /api/signals。美股有 Alpaca key 时用实时价覆盖(纯数据)。
"""
from __future__ import annotations

import threading
import time

from flask import Blueprint, jsonify, request

from quantmill import config
from quantmill.watchlist import load_watchlist
from quantmill.web.state import _QCACHE, _QSRC, _SCACHE, _SPROG

bp = Blueprint("market", __name__)


def _yahoo(sym, market):
    from quantmill.data import _cn_to_yahoo, _hk_to_yahoo
    return _hk_to_yahoo(sym) if market == "hk" else (
        _cn_to_yahoo(sym) if market == "cn" else sym)


def _get_quotes(symbols, market):
    now = time.time()
    if market in _QCACHE and now - _QCACHE[market][0] < 15:
        return _QCACHE[market][1]
    import yfinance as yf
    ymap = {s: _yahoo(s, market) for s in symbols}
    try:
        df = yf.download(list(dict.fromkeys(ymap.values())), period="3mo",
                         interval="1d", progress=False, auto_adjust=True)
    except Exception:  # noqa: BLE001
        return {}
    if df is None or df.empty:
        return {}
    close = df["Close"]
    out = {}
    for s, yt in ymap.items():
        try:
            ser = (close[yt] if hasattr(close, "columns") and yt in close.columns
                   else close).dropna()
        except Exception:  # noqa: BLE001
            continue
        if len(ser) < 2:
            continue
        last, prev = float(ser.iloc[-1]), float(ser.iloc[-2])
        out[s] = {"price": round(last, 2), "prev": round(prev, 2),
                  "chg": round((last / prev - 1) * 100, 2),
                  "spark": [round(float(x), 4) for x in ser.tail(40)]}
    # 美股:有 Alpaca key 就用实时成交价覆盖(prev 仍用昨收算涨跌)| real-time override
    src = "yfinance"
    if market == "us":
        from quantmill.data.live import alpaca_last_prices
        live = alpaca_last_prices(symbols)
        if live:
            src = "alpaca"
            for s in out:
                if s in live and out[s]["prev"]:
                    last = round(live[s], 2)
                    out[s]["price"] = last
                    out[s]["chg"] = round((last / out[s]["prev"] - 1) * 100, 2)
                    out[s]["spark"] = out[s]["spark"][:-1] + [round(live[s], 4)]
    _QSRC[market] = src
    _QCACHE[market] = (now, out)
    return out


def _get_signals(symbols, market, horizon=5):
    if market in _SCACHE:
        return _SCACHE[market]
    from quantmill.execution.engine import _snapshot
    out = {}
    for s in symbols:
        try:
            _, p_up, _, _ = _snapshot(s, market, horizon)
        except Exception:  # noqa: BLE001
            continue
        out[s] = {"p": round(p_up, 3),
                  "label": "hold" if p_up > 0.55 else ("cash" if p_up < 0.45 else "wait")}
    _SCACHE[market] = out
    return out


def _compute_signals_bg(symbols, market, horizon):
    """后台逐只算信号并更新进度,算完写入缓存。| Compute signals in background with progress."""
    from quantmill.execution.engine import _snapshot
    _SPROG[market] = {"done": 0, "total": len(symbols), "running": True}
    out = {}
    for s in symbols:
        try:
            _, p_up, _, _ = _snapshot(s, market, horizon)
            out[s] = {"p": round(p_up, 3),
                      "label": "hold" if p_up > 0.55 else ("cash" if p_up < 0.45 else "wait")}
        except Exception:  # noqa: BLE001
            pass
        _SPROG[market]["done"] += 1
    _SCACHE[market] = out
    _SPROG[market]["running"] = False


@bp.route("/api/quotes")
def api_quotes():
    m = request.args.get("market", "us")
    syms = load_watchlist().get(m, [])
    q = _get_quotes(syms, m)
    return jsonify({"market": m, "symbols": syms, "quotes": q,
                    "source": _QSRC.get(m, "yfinance"),
                    "updated": time.strftime("%H:%M:%S")})


@bp.route("/api/signals")
def api_signals():
    """信号:算好就返回;没算就后台启动并返回进度(前端轮询)。| ready or computing+progress."""
    m = request.args.get("market", "us")
    if request.args.get("refresh"):
        _SCACHE.pop(m, None)
        _SPROG.pop(m, None)
    if m in _SCACHE:
        return jsonify({"status": "ready", "signals": _SCACHE[m]})
    pr = _SPROG.get(m)
    if not pr or not pr["running"]:
        syms = load_watchlist().get(m, [])
        threading.Thread(target=_compute_signals_bg, args=(syms, m, config.HORIZON),
                         daemon=True).start()
        pr = {"done": 0, "total": len(syms), "running": True}
        _SPROG[m] = pr
    return jsonify({"status": "computing", "done": pr["done"], "total": pr["total"]})
