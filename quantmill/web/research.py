# -*- coding: utf-8 -*-
"""
research.py —— 个股研究 | chart / factors / news / credibility blueprint
=====================================================================
路由:/api/chart /api/factors /api/news /api/credibility。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from quantmill import config
from quantmill.watchlist import load_watchlist
from quantmill.web.state import _CCACHE

bp = Blueprint("research", __name__)


def _get_chart(symbol, market, n=120):
    from quantmill.data import get_ohlcv
    df = get_ohlcv(symbol, market).tail(n)
    return [{"d": str(i.date()), "o": round(float(o), 2), "h": round(float(h), 2),
             "l": round(float(lo), 2), "c": round(float(c), 2)}
            for i, o, h, lo, c in zip(df.index, df["Open"], df["High"],
                                      df["Low"], df["Close"])]


def _get_credibility(market):
    if market in _CCACHE:
        return _CCACHE[market]
    from quantmill.credibility.validate import compute_proba, symbol_credibility
    rows = []
    for s in load_watchlist().get(market, []):
        try:
            feat_df, proba = compute_proba(s, market, config.START, None, config.HORIZON)
            h = symbol_credibility(feat_df, proba, config.ROBUSTNESS_BUY_THS,
                                   config.CASH, config.COMMISSION)
        except Exception:  # noqa: BLE001
            h = None
        if h:
            rows.append({"sym": f"{market}:{s}", **h})
    n = len(rows)
    res = {"rows": rows, "n": n, "sig": sum(1 for r in rows if r["dsr"] > 0.95),
           "mean_pbo": round(sum(r["pbo"] for r in rows) / n, 3) if n else 0.0}
    _CCACHE[market] = res
    return res


def _get_factors(symbol, market):
    from quantmill.data import get_ohlcv
    from quantmill.factor.analysis import ic_report
    rep = ic_report(get_ohlcv(symbol, market), horizon=config.HORIZON)
    return rep.head(18).to_dict("records")


def _get_news(symbol, market):
    from quantmill.llm.sentiment import news_sentiment
    res = news_sentiment(symbol, market, limit=12)
    return {"mean": round(res["mean"], 3), "n": res["n"], "scorer": res["scorer"],
            "items": [{"title": it["title"], "sent": round(it.get("sentiment", 0), 2),
                       "date": str(it["time"].date()) if it.get("time") is not None else ""}
                      for it in res["items"]]}


@bp.route("/api/chart")
def api_chart():
    return jsonify(_get_chart(request.args.get("symbol"), request.args.get("market", "us")))


@bp.route("/api/credibility")
def api_credibility():
    m = request.args.get("market", "us")
    if request.args.get("refresh"):
        _CCACHE.pop(m, None)
    return jsonify(_get_credibility(m))


@bp.route("/api/factors")
def api_factors():
    return jsonify(_get_factors(request.args.get("symbol"),
                                request.args.get("market", "us")))


@bp.route("/api/news")
def api_news():
    return jsonify(_get_news(request.args.get("symbol"),
                             request.args.get("market", "us")))
