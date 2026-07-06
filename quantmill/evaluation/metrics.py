# -*- coding: utf-8 -*-
"""
metrics.py —— 标准绩效指标(纯函数,收益序列上即可算)
=====================================================================
量化人一打开就找的四个:Sortino(只罚下行波动)/ Calmar(年化÷最大回撤)/
Information Ratio(超额均值÷超额波动)/ Turnover(换手率)。全部纯函数、可离线测。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _ann_return(rets: pd.Series, ppy: float) -> float:
    n = len(rets)
    if n == 0:
        return float("nan")
    total = float((1 + rets).prod() - 1)
    return (1 + total) ** (ppy / n) - 1


def sortino(rets, ppy: float, target: float = 0.0) -> float:
    """索提诺:年化收益 ÷ 年化【下行】波动。只罚亏损波动,涨得猛不算风险。"""
    r = pd.Series(rets).dropna()
    if len(r) < 2:
        return float("nan")
    downside = (r[r < target] - target)
    dd = np.sqrt((downside ** 2).mean()) * np.sqrt(ppy) if len(downside) else 0.0
    return float(_ann_return(r, ppy) / dd) if dd > 0 else float("nan")


def calmar(rets, ppy: float) -> float:
    """卡玛:年化收益 ÷ |最大回撤|。衡量"每承受一单位回撤换来多少年化"。"""
    r = pd.Series(rets).dropna()
    if len(r) < 2:
        return float("nan")
    eq = (1 + r).cumprod()
    mdd = float((eq / eq.cummax() - 1).min())
    return float(_ann_return(r, ppy) / abs(mdd)) if mdd < 0 else float("nan")


def information_ratio(rets, bench, ppy: float) -> float:
    """信息比 IR:超额收益(策略−基准)的年化均值 ÷ 年化波动。衡量跑赢基准的稳定性。"""
    a = pd.concat([pd.Series(rets).rename("r"), pd.Series(bench).rename("b")],
                  axis=1).dropna()
    if len(a) < 2:
        return float("nan")
    ex = a["r"] - a["b"]
    v = float(ex.std(ddof=1) * np.sqrt(ppy))
    return float(ex.mean() * ppy / v) if v > 0 else float("nan")


def turnover_from_sets(holdings) -> float:
    """换手率(单边,0~1):每次换仓相对上次【新进】的比例,再平均。适合等权 top-k。"""
    hs = [set(h) for h in holdings]
    if len(hs) < 2:
        return 0.0
    t = [len(b - a) / max(len(b), 1) for a, b in zip(hs, hs[1:])]
    return float(np.mean(t))


def turnover_from_weights(weights: pd.DataFrame) -> float:
    """换手率(单次单边):每日权重变动只在换仓日非零,取这些日 0.5·Σ|Δw| 的均值。"""
    dw = weights.diff().abs().sum(axis=1)
    ch = dw[dw > 1e-9]
    return float(0.5 * ch.mean()) if len(ch) else 0.0
