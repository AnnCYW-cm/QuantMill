# -*- coding: utf-8 -*-
"""
overlay.py —— 风控叠加层 | risk overlay on the cross-sectional top-k backtest
=====================================================================
把选股打分(score)变成【风险管理后的】资金曲线,并与"等权满仓"对照,
让你看清风控到底把回撤/波动压下去多少、代价是多少收益。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def inverse_vol_weights(vols: pd.Series, max_weight: float = 0.15) -> pd.Series:
    """逆波动加权 + 单只封顶,归一化。缺波动的退等权。| inverse-vol weights, capped."""
    v = pd.to_numeric(vols, errors="coerce")
    if v.isna().all() or (v.fillna(0) <= 0).all():
        w = pd.Series(1.0 / len(vols), index=vols.index)
    else:
        inv = 1.0 / v.replace(0, np.nan)
        w = (inv / inv.sum()).fillna(0.0)
    for _ in range(10):                       # 迭代封顶:超上限的削平,剩余按比例补回
        over = w > max_weight
        if not over.any():
            break
        excess = (w[over] - max_weight).sum()
        w[over] = max_weight
        room = w[~over]
        if room.sum() <= 0:
            break
        w[~over] = room + excess * room / room.sum()
    return w / w.sum()


def _metrics(r: pd.Series, ppy: float) -> dict:
    if len(r) == 0:
        return {}
    eq = (1 + r).cumprod()
    total = float(eq.iloc[-1] - 1)
    ann = float((1 + total) ** (ppy / len(r)) - 1)
    vol = float(r.std(ddof=1) * np.sqrt(ppy)) if len(r) > 1 else 0.0
    sharpe = float(r.mean() * ppy / vol) if vol else float("nan")
    mdd = float((eq / eq.cummax() - 1).min())
    return {"总收益%": round(total * 100, 1), "年化%": round(ann * 100, 1),
            "年化波动%": round(vol * 100, 1), "夏普": round(sharpe, 2),
            "最大回撤%": round(mdd * 100, 1)}


def risk_managed_backtest(panel: pd.DataFrame, score: pd.Series, k: int = 20,
                          horizon: int = 20, cost: float = 0.0015,
                          target_vol: float = 0.15, max_weight: float = 0.15,
                          dd_limit: float = 0.12, derisk: float = 0.5,
                          max_leverage: float = 1.0, vol_col: str = "vol_20d") -> dict:
    """风控后的 top-k 回测,并与等权满仓对照。

    target_vol   年化波动目标(缩放总敞口)| annualized vol target
    max_weight   单只权重上限 | per-name cap
    dd_limit     回撤开关阈值(净值从高点回撤超此值就降仓)
    derisk       触发回撤开关时的降仓系数
    max_leverage 敞口上限(默认 1.0 = 不加杠杆)
    """
    df = panel[["fwd"]].copy()
    df["score"] = score
    df["vol"] = panel[vol_col] if vol_col in panel.columns else np.nan
    df = df.dropna(subset=["fwd", "score"])
    n_uni = df.index.get_level_values("symbol").nunique()
    k = min(k, max(2, n_uni // 3))
    dates = df.index.get_level_values("date").unique().sort_values()[::horizon]
    ppy = 252.0 / horizon

    raw_eq = mgd_eq = mgd_peak = 1.0
    hist: list[float] = []                    # 组合毛收益历史(估波动用,只到上一期)
    rows = []
    for d in dates:
        g = df.xs(d, level="date")
        if len(g) < k:
            continue
        g = g.sort_values("score", ascending=False).head(k)
        w = inverse_vol_weights(g["vol"], max_weight)
        gross = float((w * g["fwd"]).sum())            # 风险加权的毛收益
        raw = float(g["fwd"].mean())                   # 对照:等权满仓

        exposure = 1.0                                 # ① 波动率目标(用过去毛收益估波动)
        if len(hist) >= 6:
            rv = float(np.std(hist[-12:], ddof=1)) * np.sqrt(ppy)
            if rv > 0:
                exposure = min(max_leverage, target_vol / rv)
        dd = mgd_eq / mgd_peak - 1                      # ② 回撤开关(只看已实现净值)
        if dd < -dd_limit:
            exposure *= derisk

        net = exposure * (gross - cost)
        hist.append(gross)
        raw_eq *= (1 + raw - cost)
        mgd_eq *= (1 + net)
        mgd_peak = max(mgd_peak, mgd_eq)
        rows.append({"date": d, "raw": raw - cost, "managed": net, "exposure": round(exposure, 2)})

    bt = pd.DataFrame(rows).set_index("date")
    return {
        "equity": bt, "k_used": k, "periods": len(bt),
        "avg_exposure": round(float(bt["exposure"].mean()), 2) if len(bt) else None,
        "metrics": {"等权满仓": _metrics(bt["raw"], ppy) if len(bt) else {},
                    "风控后": _metrics(bt["managed"], ppy) if len(bt) else {}},
    }
