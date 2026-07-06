# -*- coding: utf-8 -*-
"""
neutralize.py —— 因子中性化(行业/市值/beta)
=====================================================================
逐日横截面把因子对"你不想要的暴露"(市值 size、beta、行业哑变量)回归,取残差。
去掉后,因子的 IC/收益就不再是"市值/行业的替身"——因子研究的标配一步。
默认按 size 中性化(平台已有 size 列);传 by=[...] 可加 beta / 行业列。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def neutralize(panel: pd.DataFrame, factor: str, by=("size",),
               dummies: list | None = None) -> pd.Series:
    """逐日把 factor 对 by(连续变量)+ dummies(行业等分类列的哑变量)回归,返回残差。
    残差 index=(date,symbol);某天变量缺失/样本太少 → 该天保留原值(不硬中性化)。"""
    cont = [c for c in by if c in panel.columns]
    cats = [c for c in (dummies or []) if c in panel.columns]
    out = {}
    for d in panel.index.get_level_values("date").unique():
        sub = panel.xs(d, level="date", drop_level=False)
        f = sub[factor].astype(float)
        parts = [pd.Series(1.0, index=sub.index, name="const")]
        if cont:
            parts.append(sub[cont].astype(float))
        for c in cats:                                   # 行业哑变量(drop_first 防共线)
            parts.append(pd.get_dummies(sub[c], prefix=c, drop_first=True).astype(float))
        Z = pd.concat(parts, axis=1)
        ok = f.notna() & Z.notna().all(axis=1)
        if int(ok.sum()) < Z.shape[1] + 3:               # 样本不够回归就跳过(保留原值)
            for k, v in f.items():
                out[k] = v
            continue
        Xm = Z[ok.values].to_numpy(float)
        beta, *_ = np.linalg.lstsq(Xm, f[ok.values].to_numpy(float), rcond=None)
        resid = f[ok.values].to_numpy(float) - Xm @ beta
        for k, r in zip(sub.index[ok.values], resid):
            out[k] = r
        for k in sub.index[~ok.values]:
            out[k] = np.nan
    s = pd.Series(out, name=f"{factor}_neut")
    s.index = pd.MultiIndex.from_tuples(s.index, names=["date", "symbol"])
    return s.reindex(panel.index)


def add_beta(panel: pd.DataFrame, price_col: str = "close", window: int = 60) -> pd.Series:
    """每票对等权市场的滚动 beta(需 keep_close 的 close 列)。可当中性化变量之一。"""
    if price_col not in panel.columns:
        raise ValueError("add_beta 需要 close 列(build_panel(keep_close=True))")
    ret = panel[price_col].groupby(level="symbol").pct_change()
    mkt = ret.groupby(level="date").transform("mean")            # 等权市场收益
    df = pd.DataFrame({"r": ret, "m": mkt})

    def _beta(g):
        cov = g["r"].rolling(window).cov(g["m"])
        var = g["m"].rolling(window).var()
        return cov / var
    return df.groupby(level="symbol", group_keys=False).apply(_beta).rename("beta")
