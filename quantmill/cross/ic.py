# -*- coding: utf-8 -*-
"""
ic.py —— 横截面 IC | cross-sectional information coefficient
=====================================================================
和 factor/analysis.py 的**时序 IC** 是两码事:

    时序 IC    :一只股票,它的因子随时间 vs 它自己未来收益(纵向)
    横截面 IC  :同一天,所有股票的因子 vs 它们各自未来收益(横向排名),再按天平均

后者才是「选股」真正依赖的指标:它衡量的是「因子高的票,是不是当天就比因子低的票涨得多」。
经验值:日频单因子横截面 |IC|~0.02–0.05 已经可用;ICIR(=均值/波动)> 0.3 算稳。

⚠️ horizon 天的未来收益在相邻日高度重叠,t 值会被高估——这里的 t 仅作相对参考。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def daily_ic(panel: pd.DataFrame, factor: str, ret_col: str = "fwd",
             method: str = "spearman", min_names: int = 5) -> pd.Series:
    """逐日横截面 IC 序列。| daily cross-sectional IC series."""
    def _one(g):
        s = g[[factor, ret_col]].dropna()
        if len(s) < min_names or s[factor].std() == 0 or s[ret_col].std() == 0:
            return np.nan
        return s[factor].corr(s[ret_col], method=method)
    return panel.groupby(level="date").apply(_one).dropna()


def ic_summary(panel: pd.DataFrame, factor: str, ret_col: str = "fwd",
               method: str = "spearman") -> dict:
    """单因子横截面 IC 汇总:均值 / ICIR / t / 正比例 / 天数。"""
    ics = daily_ic(panel, factor, ret_col, method)
    if len(ics) == 0:
        return {"factor": factor, "IC": np.nan, "ICIR": np.nan, "t": np.nan,
                "pos%": np.nan, "days": 0}
    mean, std = ics.mean(), ics.std(ddof=1)
    icir = mean / std if std else np.nan
    t = icir * np.sqrt(len(ics)) if std else np.nan
    return {"factor": factor, "IC": round(mean, 4), "ICIR": round(icir, 3),
            "t": round(t, 2), "pos%": round((ics > 0).mean() * 100, 1),
            "days": len(ics)}


def ic_table(panel: pd.DataFrame, factors, ret_col: str = "fwd",
             method: str = "spearman") -> pd.DataFrame:
    """对一组因子算横截面 IC,按 |IC| 降序。| ranked cross-sectional IC table."""
    rows = [ic_summary(panel, f, ret_col, method) for f in factors]
    tab = pd.DataFrame(rows)
    tab["absIC"] = tab["IC"].abs()
    return tab.sort_values("absIC", ascending=False,
                           na_position="last").reset_index(drop=True)
