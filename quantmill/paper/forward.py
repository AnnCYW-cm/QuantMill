# -*- coding: utf-8 -*-
"""
forward.py —— 前瞻纸面记录引擎 | forward paper track engine
=====================================================================
纯状态推进(step_forward,可离线测)+ 实盘取数封装(run_forward,你机器上跑)分离。
状态存 results/forward_<market>_<model>.json:只追加净值点,绝不改历史。
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from quantmill import config
from quantmill.risk.overlay import inverse_vol_weights


def _state_path(market: str, model: str) -> str:
    return os.path.join(config.RESULTS_DIR, f"forward_{market}_{model}.json")


def load_state(market: str, model: str) -> dict:
    p = _state_path(market, model)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict, market: str, model: str) -> str:
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    p = _state_path(market, model)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return p


def target_weights(panel: pd.DataFrame, score: pd.Series, k: int = 20,
                   max_weight: float = 0.15, vol_col: str = "vol_20d") -> dict:
    """最新一个交易日的目标权重(top-k 逆波动加权,单只封顶)。"""
    d = panel.index.get_level_values("date").max()
    sc = score[score.index.get_level_values("date") == d]
    sc = pd.Series(sc.to_numpy(), index=sc.index.get_level_values("symbol"))
    g = panel.xs(d, level="date").assign(score=sc).dropna(subset=["score"])
    n_uni = g.shape[0]
    k = min(k, max(2, n_uni // 3))
    g = g.sort_values("score", ascending=False).head(k)
    w = inverse_vol_weights(g[vol_col] if vol_col in g else pd.Series(np.nan, index=g.index), max_weight)
    return {str(s): round(float(x), 5) for s, x in w.items()}


def step_forward(state: dict, target: dict, prices: dict, today: str, notional: float = 100000.0,
                 horizon: int = 20, cost: float = 0.0015, dd_limit: float = 0.12,
                 derisk: float = 0.5) -> dict:
    """一步前瞻推进(纯函数)。只追加/更新【今天】这一点,过去的净值点绝不改。

    首跑:按 target 建仓,NAV=notional。之后:按当日价标记市值 → 追加今日净值;
    到换仓日(距上次≥horizon天)才换成新 target,并按回撤开关定敞口。
    """
    if not state.get("nav"):                                   # —— 首跑建仓 ——
        return {
            "inception": today, "notional": float(notional),
            "positions": dict(target),
            "entry_prices": {s: float(prices[s]) for s in target if s in prices},
            "entry_nav": float(notional), "last_rebalance": today, "exposure": 1.0,
            "nav": [{"date": today, "nav": float(notional)}],
        }

    pos, ep = state["positions"], state["entry_prices"]
    port_ret = sum(w * (prices[s] / ep[s] - 1)                 # 自上次换仓以来的组合收益
                   for s, w in pos.items() if s in prices and ep.get(s))
    nav_now = round(state["entry_nav"] * (1 + state["exposure"] * port_ret), 2)

    if state["nav"][-1]["date"] != today:                     # —— 只追加/更新今天 ——
        state["nav"].append({"date": today, "nav": nav_now})
    else:
        state["nav"][-1]["nav"] = nav_now                     # 同日重复跑=更新今天,不动历史

    days = (pd.Timestamp(today) - pd.Timestamp(state["last_rebalance"])).days
    if days >= horizon and target:                            # —— 到换仓日 ——
        peak = max(p["nav"] for p in state["nav"])
        dd = nav_now / peak - 1
        state["exposure"] = derisk if dd < -dd_limit else 1.0  # 回撤开关
        state["positions"] = dict(target)
        state["entry_prices"] = {s: float(prices[s]) for s in target if s in prices}
        state["entry_nav"] = round(nav_now * (1 - cost), 2)    # 换仓成本
        state["last_rebalance"] = today
    return state


def forward_summary(state: dict) -> dict:
    navs = [p["nav"] for p in state.get("nav", [])]
    if len(navs) < 1:
        return {"points": 0}
    s = pd.Series(navs)
    peak = s.cummax()
    mdd = float((s / peak - 1).min())
    return {"points": len(navs), "inception": state.get("inception"),
            "nav": navs[-1], "notional": state.get("notional"),
            "return%": round((navs[-1] / navs[0] - 1) * 100, 2),
            "max_dd%": round(mdd * 100, 1), "exposure": state.get("exposure", 1.0),
            "n_positions": len(state.get("positions", {}))}


def run_forward(market: str = "cn", model: str = "composite", notional: float = 100000.0,
                k: int = 20, horizon: int = 20, cost: float = 0.0015,
                dd_limit: float = 0.12, refresh: bool = False) -> dict:
    """实盘一步:取最新数据→算目标→按当日价推进前瞻记录→存档。你机器上跑(需联网)。"""
    from datetime import datetime

    from quantmill.cross import (composite_score, factor_columns, get_panel,
                                 walk_forward_scores)
    from quantmill.data import get_ohlcv
    panel = get_panel(market=market, horizon=horizon, refresh=refresh, verbose=False)
    if model == "composite":
        score = composite_score(panel)
    else:
        nd = panel.index.get_level_values(0).nunique()
        score = walk_forward_scores(panel, factor_columns(panel), horizon=horizon,
                                    init_train=min(504, max(60, nd // 2)), step=63)
    target = target_weights(panel, score, k=k)
    prices = {}                                                # 目标票的最新收盘
    for s in target:
        try:
            prices[s] = float(get_ohlcv(s, market).iloc[-1]["Close"])
        except Exception:  # noqa: BLE001
            pass
    today = datetime.now().strftime("%Y-%m-%d")
    state = step_forward(load_state(market, model), target, prices, today,
                         notional=notional, horizon=horizon, cost=cost, dd_limit=dd_limit)
    save_state(state, market, model)
    return {"state": state, "summary": forward_summary(state), "prices_ok": len(prices)}
