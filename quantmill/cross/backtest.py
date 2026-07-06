"""
backtest.py —— 横截面 top-k 回测 | cross-sectional top-k backtest
=====================================================================
拿样本外打分 score,每隔 rebalance 天换一次仓:
    · 长多:买 score 最高的 k 只,等权
    · 多空(可选):再融券卖 score 最低的 k 只
基准 = 同一股票池等权(公平对比:同池子无脑等权你能不能跑赢)。

巧妙点:令 rebalance == horizon,则「持有一期的真实收益」正好就是面板里的 fwd,
无需再单独取价——自洽且不重叠(每 horizon 天取一个换仓点)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _metrics(rets: pd.Series, periods_per_year: float) -> dict:
    if len(rets) == 0:
        return {}
    from quantmill.evaluation.metrics import calmar, sortino
    eq = (1 + rets).cumprod()
    total = eq.iloc[-1] - 1
    ann = (1 + total) ** (periods_per_year / len(rets)) - 1
    vol = rets.std(ddof=1) * np.sqrt(periods_per_year)
    sharpe = (rets.mean() * periods_per_year) / vol if vol else np.nan
    peak = eq.cummax()
    mdd = (eq / peak - 1).min()
    return {"总收益": round(total * 100, 1), "年化": round(ann * 100, 1),
            "夏普": round(sharpe, 2), "Sortino": round(sortino(rets, periods_per_year), 2),
            "Calmar": round(calmar(rets, periods_per_year), 2),
            "最大回撤": round(mdd * 100, 1), "期数": len(rets)}


def topk_backtest(panel: pd.DataFrame, score: pd.Series, k: int = 20,
                  horizon: int = 20, ret_col: str = "fwd",
                  long_short: bool = False, cost: float = 0.0) -> dict:
    """按 score 每 horizon 天换仓选 top-k,和等权基准比。

    返回 {equity, metrics}:曲线(策略/基准/[多空])+ 指标表。
    """
    df = panel[[ret_col]].copy()
    df["score"] = score
    df = df.dropna(subset=["score", ret_col])

    dates = df.index.get_level_values("date").unique().sort_values()
    rebal = dates[::horizon]                         # 不重叠换仓点

    rows, picks = [], []                             # picks:每期 top-k 标的,算换手用
    picks_by_date = {}                               # {date:[symbols]},供归因用
    for d in rebal:
        g = df.xs(d, level="date")
        if len(g) < 2 * k + 5:
            continue
        g = g.sort_values("score", ascending=False)
        top = g.head(k)
        long_ret = top[ret_col].mean()
        bench_ret = g[ret_col].mean()
        picks.append(list(top.index))                # index = symbol
        picks_by_date[d] = list(top.index)
        rec = {"date": d, "long": long_ret, "bench": bench_ret}
        if long_short:
            short_ret = g.tail(k)[ret_col].mean()
            rec["ls"] = long_ret - short_ret         # 多空:买强卖弱
        rows.append(rec)

    if rows:
        bt = pd.DataFrame(rows).set_index("date")
    else:
        cols = ["long", "bench"] + (["ls"] if long_short else [])
        bt = pd.DataFrame(columns=cols)
        bt.index = pd.DatetimeIndex([], name="date")
    if cost:                                          # 换手成本(每期两边各扣一次)
        bt["long"] -= cost
        if long_short:
            bt["ls"] -= 2 * cost

    ppy = 252.0 / horizon                             # 每年换仓期数
    out = {"equity": bt, "picks": picks_by_date, "metrics": {
        "策略 top-k": _metrics(bt["long"], ppy),
        "基准 等权": _metrics(bt["bench"], ppy),
    }}
    if long_short:
        out["metrics"]["多空 L/S"] = _metrics(bt["ls"], ppy)
    # 超额 + 信息比 IR + 换手率(量化人一打开就找的)
    from quantmill.evaluation.metrics import information_ratio, turnover_from_sets
    if out["metrics"]["策略 top-k"] and out["metrics"]["基准 等权"]:
        out["metrics"]["策略 top-k"]["超额年化"] = round(
            out["metrics"]["策略 top-k"]["年化"] - out["metrics"]["基准 等权"]["年化"], 1)
        out["metrics"]["策略 top-k"]["信息比IR"] = round(
            information_ratio(bt["long"], bt["bench"], ppy), 2)
        out["metrics"]["策略 top-k"]["换手率%"] = round(turnover_from_sets(picks) * 100, 1)
    return out
